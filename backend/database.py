import sqlite3
import csv
from pathlib import Path

DB_PATH   = Path(__file__).parent / "kanji.db"
CSV_PATH  = Path(__file__).parent / "heisig-kanjis.csv"
PRIM_PATH = Path(__file__).parent / "data.txt"
PDF_PATH  = Path(__file__).parent / "data_from_pdf.txt"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # Without this, a writer that finds the DB locked (another connection mid-write)
    # raises "database is locked" immediately instead of waiting — surfaced concretely
    # by the isolated test suite (architecture review finding #3, test_api_search.py),
    # where a test fixture holding one connection open while making an API call on a
    # second connection hit exactly this. Previously a known, accepted, low-priority
    # gap (CLAUDE.md's "no PRAGMA busy_timeout... cheap fix if it comes up") — fixed
    # here since it just did. 5s comfortably covers this app's short, simple
    # transactions; WAL mode already means readers never block writers or each other,
    # so this only matters for writer-vs-writer contention.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kanji (
            id          TEXT PRIMARY KEY,
            character   TEXT,
            keyword     TEXT,
            frame       INTEGER,
            stroke_count INTEGER,
            jlpt        TEXT
        );

        CREATE TABLE IF NOT EXISTS aliases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            alias       TEXT NOT NULL,
            UNIQUE(kanji_id, alias)
        );
        CREATE INDEX IF NOT EXISTS idx_aliases_alias  ON aliases(alias);
        CREATE INDEX IF NOT EXISTS idx_aliases_kanji  ON aliases(kanji_id);

        CREATE TABLE IF NOT EXISTS parts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            part_term   TEXT NOT NULL,
            position    INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_parts_kanji ON parts(kanji_id);
        CREATE INDEX IF NOT EXISTS idx_parts_term  ON parts(part_term);
    """)
    conn.commit()
    conn.close()


def db_conn():
    """FastAPI dependency: yields a connection, closes it after the request."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


_MIGRATIONS = []  # populated below each _migrate_vN definition via _register


def _register(version, fn):
    _MIGRATIONS.append((version, fn))
    return fn


def migrate_schema(conn):
    """
    Idempotent schema upgrades gated by PRAGMA user_version — safe to call on every
    startup, on both a fresh DB and an existing populated one. Each version's body is
    guarded by its own `if version < N` so re-running against a DB already past that
    version never re-issues a non-idempotent statement (e.g. a bare ALTER TABLE ADD
    COLUMN, which errors on a second run unlike CREATE TABLE IF NOT EXISTS).

    Each version's DDL/DML and its PRAGMA user_version bump run inside one explicit
    transaction (BEGIN ... COMMIT/ROLLBACK), so a crash or error partway through a
    version can never leave user_version pointing at an old version while some of
    that version's schema changes already landed (which would make the *next*
    startup fail on a duplicate ALTER TABLE / CREATE TABLE, since those aren't
    idempotent against a half-applied version). Each _migrate_vN body must therefore
    use conn.execute() per-statement, not conn.executescript() — executescript()
    always implicitly commits first and doesn't compose with a manually-opened
    transaction, which would silently defeat this. (Found and fixed 2026-08-31,
    architecture review finding #2 — see docs/2026-08-31-architecture-review.md.)
    Verified against a temp DB with a fault injected mid-version: user_version
    stays at the pre-migration value and none of that version's schema changes are
    visible, so the next startup retries the whole version cleanly instead of
    erroring on a duplicate ALTER TABLE.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    for target_version, fn in sorted(_MIGRATIONS, key=lambda pair: pair[0]):
        if version >= target_version:
            continue
        conn.execute("BEGIN")
        try:
            fn(conn)
            # PRAGMA user_version can't take a bound parameter; target_version is a
            # fixed int literal from this module's own _register() calls, not
            # user input, so an f-string here is safe.
            conn.execute(f"PRAGMA user_version = {target_version}")
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
            version = target_version


def _migrate_v1(conn):
    """"DB is a disposable cache" -> "DB is the source of truth": adds
    users/sessions/decompositions/stories tables and owner_id/visibility/script/
    variant_of columns on kanji/aliases/parts.

    Runs as individual conn.execute() statements rather than one executescript()
    call — see migrate_schema()'s docstring for why (executescript() always
    implicitly commits, which would defeat the transaction migrate_schema() wraps
    this in)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            username          TEXT NOT NULL UNIQUE,
            password_hash     TEXT,
            auth_provider     TEXT NOT NULL DEFAULT 'local',
            provider_user_id  TEXT,
            display_name      TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")

    conn.execute("CREATE TABLE IF NOT EXISTS user_entry_seq (id INTEGER PRIMARY KEY AUTOINCREMENT)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS decompositions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            owner_id    INTEGER NOT NULL REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('public','private')),
            label       TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decomp_kanji ON decompositions(kanji_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_decomp_owner ON decompositions(owner_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            owner_id    INTEGER NOT NULL REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('public','private')),
            story       TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(kanji_id, owner_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_kanji ON stories(kanji_id)")

    # Reserved system account, fixed id=1 — owns all Heisig-seeded data. Must exist
    # before the ALTER TABLEs below, which default owner_id to 1.
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, auth_provider, display_name) "
        "VALUES (1, 'system', 'system', 'Heisig / System')"
    )

    # Note: SQLite rejects ADD COLUMN ... REFERENCES ... with a non-NULL DEFAULT in the
    # same statement ("Cannot add a REFERENCES column with non-NULL default value"), so
    # owner_id is a plain INTEGER here (FK integrity enforced by always writing valid
    # user ids at the application layer, same as this app already does for kanji_id
    # elsewhere). variant_of/decomposition_id have no default, so REFERENCES is fine there.
    conn.execute("ALTER TABLE kanji ADD COLUMN owner_id   INTEGER NOT NULL DEFAULT 1")
    conn.execute("ALTER TABLE kanji ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private'))")
    conn.execute("ALTER TABLE kanji ADD COLUMN script     TEXT NOT NULL DEFAULT 'ja-kanji' CHECK(script IN ('ja-kanji','zh-Hans','zh-Hant','zh-Hani'))")
    conn.execute("ALTER TABLE kanji ADD COLUMN variant_of TEXT REFERENCES kanji(id)")

    conn.execute("ALTER TABLE parts ADD COLUMN decomposition_id INTEGER REFERENCES decompositions(id)")

    # aliases: relax UNIQUE(kanji_id, alias) -> UNIQUE(kanji_id, alias, owner_id) so two
    # different users can submit the same alias text. SQLite can't alter a UNIQUE
    # constraint in place, so rebuild the table.
    conn.execute("""
        CREATE TABLE aliases_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            alias       TEXT NOT NULL,
            owner_id    INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private')),
            UNIQUE(kanji_id, alias, owner_id)
        )
    """)
    conn.execute("""
        INSERT INTO aliases_new (id, kanji_id, alias, owner_id, visibility)
            SELECT id, kanji_id, alias, 1, 'public' FROM aliases
    """)
    conn.execute("DROP TABLE aliases")
    conn.execute("ALTER TABLE aliases_new RENAME TO aliases")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_kanji ON aliases(kanji_id)")

    _backfill_decompositions(conn)


_register(1, _migrate_v1)


def _migrate_v2(conn):
    """Adds per-account UI language and study-language (script) preferences."""
    conn.execute("ALTER TABLE users ADD COLUMN ui_language  TEXT NOT NULL DEFAULT 'en' CHECK(ui_language IN ('en','ru'))")
    conn.execute("ALTER TABLE users ADD COLUMN study_script TEXT CHECK(study_script IN ('ja-kanji','zh-Hans','zh-Hant'))")


_register(2, _migrate_v2)


def _migrate_v3(conn):
    """Adds kanji.image_url for user-invented primitives with no real Unicode glyph
    (an uploaded picture stands in for a `character`)."""
    conn.execute("ALTER TABLE kanji ADD COLUMN image_url TEXT")


_register(3, _migrate_v3)


def _migrate_v4(conn):
    """
    In-app decomposition review queue: a logged-in user can mark a decomposition
    "approved" (correct as shown) or "disputed" (looks wrong) straight from the
    detail page, instead of that judgement only ever happening in an out-of-band
    audit session. One row per (decomposition, reviewer) — a reviewer can change
    their mind, which upserts rather than piling up duplicate rows.

    `processed_at` distinguishes "reviewed" from "acted on": approved rows get
    turned into a pinned regression-test entry and disputed rows get individually
    investigated, both by a maintainer working through review_queue.py — at which
    point that row is marked processed so it drops out of the pending queue. This
    is the "запомни этот метод" standing verification practice from the audit,
    exposed as a UI affordance instead of only ever running from a rendered PNG.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decomposition_reviews (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            decomposition_id INTEGER NOT NULL REFERENCES decompositions(id),
            kanji_id         TEXT NOT NULL REFERENCES kanji(id),
            verdict          TEXT NOT NULL CHECK(verdict IN ('approved','disputed')),
            reviewer_id      INTEGER NOT NULL REFERENCES users(id),
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            processed_at     TEXT,
            UNIQUE(decomposition_id, reviewer_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_verdict ON decomposition_reviews(verdict, processed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_decomp   ON decomposition_reviews(decomposition_id)")


_register(4, _migrate_v4)


def _migrate_v5(conn):
    """
    A simple first-party visit counter (2026-08-29, owner-requested, after nginx-log
    analysis showed the site's raw traffic is almost entirely bots/scanners with no
    way to tell a real visitor from one without reading logs by hand). One row per
    page load, tagged with a random visitor_id stored in a long-lived first-party
    cookie (see analytics.py) — deliberately not IP-based, so it naturally excludes
    the vast majority of non-JS-executing bot traffic (a bot hitting a URL directly
    never runs the frontend JS that calls this), unlike parsing web server logs.
    `visit_stats.py` is the owner-facing read side, same "one-off script reads
    kanji.db directly" convention as review_queue.py/coverage_status.py rather than
    a public HTTP stats endpoint — no admin-role concept exists in this schema yet.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS page_views (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id  TEXT NOT NULL,
            path        TEXT,
            viewed_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_page_views_visitor ON page_views(visitor_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_page_views_time ON page_views(viewed_at)")


_register(5, _migrate_v5)


def _migrate_v6(conn):
    """
    Analytics retention (2026-08-31, architecture review finding #4): page_views had
    no pruning at all — an unauthenticated endpoint (POST /analytics/pageview) that
    grows the table forever is exactly the "easy unbounded-growth vector" the review
    flagged. A naive "delete rows older than N days" would silently corrupt
    visit_stats.py's all-time unique-visitor count (a visitor whose only rows got
    pruned stops counting as ever having visited) and break its --days N breakdown
    for pruned ranges, so pruning needs to aggregate first, not just delete.

    daily_visit_summary holds one row per calendar day (view_count, distinct_
    visitor_count for that day alone — accurate forever, independent of whether the
    raw page_views rows for that day still exist). known_visitors holds one row per
    visitor_id ever seen, first/last-seen timestamps — this is what makes an
    all-time distinct-visitor count possible after old page_views rows are gone;
    daily per-day distinct counts alone can't dedupe a visitor who returns across
    multiple days once the raw rows backing earlier days are pruned.
    prune_page_views.py (added alongside this migration) is the maintenance script
    that populates both of these from page_views before deleting old raw rows —
    same "one-off script, run on a schedule" convention as backup_db.py.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_visit_summary (
            day                     TEXT PRIMARY KEY,
            view_count              INTEGER NOT NULL,
            distinct_visitor_count  INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_visitors (
            visitor_id  TEXT PRIMARY KEY,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL
        )
    """)


_register(6, _migrate_v6)


def record_page_view(conn, visitor_id: str, path: str | None):
    conn.execute(
        "INSERT INTO page_views (visitor_id, path) VALUES (?, ?)",
        (visitor_id, path)
    )
    conn.commit()


def _backfill_decompositions(conn):
    """
    Ensure every kanji_id present in `parts` has a system decomposition row, and every
    parts row is linked to it. Idempotent — safe to call after migrate_schema() (upgrading
    a populated DB, where parts already has rows) and after import_data() (seeding a fresh
    DB, where parts gets populated only after migrate_schema() already ran).

    Does not commit — callers own the transaction boundary (migrate_schema() wraps
    its _migrate_v1() call, which calls this, in one atomic transaction; import_data()
    commits once at the end of its own flow). Committing here would either be a
    silent no-op (inside migrate_schema()'s already-open transaction, conn.commit()
    just ends it early) or, worse, close out a transaction a caller expected to
    still be able to roll back.
    """
    conn.execute("""
        INSERT INTO decompositions (kanji_id, owner_id, visibility, label)
        SELECT DISTINCT kanji_id, 1, 'public', NULL FROM parts
        WHERE kanji_id NOT IN (SELECT kanji_id FROM decompositions WHERE owner_id = 1)
    """)
    conn.execute("""
        UPDATE parts SET decomposition_id = (
            SELECT id FROM decompositions d WHERE d.kanji_id = parts.kanji_id AND d.owner_id = 1
        ) WHERE decomposition_id IS NULL
    """)


def _load_parts_file(path: Path) -> dict[str, list[str]]:
    """Load {id: [part_terms]} from a data file. ASCII parts are lowercased; kanji chars kept
    as-is. A line with a present-but-empty parts field (e.g. `rtk639:心:heart:`) is an explicit
    "this primitive is atomic" override and is kept as `id: []` — distinct from a line that
    omits the parts column entirely (fewer than 4 `:`-fields), which means "no opinion" and is
    skipped so the other source file's value (if any) isn't clobbered. import_data()'s merge/
    override loop relies on this distinction to actually apply an empty override instead of
    silently falling back to data_from_pdf.txt / the CSV."""
    result: dict[str, list[str]] = {}
    if not path.exists():
        return result
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split(":")
            pid = cols[0].strip().lower()
            if not pid or len(cols) < 4:
                continue
            parts_str = cols[3].strip()
            raw = [p.strip() for p in parts_str.replace(";", ",").split(",") if p.strip()]
            normalised = [p.lower() if p.isascii() else p for p in raw]
            result[pid] = normalised
    return result


def _build_char_lookup(conn) -> tuple[dict[str, list[tuple[str, str]]], dict[str, str]]:
    """Build (character -> [(kanji_id, script), ...] candidates, kanji_id -> keyword)
    lookups for expand_part_terms. A glyph can have more than one candidate when it
    exists as both a ja-kanji row and a separate zh-* row (~2,628 of them, see
    CLAUDE.md's script-aware resolution section) — expand_part_terms disambiguates
    using script_group, the same _script_group() pattern _resolve_parts_detail already
    uses at read time."""
    char_to_candidates: dict[str, list[tuple[str, str]]] = {}
    for r in conn.execute("SELECT id, character, script FROM kanji WHERE character IS NOT NULL AND character != ''").fetchall():
        if r["character"] not in ("?", "??"):
            char_to_candidates.setdefault(r["character"], []).append((r["id"], r["script"]))
    id_to_keyword: dict[str, str] = {
        r["id"]: r["keyword"]
        for r in conn.execute("SELECT id, keyword FROM kanji WHERE keyword IS NOT NULL").fetchall()
    }
    return char_to_candidates, id_to_keyword


def expand_part_terms(conn, terms: list[str], char_lookup: tuple[dict, dict] | None = None,
                       script_group: str | None = None) -> list[str]:
    """
    If a part term is itself a kanji CHARACTER (rather than a primitive name), also
    include that character's keyword right after it, so keyword-based search matches
    without the contributor having to type both. char_lookup can be passed in (from
    _build_char_lookup) to avoid rebuilding it on every call in a bulk loop like
    import_data()'s; for a single one-off submission it's built fresh here, which is
    cheap at that scale.

    script_group (a _script_group() value, "ja"/"zh"/None) picks which candidate's
    keyword to use when the glyph is ambiguous across scripts, preferring a match to
    the decomposition's own script and falling back to the first candidate otherwise.
    Before this parameter existed, the "first" candidate was really whichever row a
    fresh, unordered dict-building query happened to return last — non-deterministic
    in practice, and a real bug (found 2026-08-13, see docs/2026-08-search-quality-
    audit.md): a shared glyph could silently pull in the wrong script's keyword.
    """
    char_to_candidates, id_to_keyword = char_lookup if char_lookup else _build_char_lookup(conn)
    expanded = []
    for term in terms:
        candidates = char_to_candidates.get(term)
        if candidates:
            expanded.append(term)
            chosen_id = None
            if script_group:
                chosen_id = next(
                    (kid for kid, script in candidates if _script_group(script) == script_group), None
                )
            if chosen_id is None:
                chosen_id = candidates[0][0]
            kw = id_to_keyword.get(chosen_id)
            if kw:
                expanded.append(kw)
        else:
            expanded.append(term)
    return expanded


def import_data():
    """
    Import all RTK kanji from heisig-kanjis.csv, then overlay
    primitive definitions from data.txt (for missing chars / extra aliases).

    Component terms in the CSV are already fully expanded (all sub-levels
    included), so search is a simple flat set-intersection after alias expansion.

    The DB is the source of truth now, not a disposable cache: this is a one-time
    seed, not a live/repeatable reset. It's a no-op once system data already exists
    (checked below), so user contributions are never at risk from a later call —
    but if invoked manually against a populated DB (e.g. for a local dev reset)
    the deletes below are still scoped to owner_id=1 (system) rows only.
    """
    conn = get_db()
    already_seeded = conn.execute(
        "SELECT COUNT(*) FROM kanji WHERE owner_id = 1"
    ).fetchone()[0] > 0
    if already_seeded:
        conn.close()
        print("System data already seeded; import_data() is a no-op. "
              "For a local dev reset, delete kanji.db and restart instead.")
        return

    conn.executescript("""
        DELETE FROM parts WHERE kanji_id IN (SELECT id FROM kanji WHERE owner_id = 1);
        DELETE FROM aliases WHERE owner_id = 1;
        DELETE FROM kanji WHERE owner_id = 1;
    """)

    # ── 1. Load primitives AND overrides from data.txt ────────────────────────
    prim_aliases:  dict[str, list[str]] = {}   # id -> [alias, ...]
    prim_chars:    dict[str, str]       = {}   # id -> character

    if PRIM_PATH.exists():
        with open(PRIM_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split(":")
                pid = cols[0].strip().lower()
                if not pid:
                    continue
                char = cols[1].strip() if len(cols) > 1 else ""
                alias_str = cols[2].strip() if len(cols) > 2 else ""
                aliases = [a.strip().lower() for a in alias_str.split(",") if a.strip()]
                prim_aliases[pid] = aliases
                if char and char not in ("?", "??", ""):
                    prim_chars[pid] = char

    parts_override = _load_parts_file(PRIM_PATH)
    pdf_parts      = _load_parts_file(PDF_PATH)

    # Merge: data.txt overrides take priority; PDF fills in where data.txt is silent
    merged_parts_override: dict[str, list[str]] = {**pdf_parts, **parts_override}

    # ── 2. Build alias → canonical-id lookup from primitives ──────────────────
    alias_to_id: dict[str, str] = {}
    for pid, aliases in prim_aliases.items():
        for a in aliases:
            if a not in alias_to_id:
                alias_to_id[a] = pid
        if pid not in alias_to_id:
            alias_to_id[pid] = pid

    # ── 3. Import from heisig-kanjis.csv ──────────────────────────────────────
    rows_to_insert = []
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            frame_raw = row.get("id_6th_ed", "").strip()
            if not frame_raw:
                continue
            try:
                frame = int(frame_raw)
            except ValueError:
                continue

            char     = row["kanji"].strip()
            keyword  = (row.get("keyword_6th_ed") or row.get("keyword_5th_ed", "")).strip().lower()
            comp_str = row.get("components", "").strip()
            strokes  = row.get("stroke_count", "").strip()
            jlpt     = row.get("jlpt", "").strip()

            comp_terms = [t.strip().lower() for t in comp_str.split(";") if t.strip()] if comp_str else []

            entry_id = f"rtk{frame}"
            rows_to_insert.append({
                "id": entry_id,
                "char": char,
                "keyword": keyword,
                "frame": frame,
                "strokes": int(strokes) if strokes.isdigit() else None,
                "jlpt": jlpt,
                "comp_terms": comp_terms,
            })

    conn.executemany(
        "INSERT OR IGNORE INTO kanji (id, character, keyword, frame, stroke_count, jlpt) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(r["id"], r["char"], r["keyword"], r["frame"], r["strokes"], r["jlpt"])
         for r in rows_to_insert]
    )

    for r in rows_to_insert:
        _insert_alias(conn, r["id"], r["keyword"])
        _insert_alias(conn, r["id"], str(r["frame"]))
        if r["char"]:
            _insert_alias(conn, r["id"], r["char"])

    for r in rows_to_insert:
        for pos, term in enumerate(r["comp_terms"]):
            conn.execute(
                "INSERT INTO parts (kanji_id, part_term, position) VALUES (?, ?, ?)",
                (r["id"], term, pos)
            )

    # ── 4. Insert primitive entries from data.txt ─────────────────────────────
    # Pre-build lookup dicts to avoid per-primitive DB queries in the loop.
    char_to_id:   dict[str, str] = {}
    existing_ids: set[str]       = set()
    for r in conn.execute("SELECT id, character FROM kanji").fetchall():
        existing_ids.add(r["id"])
        if r["character"] and r["character"] not in ("?", "??", ""):
            char_to_id[r["character"]] = r["id"]

    for pid, aliases in prim_aliases.items():
        char    = prim_chars.get(pid, "?")
        keyword = aliases[0] if aliases else pid

        canonical = pid
        if char and char not in ("?", "??"):
            canonical = char_to_id.get(char, pid)
        if canonical == pid:
            for a in aliases:
                if a in existing_ids:
                    canonical = a
                    break

        if canonical == pid and pid not in existing_ids:
            conn.execute(
                "INSERT OR IGNORE INTO kanji (id, character, keyword) VALUES (?, ?, ?)",
                (pid, char, keyword)
            )
            existing_ids.add(pid)

        for a in aliases:
            _insert_alias(conn, canonical, a)
        _insert_alias(conn, canonical, pid)
        if char and char not in ("?", "??"):
            _insert_alias(conn, canonical, char)

    # ── 5. Apply parts overrides ───────────────────────────────────────────────
    char_lookup = _build_char_lookup(conn)

    overrides_applied = 0
    for pid, parts in merged_parts_override.items():
        canonical = resolve_alias(conn, pid)
        if not canonical:
            continue

        # parts may legitimately be [] here — an explicit "this is atomic" override
        # (see _load_parts_file) — in which case we still clear any fallback parts,
        # just insert nothing.
        expanded_terms = expand_part_terms(conn, parts, char_lookup, script_group="ja") if parts else []

        conn.execute("DELETE FROM parts WHERE kanji_id = ?", (canonical,))
        if expanded_terms:
            conn.executemany(
                "INSERT INTO parts (kanji_id, part_term, position) VALUES (?, ?, ?)",
                [(canonical, term, pos) for pos, term in enumerate(expanded_terms)]
            )
        overrides_applied += 1

    _backfill_decompositions(conn)

    conn.commit()
    conn.close()
    print(f"Import complete: {len(rows_to_insert)} kanji rows, {overrides_applied} parts overrides applied "
          f"({len(pdf_parts)} from PDF, {len(parts_override)} from data.txt, "
          f"{len(pdf_parts) - len(set(pdf_parts) - set(parts_override))} PDF entries superseded by data.txt).")


def _insert_alias(conn, kanji_id: str, alias: str, owner_id: int = 1, visibility: str = "public"):
    alias = alias.strip().lower()
    if alias:
        conn.execute(
            "INSERT OR IGNORE INTO aliases (kanji_id, alias, owner_id, visibility) VALUES (?, ?, ?, ?)",
            (kanji_id, alias, owner_id, visibility)
        )


# ── Query helpers ─────────────────────────────────────────────────────────────
#
# Every read function below takes an optional viewer_id: int | None. None means an
# anonymous viewer, who only ever sees visibility='public' rows. A logged-in viewer
# additionally sees their own private rows. The SQL pattern throughout is
# `(visibility = 'public' OR owner_id = ?)` with viewer_id bound as the parameter —
# when viewer_id is None, `owner_id = NULL` is never true in SQL, so this correctly
# collapses to "public only" with no special-casing needed.

# Most ja-kanji rows share their glyph with a separate zh-* row (e.g. '一' exists as
# both rtk1 and hanzi-4e00, each with their own '一' alias). SCRIPT_VISIBILITY maps a
# study-language filter to the set of `kanji.script` values it should match — picking
# a Chinese variant also includes the script-neutral zh-Hani rows (no
# simplified/traditional distinction). Used to scope search results.
SCRIPT_VISIBILITY: dict[str, tuple[str, ...]] = {
    "ja-kanji": ("ja-kanji",),
    "zh-Hans": ("zh-Hans", "zh-Hani"),
    "zh-Hant": ("zh-Hant", "zh-Hani"),
}


SOURCE_SCOPES = ("system", "community", "mine")

# Shared depth cap for anything that walks the decomposition tree recursively (query-time
# hierarchy resolution for the detail view, and recursive search below) — bounds both
# runaway recursion and the cost of a very common primitive's reachability search.
MAX_DECOMPOSITION_DEPTH = 5


def _source_scope_sql(prefix: str, sources: set[str] | None, viewer_id: int | None) -> tuple[str, list]:
    """Build a SQL fragment restricting `{prefix}owner_id`/`{prefix}visibility` to the
    selected content sources — 'system' (owner_id=1), 'community' (any other owner's
    public rows), 'mine' (the viewer's own rows, regardless of visibility). `sources`
    of None (or all three) means no restriction — every visible row passes, same as
    before this filter existed. An empty set means nothing matches (all sources
    deselected), returned as the literal '0' so it composes into an AND'd WHERE clause.
    `prefix` is the table alias plus '.', e.g. "k." — pass "" for an unaliased table."""
    if sources is None or set(sources) >= set(SOURCE_SCOPES):
        return "", []
    owner_col, vis_col = f"{prefix}owner_id", f"{prefix}visibility"
    clauses, params = [], []
    if "system" in sources:
        clauses.append(f"{owner_col} = 1")
    if "community" in sources:
        clauses.append(f"({owner_col} != 1 AND {vis_col} = 'public')")
    if "mine" in sources:
        clauses.append(f"{owner_col} = ?")
        params.append(viewer_id)
    if not clauses:
        return "0", []
    return f"({' OR '.join(clauses)})", params


def _script_group(script: str | None) -> str | None:
    """Coarse ja/zh grouping (ignoring Simplified/Traditional/neutral) used to
    disambiguate a shared-glyph term against the script of the kanji it's part of,
    independent of the viewer's own study-language filter."""
    if script == "ja-kanji":
        return "ja"
    if script in ("zh-Hans", "zh-Hant", "zh-Hani"):
        return "zh"
    return None


def resolve_alias(conn, term: str, viewer_id: int | None = None,
                   script_scope: tuple[str, ...] | None = None) -> str | None:
    """Return canonical kanji id for a term (alias or id), visible to viewer_id.
    When script_scope is given and the term is ambiguous across scripts (e.g. '一'
    matching both an rtk row and a hanzi row), prefers a match whose kanji.script is
    in script_scope; otherwise (or if nothing matches script_scope) prefers a
    public/system match over the viewer's own private one, as before.

    The alias-lookup query also requires the *joined kanji* to be visible, not just
    the alias row itself -- an alias can be made public while the kanji it names
    stays private (e.g. a user publishes just the name of their own private kanji),
    and callers like contributions.py's _visible_kanji_id() rely on this function as
    their sole visibility gate for write endpoints. Same bug class as the
    _resolve_parts_detail leak (2026-08-27) and the one _self_identity_kanji_ids
    already guards against; found unfixed here 2026-08-31 during an architecture
    review, confirmed exploitable via a rolled-back two-user test before fixing."""
    term = term.strip().lower()
    row = conn.execute(
        "SELECT id FROM kanji WHERE id = ? AND (visibility = 'public' OR owner_id = ?)",
        (term, viewer_id)
    ).fetchone()
    if row:
        return row["id"]
    rows = conn.execute(
        "SELECT a.kanji_id, a.visibility, k.script FROM aliases a "
        "JOIN kanji k ON k.id = a.kanji_id "
        "WHERE a.alias = ? AND (a.visibility = 'public' OR a.owner_id = ?) "
        "AND (k.visibility = 'public' OR k.owner_id = ?)",
        (term, viewer_id, viewer_id)
    ).fetchall()
    if not rows:
        return None
    if script_scope:
        scoped = [r for r in rows if r["script"] in script_scope]
        if scoped:
            rows = scoped
    for r in rows:
        if r["visibility"] == "public":
            return r["kanji_id"]
    return rows[0]["kanji_id"]


def _self_identity_kanji_ids(conn, term: str, viewer_id: int | None,
                              script_scope: tuple[str, ...] | None) -> set[str]:
    """Every kanji id that `term` itself names — by id or by alias — visible to
    viewer_id. Unlike resolve_alias (which collapses an ambiguous term to a single
    canonical id, e.g. for decomposition-graph expansion), this returns *all* matches:
    a term ambiguous across scripts (like '族', matching both rtk1307 and hanzi-65cf)
    must self-identity-match every one of them, not just whichever one resolve_alias
    happened to pick, or an unfiltered ('All scripts') search silently drops half.

    The alias lookup checks both the alias's own visibility and the joined kanji's —
    an alias row can be public while the kanji it names is still private (e.g. a user
    makes their own private kanji's name public without making the kanji itself
    public), same class of gap as the _resolve_parts_detail leak found 2026-08-27;
    found and closed here 2026-08-27 in the audit that followed it (see
    docs/2026-08-search-quality-audit.md)."""
    term = term.strip().lower()
    row = conn.execute(
        "SELECT id FROM kanji WHERE id = ? AND (visibility = 'public' OR owner_id = ?)",
        (term, viewer_id)
    ).fetchone()
    if row:
        return {row["id"]}
    rows = conn.execute(
        "SELECT a.kanji_id, k.script FROM aliases a "
        "JOIN kanji k ON k.id = a.kanji_id "
        "WHERE a.alias = ? AND (a.visibility = 'public' OR a.owner_id = ?) "
        "AND (k.visibility = 'public' OR k.owner_id = ?)",
        (term, viewer_id, viewer_id)
    ).fetchall()
    if script_scope:
        scoped = [r for r in rows if r["script"] in script_scope]
        if scoped:
            rows = scoped
    return {r["kanji_id"] for r in rows}


def get_all_aliases_for_term(conn, term: str, viewer_id: int | None = None,
                              script_scope: tuple[str, ...] | None = None) -> set[str]:
    """Return the full visible alias set for a primitive (for parts-table matching)."""
    term = term.strip().lower()
    cid = resolve_alias(conn, term, viewer_id, script_scope)
    if not cid:
        return {term}
    rows = conn.execute(
        "SELECT alias FROM aliases WHERE kanji_id = ? AND (visibility = 'public' OR owner_id = ?)",
        (cid, viewer_id)
    ).fetchall()
    return {r["alias"] for r in rows} | {term, cid}


def _kanji_with_part_terms(conn, terms: set[str], viewer_id: int | None,
                            sources: set[str] | None) -> set[str]:
    """kanji ids that directly list any of `terms` as a part_term, in ANY decomposition
    visible to the viewer (not just one picked one) — one layer of the reverse
    decomposition graph used by _reachable_kanji_for_term below. Also checks the
    listing kanji's own visibility, not just the decomposition's — a decomposition
    can be public while the kanji it belongs to is still private (found alongside
    the _self_identity_kanji_ids gap, 2026-08-27)."""
    if not terms:
        return set()
    decomp_source_sql, decomp_source_params = _source_scope_sql("d.", sources, viewer_id)
    decomp_extra = f" AND {decomp_source_sql}" if decomp_source_sql else ""
    ph = ",".join("?" * len(terms))
    rows = conn.execute(
        f"SELECT DISTINCT p.kanji_id FROM parts p "
        f"JOIN decompositions d ON d.id = p.decomposition_id "
        f"JOIN kanji k ON k.id = p.kanji_id "
        f"WHERE p.part_term IN ({ph}) AND (d.visibility = 'public' OR d.owner_id = ?){decomp_extra} "
        f"AND (k.visibility = 'public' OR k.owner_id = ?)",
        [*terms, viewer_id, *decomp_source_params, viewer_id]
    ).fetchall()
    return {r["kanji_id"] for r in rows}


def _terms_for_kanji_ids(conn, kanji_ids: set[str], viewer_id: int | None) -> set[str]:
    """Every alias string, id, and character for the given kanji ids (public, or the
    viewer's own) — i.e. every literal part_term string that could name one of these
    kanji as a part, feeding the next BFS layer of _reachable_kanji_for_term."""
    if not kanji_ids:
        return set()
    ph = ",".join("?" * len(kanji_ids))
    result = set(kanji_ids)
    for r in conn.execute(
        f"SELECT alias FROM aliases WHERE kanji_id IN ({ph}) AND (visibility = 'public' OR owner_id = ?)",
        [*kanji_ids, viewer_id]
    ).fetchall():
        result.add(r["alias"])
    for r in conn.execute(
        f"SELECT character FROM kanji WHERE id IN ({ph}) AND (visibility = 'public' OR owner_id = ?)",
        [*kanji_ids, viewer_id]
    ).fetchall():
        if r["character"]:
            result.add(r["character"])
    return result


def _reachable_kanji_for_term(conn, term: str, viewer_id: int | None,
                               script_scope: tuple[str, ...] | None,
                               sources: set[str] | None, max_depth: int) -> set[str]:
    """All kanji ids where `term` is present anywhere in the decomposition tree —
    directly, or nested inside any alternative decomposition of any part, up to
    `max_depth` levels deep (same cycle-safety as the detail view's recursive
    resolution: each BFS layer only ever adds kanji not already found, so a cycle just
    stops contributing new terms rather than looping). `max_depth=1` is a direct match
    only (the term must appear literally in a decomposition of the kanji itself) —
    every depth beyond that also matches a part's part, recursively. Considers *every*
    visible decomposition at each level, not just one picked one — a kanji reachable
    via any alternative decomposition of any ancestor counts. Self-identity (a kanji
    "is made of" itself) is included via every kanji the term itself names — not just
    resolve_alias's single canonical pick, so a term ambiguous across scripts (e.g.
    '族', matching both an rtk row and a hanzi row) self-matches all of them — and is
    independent of max_depth."""
    matched = _self_identity_kanji_ids(conn, term, viewer_id, script_scope)

    frontier_terms = get_all_aliases_for_term(conn, term, viewer_id, script_scope)
    found_kanji: set[str] = set()
    depth = 0
    while frontier_terms and depth < max_depth:
        new_kanji = _kanji_with_part_terms(conn, frontier_terms, viewer_id, sources) - found_kanji
        if not new_kanji:
            break
        found_kanji |= new_kanji
        frontier_terms = _terms_for_kanji_ids(conn, new_kanji, viewer_id)
        depth += 1
    return matched | found_kanji


def search_by_parts(conn, part_names: list[str], viewer_id: int | None = None,
                     script: str | None = None, sources: set[str] | None = None,
                     depth: int = 1) -> list[dict]:
    """Find kanji containing ALL given primitives. A primitive counts as present if it's
    reachable within `depth` levels of a kanji's decomposition tree — directly (depth=1,
    the historical/default behavior: the term must appear in a decomposition of the
    kanji itself, in any alternative decomposition — a kanji taught two different ways
    matches via either), or, for depth > 1, nested inside any alternative decomposition
    of any of its parts, recursively (so e.g. at depth=3, searching "corpse" also finds
    壁, because 壁 -> 辟 -> 尸/corpse, even though 壁's own parts list never literally says
    "corpse") — see _reachable_kanji_for_term. This is a real, deliberate trade-off, not
    a bug: a very common primitive's reachable set can grow to a large fraction of the
    whole dataset at high depth (e.g. "mouth" reaches ~65% of rtk kanji at depth=5) — the
    caller (UI) is expected to expose depth as a user choice rather than silently
    defaulting to the broadest setting. A term is also trivially satisfied by self-
    identity: a kanji "is made of" itself, so e.g. searching ["weep", "water"] must
    still return 'weep' even though 'weep' doesn't literally list itself as one of its
    own parts — only 'water' (+ something else) does, independent of depth.
    script (one of SCRIPT_VISIBILITY's keys) scopes both which kanji are returned and,
    for terms ambiguous across scripts, which alias set they expand to. sources (a subset
    of SOURCE_SCOPES) restricts both which kanji can be returned and which decompositions
    are consulted for matching (at every depth) to the selected contributor scope(s) — it
    does NOT restrict which alias terms resolve (get_all_aliases_for_term is source-
    agnostic), so a primitive name contributed by an excluded source can still be typed
    to search, it just won't match via a decomposition from that source."""
    terms = [p.strip().lower() for p in part_names if p.strip()]
    if not terms:
        return []

    depth = max(1, min(depth, MAX_DECOMPOSITION_DEPTH))
    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    matched_sets = [
        _reachable_kanji_for_term(conn, t, viewer_id, script_scope, sources, depth) for t in terms
    ]
    candidate_ids = set.intersection(*matched_sets) if matched_sets else set()
    if not candidate_ids:
        return []

    kanji_source_sql, kanji_source_params = _source_scope_sql("k.", sources, viewer_id)
    conditions = ["(k.visibility = 'public' OR k.owner_id = ?)"]
    params = [viewer_id]
    if kanji_source_sql:
        conditions.append(kanji_source_sql)
        params.extend(kanji_source_params)
    if script_scope:
        conditions.append(f"k.script IN ({','.join('?' * len(script_scope))})")
        params.extend(script_scope)

    # Filtered in Python against candidate_ids rather than a SQL "id IN (...)" clause —
    # a very common primitive's reachable set can run into the thousands now that search
    # walks the full decomposition tree, and SQLite's bound-parameter limit is a real risk
    # at that size. A full table scan of ~23k kanji rows is still cheap at this scale.
    sql = (
        f"SELECT id, character, keyword, frame, stroke_count, jlpt, image_url FROM kanji k "
        f"WHERE {' AND '.join(conditions)} ORDER BY frame NULLS LAST"
    )
    rows = [r for r in conn.execute(sql, params).fetchall() if r["id"] in candidate_ids]
    return _rows_to_dicts(conn, rows, viewer_id)


def search_by_substring(conn, substring: str, viewer_id: int | None = None,
                         script: str | None = None, sources: set[str] | None = None) -> list[dict]:
    """Find kanji whose id, keyword, or any visible alias contains the term as a whole
    word — not an arbitrary substring ("hat" matches "hat"/"hat trick"/"bright hat" but
    not "chatter", "what", or "hate"). Keywords/aliases can be comma-separated synonym
    lists (e.g. "hate, detest, abhor"), so commas are normalised to spaces before the
    word-boundary check, alongside the string's own start/end. sources (a subset of
    SOURCE_SCOPES) restricts results to kanji owned within the selected contributor
    scope(s), regardless of whether the match itself came from the id/keyword or an
    alias — the alias's own owner isn't considered separately."""
    sub = substring.strip().lower()
    word = f"% {sub} %"
    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    script_cond = ""
    script_params: list[str] = []
    if script_scope:
        script_cond = f" AND k.script IN ({','.join('?' * len(script_scope))})"
        script_params = list(script_scope)
    source_sql, source_params = _source_scope_sql("k.", sources, viewer_id)
    source_cond = f" AND {source_sql}" if source_sql else ""
    id_bounded = "(' ' || k.id || ' ')"
    keyword_bounded = "(' ' || REPLACE(k.keyword, ',', ' ') || ' ')"
    alias_bounded = "(' ' || REPLACE(a.alias, ',', ' ') || ' ')"
    rows = conn.execute(
        f"""
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt, k.image_url
        FROM kanji k
        WHERE ({id_bounded} LIKE ? OR {keyword_bounded} LIKE ?)
              AND (k.visibility = 'public' OR k.owner_id = ?){script_cond}{source_cond}
        UNION
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt, k.image_url
        FROM kanji k
        JOIN aliases a ON a.kanji_id = k.id
        WHERE {alias_bounded} LIKE ? AND (a.visibility = 'public' OR a.owner_id = ?)
              AND (k.visibility = 'public' OR k.owner_id = ?){script_cond}{source_cond}
        ORDER BY frame NULLS LAST
        """,
        (word, word, viewer_id, *script_params, *source_params,
         word, viewer_id, viewer_id, *script_params, *source_params)
    ).fetchall()
    return _rows_to_dicts(conn, rows, viewer_id)


def search_by_char(conn, character: str, viewer_id: int | None = None,
                    script: str | None = None, sources: set[str] | None = None) -> dict | None:
    """Find a kanji by its character glyph. A user's own private duplicate of an
    existing public glyph (if any) takes precedence over the public one for that user.
    sources (a subset of SOURCE_SCOPES) restricts matches to the selected contributor
    scope(s), same semantics as search_by_substring."""
    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    script_cond = ""
    params: list = [character, viewer_id]
    if script_scope:
        script_cond = f" AND script IN ({','.join('?' * len(script_scope))})"
        params.extend(script_scope)
    source_sql, source_params = _source_scope_sql("", sources, viewer_id)
    source_cond = f" AND {source_sql}" if source_sql else ""
    params.extend(source_params)
    rows = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt, image_url, owner_id FROM kanji "
        f"WHERE character = ? AND (visibility = 'public' OR owner_id = ?){script_cond}{source_cond}",
        params
    ).fetchall()
    if not rows:
        return None
    row = next((r for r in rows if viewer_id is not None and r["owner_id"] == viewer_id), rows[0])
    return _rows_to_dicts(conn, [row], viewer_id)[0]


def get_kanji_detail(conn, kanji_id: str, viewer_id: int | None = None,
                      sources: set[str] | None = None) -> dict | None:
    """
    Return full detail for one kanji: the canonical entry plus every decomposition,
    alias, and story visible to the viewer (system + public + the viewer's own private),
    each tagged with its owner. A kanji can have contributions from multiple owners, so
    this is owner-grouped rather than the old flat single-decomposition shape.

    `sources` (a subset of SOURCE_SCOPES, e.g. {"system", "mine"}) restricts which
    decompositions are offered as tabs, and which decomposition is used at every level
    of the recursive part breakdown (see _resolve_parts_detail) — same semantics as
    search's `sources` filter. None means no restriction. Aliases/stories are source-
    agnostic, same as search.
    """
    cid = resolve_alias(conn, kanji_id, viewer_id)
    if not cid:
        return None
    row = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt, image_url, script, variant_of, owner_id "
        "FROM kanji WHERE id = ? AND (visibility = 'public' OR owner_id = ?)",
        (cid, viewer_id)
    ).fetchone()
    if not row:
        return None

    entry = {
        "id": row["id"], "character": row["character"], "keyword": row["keyword"],
        "frame": row["frame"], "stroke_count": row["stroke_count"], "jlpt": row["jlpt"],
        "image_url": row["image_url"],
        "script": row["script"], "variant_of": row["variant_of"],
        "is_system": row["owner_id"] == 1,
        "is_mine": viewer_id is not None and row["owner_id"] == viewer_id,
    }

    entry["aliases"] = [
        {
            "id": r["id"], "alias": r["alias"], "owner": r["username"],
            "is_mine": viewer_id is not None and r["owner_id"] == viewer_id,
            "visibility": r["visibility"],
        }
        for r in conn.execute(
            "SELECT a.id, a.alias, a.owner_id, a.visibility, u.username FROM aliases a "
            "JOIN users u ON u.id = a.owner_id "
            "WHERE a.kanji_id = ? AND (a.visibility = 'public' OR a.owner_id = ?) "
            "ORDER BY (a.owner_id = 1) DESC, a.id",
            (cid, viewer_id)
        ).fetchall()
    ]

    decomp_rows = _list_decompositions(conn, cid, viewer_id, sources)
    decomp_ids = [d["id"] for d in decomp_rows]
    my_reviews = _reviews_for_decompositions(conn, decomp_ids, viewer_id) if viewer_id else {}
    entry["decompositions"] = [
        {
            "id": d["id"], "owner": d["username"],
            "is_mine": viewer_id is not None and d["owner_id"] == viewer_id,
            "visibility": d["visibility"], "label": d["label"],
            "parts_detail": _resolve_parts_detail(conn, cid, d["id"], viewer_id, sources, frozenset({cid})),
            "my_review": my_reviews.get(d["id"]),
        }
        for d in decomp_rows
    ]

    entry["stories"] = [
        {
            "id": s["id"], "owner": s["username"],
            "is_mine": viewer_id is not None and s["owner_id"] == viewer_id,
            "visibility": s["visibility"], "story": s["story"],
        }
        for s in conn.execute(
            "SELECT s.id, s.owner_id, s.visibility, s.story, u.username FROM stories s "
            "JOIN users u ON u.id = s.owner_id "
            "WHERE s.kanji_id = ? AND (s.visibility = 'public' OR s.owner_id = ?) "
            "ORDER BY (s.owner_id = 1) DESC, s.id",
            (cid, viewer_id)
        ).fetchall()
    ]

    return entry


def _reviews_for_decompositions(conn, decomposition_ids: list[int], reviewer_id: int) -> dict:
    """decomposition_id -> this reviewer's own verdict ('approved'/'disputed'), for
    however many of `decomposition_ids` they've already reviewed. Batched, not N+1."""
    if not decomposition_ids:
        return {}
    placeholders = ",".join("?" for _ in decomposition_ids)
    rows = conn.execute(
        f"SELECT decomposition_id, verdict FROM decomposition_reviews "
        f"WHERE reviewer_id = ? AND decomposition_id IN ({placeholders})",
        [reviewer_id] + decomposition_ids
    ).fetchall()
    return {r["decomposition_id"]: r["verdict"] for r in rows}


def set_decomposition_review(conn, decomposition_id: int, reviewer_id: int, verdict: str) -> dict:
    """Record (or change) a reviewer's approve/dispute verdict on one decomposition —
    the UI-facing counterpart to this audit's render-and-compare verification method.
    One row per (decomposition, reviewer): re-clicking the other button updates the
    existing row (and clears any prior processed_at, since a changed verdict needs
    re-triage) rather than accumulating duplicates."""
    if verdict not in ("approved", "disputed"):
        raise ValueError(f"invalid verdict: {verdict!r}")
    row = conn.execute(
        "SELECT id, kanji_id FROM decompositions WHERE id = ? "
        "AND (visibility = 'public' OR owner_id = ?)",
        (decomposition_id, reviewer_id)
    ).fetchone()
    if not row:
        raise ValueError(f"no such decomposition: {decomposition_id}")
    conn.execute(
        "INSERT INTO decomposition_reviews (decomposition_id, kanji_id, verdict, reviewer_id) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(decomposition_id, reviewer_id) DO UPDATE SET "
        "  verdict = excluded.verdict, created_at = datetime('now'), processed_at = NULL",
        (decomposition_id, row["kanji_id"], verdict, reviewer_id)
    )
    conn.commit()
    return {"decomposition_id": decomposition_id, "verdict": verdict}


def get_review_queue(conn, verdict: str | None = None, only_unprocessed: bool = True) -> list[dict]:
    """Every review row, for the maintainer-facing sweep (review_queue.py) that turns
    approved reviews into pinned regression tests and disputed ones into investigation
    items, then marks them processed. Not exposed to end users — no viewer-scoping,
    this is audit tooling, not a search/detail endpoint."""
    clauses, params = [], []
    if verdict:
        clauses.append("r.verdict = ?")
        params.append(verdict)
    if only_unprocessed:
        clauses.append("r.processed_at IS NULL")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT r.id, r.decomposition_id, r.kanji_id, r.verdict, r.created_at, "
        f"       k.character, k.keyword, u.username AS reviewer "
        f"FROM decomposition_reviews r "
        f"JOIN kanji k ON k.id = r.kanji_id "
        f"JOIN users u ON u.id = r.reviewer_id "
        f"{where} ORDER BY r.created_at",
        params
    ).fetchall()
    return [dict(r) for r in rows]


def mark_reviews_processed(conn, review_ids: list[int]) -> None:
    """Clear processed rows out of the pending queue after a maintainer has acted on
    them (added a regression pin for an approval, investigated a dispute) — this is
    the "после обработки этого список очистить" step. Keeps the row (with
    processed_at set) rather than deleting, so there's still an audit trail of what
    was reviewed and when."""
    if not review_ids:
        return
    placeholders = ",".join("?" for _ in review_ids)
    conn.execute(
        f"UPDATE decomposition_reviews SET processed_at = datetime('now') "
        f"WHERE id IN ({placeholders})",
        review_ids
    )
    conn.commit()


def _list_decompositions(conn, kanji_id: str, viewer_id: int | None, sources: set[str] | None):
    """Every decomposition visible for kanji_id (system decomposition first, then by id),
    scoped by `sources` same as everywhere else. Shared by get_kanji_detail (top level)
    and _resolve_parts_detail (nested parts) so both show *all* alternative
    decompositions, not just one picked one — a kanji taught two different ways (e.g. a
    system decomposition plus a user's own) shows both, all the way down the tree."""
    source_sql, source_params = _source_scope_sql("d.", sources, viewer_id)
    decomp_extra = f" AND {source_sql}" if source_sql else ""
    return conn.execute(
        "SELECT d.id, d.owner_id, d.visibility, d.label, u.username FROM decompositions d "
        "JOIN users u ON u.id = d.owner_id "
        f"WHERE d.kanji_id = ? AND (d.visibility = 'public' OR d.owner_id = ?){decomp_extra} "
        "ORDER BY (d.owner_id = 1) DESC, d.id",
        [kanji_id, viewer_id] + source_params
    ).fetchall()


def _resolve_parts_detail(conn, cid: str, decomposition_id: int, viewer_id: int | None = None,
                           sources: set[str] | None = None, _ancestors: frozenset = frozenset(),
                           _depth: int = 0) -> list[dict]:
    """Resolve one decomposition's part terms to their kanji rows (batched, not N*3).
    A part term shared across scripts (e.g. '一' as both an rtk row and a hanzi row)
    is resolved within the same script group as the kanji it's a part of (cid), not
    an arbitrary one — see _script_group / SCRIPT_VISIBILITY.

    Recurses into each resolved part's own decomposition(s) (query-time hierarchy, not
    flattened at import), so e.g. 懸's "prefecture" part also carries prefecture's own
    "eye + little" breakdown as `sub_decompositions`, rather than only ever showing the
    fully flattened primitive list. A part with more than one visible decomposition
    (e.g. a system one and a user's own alternate) carries *all* of them, each resolved
    the same way — not just one picked one, all the way down the tree; the UI renders
    each as its own line, same as the top-level decompositions list in get_kanji_detail.
    `sources` scopes which decompositions are visible at every level (not just the
    top), same semantics as search's SOURCE_SCOPES. Bounded by MAX_DECOMPOSITION_DEPTH
    and an ancestor-chain cycle guard (`_ancestors`) — a part whose own decomposition
    would revisit a kanji already on the path from the root is left atomic
    (`sub_decompositions: []`) rather than recursing forever."""
    part_terms = [
        r["part_term"] for r in conn.execute(
            "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position",
            (decomposition_id,)
        ).fetchall()
    ]
    if not part_terms:
        return []

    parent = conn.execute("SELECT script FROM kanji WHERE id = ?", (cid,)).fetchone()
    parent_group = _script_group(parent["script"]) if parent else None

    # A literal-character part term (e.g. '宀') was stored alongside a synthetic
    # second row for that character's own keyword ('roof') by expand_part_terms at
    # import time, so search can match on either. For *display*, showing both as
    # separate chips is at best redundant (same kanji twice) and at worst actively
    # wrong: if that keyword happens to collide with a different kanji's own alias
    # (e.g. 屋/rtk1138 is *also* officially keyworded "roof" in the 6th-ed CSV — a
    # genuine Heisig naming collision, not a data bug), the synthetic term resolves
    # to that unrelated kanji instead, injecting a bogus extra chip (see
    # docs/2026-08-search-quality-audit.md, session 18). Recompute exactly which
    # positions expand_part_terms would have synthesized, using the same char/
    # keyword lookup and script_group preference, and drop them here — search
    # (_kanji_with_part_terms etc.) reads the same stored rows independently and is
    # unaffected.
    char_to_candidates, id_to_keyword = _build_char_lookup(conn)
    synthetic_positions: set[int] = set()
    for i, term in enumerate(part_terms[:-1]):
        candidates = char_to_candidates.get(term)
        if not candidates:
            continue
        chosen_id = None
        if parent_group:
            chosen_id = next((kid for kid, script in candidates if _script_group(script) == parent_group), None)
        if chosen_id is None:
            chosen_id = candidates[0][0]
        kw = id_to_keyword.get(chosen_id)
        if kw and part_terms[i + 1] == kw:
            synthetic_positions.add(i + 1)
    if synthetic_positions:
        part_terms = [t for i, t in enumerate(part_terms) if i not in synthetic_positions]

    # Every candidate lookup below is scoped to (visible = public OR owned by viewer_id),
    # matching the pattern every other read function in this module follows (see the
    # module-level "Visibility model" note) -- these two queries used to be the one
    # exception, unscoped by viewer_id entirely, so a decomposition part term could
    # resolve through a *different* user's private alias/kanji and leak its character/
    # keyword into a display anyone could see (found 2026-08-27 while wiring up a new
    # primitive whose name collided with the viewer's own private one -- see
    # docs/2026-08-search-quality-audit.md).
    ph = ",".join("?" * len(part_terms))
    term_to_id: dict[str, str] = {}
    for r in conn.execute(
        f"SELECT id FROM kanji WHERE id IN ({ph}) AND (visibility = 'public' OR owner_id = ?)",
        part_terms + [viewer_id]
    ).fetchall():
        term_to_id[r["id"]] = r["id"]

    alias_candidates: dict[str, list[tuple[str, str, str]]] = {}
    for r in conn.execute(
        f"SELECT a.alias, a.kanji_id, a.visibility, k.script FROM aliases a "
        f"JOIN kanji k ON k.id = a.kanji_id "
        f"WHERE a.alias IN ({ph}) AND (a.visibility = 'public' OR a.owner_id = ?) "
        f"AND (k.visibility = 'public' OR k.owner_id = ?)",
        part_terms + [viewer_id, viewer_id]
    ).fetchall():
        alias_candidates.setdefault(r["alias"], []).append((r["kanji_id"], r["visibility"], r["script"]))

    for term, candidates in alias_candidates.items():
        if term in term_to_id:
            continue
        pool = candidates
        if parent_group:
            scoped = [c for c in pool if _script_group(c[2]) == parent_group]
            if scoped:
                pool = scoped
        # Prefer a public match over the viewer's own private one when both are still
        # in the running, same tiebreak resolve_alias uses -- otherwise which one wins
        # depends on arbitrary SQL row order.
        preferred = next((kid for kid, visibility, _ in pool if visibility == "public"), None)
        term_to_id[term] = preferred or pool[0][0]

    resolved_ids = list({term_to_id[t] for t in part_terms if t in term_to_id and term_to_id[t] != cid})
    if not resolved_ids:
        return []

    ph2 = ",".join("?" * len(resolved_ids))
    prow_map = {
        r["id"]: r for r in conn.execute(
            f"SELECT id, character, keyword, frame, image_url FROM kanji "
            f"WHERE id IN ({ph2}) AND (visibility = 'public' OR owner_id = ?)",
            resolved_ids + [viewer_id]
        ).fetchall()
    }

    seen_ids: set[str] = set()
    resolved = []
    for term in part_terms:
        pid = term_to_id.get(term)
        if pid and pid != cid and pid not in seen_ids:
            seen_ids.add(pid)
            prow = prow_map.get(pid)
            if prow:
                sub_decompositions = []
                if _depth < MAX_DECOMPOSITION_DEPTH and pid not in _ancestors:
                    for sd in _list_decompositions(conn, pid, viewer_id, sources):
                        sub_decompositions.append({
                            "id": sd["id"], "label": sd["label"], "owner": sd["username"],
                            "parts": _resolve_parts_detail(
                                conn, pid, sd["id"], viewer_id, sources,
                                _ancestors | {cid}, _depth + 1
                            ),
                        })
                resolved.append({
                    "id": prow["id"],
                    "character": prow["character"],
                    "keyword": prow["keyword"],
                    "frame": prow["frame"],
                    "image_url": prow["image_url"],
                    "term": term,
                    "sub_decompositions": sub_decompositions,
                })
    return resolved


def _rows_to_dicts(conn, rows, viewer_id: int | None = None) -> list[dict]:
    """Convert a list of kanji rows to dicts (for search-result cards), batching alias
    and parts lookups. Only aliases/parts visible to viewer_id are included."""
    if not rows:
        return []
    kids = [r["id"] for r in rows]
    ph = ",".join("?" * len(kids))

    alias_map: dict[str, list[str]] = {k: [] for k in kids}
    for r in conn.execute(
        f"SELECT kanji_id, alias FROM aliases WHERE kanji_id IN ({ph}) "
        f"AND (visibility = 'public' OR owner_id = ?) ORDER BY id",
        kids + [viewer_id]
    ).fetchall():
        alias_map[r["kanji_id"]].append(r["alias"])

    parts_map: dict[str, list[str]] = {k: [] for k in kids}
    seen: dict[str, set[str]] = {k: set() for k in kids}
    for r in conn.execute(
        f"SELECT p.kanji_id, p.part_term FROM parts p "
        f"JOIN decompositions d ON d.id = p.decomposition_id "
        f"WHERE p.kanji_id IN ({ph}) AND (d.visibility = 'public' OR d.owner_id = ?) "
        f"ORDER BY p.position",
        kids + [viewer_id]
    ).fetchall():
        kid, term = r["kanji_id"], r["part_term"]
        if term not in seen[kid]:
            seen[kid].add(term)
            parts_map[kid].append(term)

    return [
        {
            "id": r["id"],
            "character": r["character"],
            "keyword": r["keyword"],
            "frame": r["frame"],
            "stroke_count": r["stroke_count"],
            "jlpt": r["jlpt"],
            "image_url": r["image_url"],
            "aliases": alias_map[r["id"]],
            "parts": parts_map[r["id"]],
        }
        for r in rows
    ]


# ── User contributions (writes) ─────────────────────────────────────────────
# Everything here is invoked only behind auth (see auth.require_user) and always
# writes an explicit owner_id — never system (id=1), which stays immutable to
# normal users by construction (nothing here lets owner_id be set to 1).

def next_user_entry_id(conn) -> str:
    """Collision-free id for a new user-created kanji/primitive entry: usr{n}, n from
    a dedicated AUTOINCREMENT counter (SQLite never reuses AUTOINCREMENT ids)."""
    cur = conn.execute("INSERT INTO user_entry_seq DEFAULT VALUES")
    conn.commit()
    return f"usr{cur.lastrowid}"


def create_kanji_entry(conn, owner_id: int, keyword: str, character: str | None,
                        script: str, visibility: str) -> str:
    new_id = next_user_entry_id(conn)
    keyword = keyword.strip().lower()
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, character or None, keyword, owner_id, visibility, script)
    )
    _insert_alias(conn, new_id, keyword, owner_id, visibility)
    conn.commit()
    return new_id


def create_decomposition(conn, kanji_id: str, owner_id: int, parts: list[str],
                          label: str | None, visibility: str) -> int:
    terms = [p.strip().lower() for p in parts if p.strip()]
    parent = conn.execute("SELECT script FROM kanji WHERE id = ?", (kanji_id,)).fetchone()
    script_group = _script_group(parent["script"]) if parent else None
    expanded_terms = expand_part_terms(conn, terms, script_group=script_group)
    cur = conn.execute(
        "INSERT INTO decompositions (kanji_id, owner_id, visibility, label) VALUES (?, ?, ?, ?)",
        (kanji_id, owner_id, visibility, label)
    )
    decomposition_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
        [(kanji_id, term, pos, decomposition_id) for pos, term in enumerate(expanded_terms)]
    )
    conn.commit()
    return decomposition_id


def create_alias(conn, kanji_id: str, owner_id: int, alias: str, visibility: str):
    _insert_alias(conn, kanji_id, alias, owner_id, visibility)
    conn.commit()


def upsert_story(conn, kanji_id: str, owner_id: int, story: str, visibility: str) -> int:
    """One editable story per (kanji, owner) — resubmitting updates it in place."""
    conn.execute(
        """INSERT INTO stories (kanji_id, owner_id, story, visibility, updated_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(kanji_id, owner_id) DO UPDATE SET
             story = excluded.story, visibility = excluded.visibility, updated_at = datetime('now')""",
        (kanji_id, owner_id, story, visibility)
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM stories WHERE kanji_id = ? AND owner_id = ?", (kanji_id, owner_id)
    ).fetchone()
    return row["id"]


def set_visibility(conn, table: str, row_id: int | str, owner_id: int, visibility: str) -> bool:
    """
    Owner-only visibility toggle for kanji/aliases/decompositions/stories. Returns False
    if the row doesn't exist or isn't owned by owner_id — including system rows
    (owner_id=1), which no normal user ever owns, so this doubles as the "system rows
    are immutable to normal users" guard with no separate check needed.
    """
    if table not in ("kanji", "aliases", "decompositions", "stories"):
        raise ValueError(f"invalid table: {table}")
    cur = conn.execute(
        f"UPDATE {table} SET visibility = ? WHERE id = ? AND owner_id = ? AND owner_id != 1",
        (visibility, row_id, owner_id)
    )
    conn.commit()
    return cur.rowcount > 0


def set_kanji_image(conn, kanji_id: str, owner_id: int, image_url: str,
                    commit: bool = True) -> bool:
    """Owner-only image attach/replace for a kanji with no real Unicode glyph. Same
    owner_id != 1 guard as set_visibility — system rows are immutable to normal users."""
    cur = conn.execute(
        "UPDATE kanji SET image_url = ? WHERE id = ? AND owner_id = ? AND owner_id != 1",
        (image_url, kanji_id, owner_id)
    )
    if commit:
        conn.commit()
    return cur.rowcount > 0


def get_my_contributions(conn, owner_id: int) -> dict:
    """Everything owned by this user across kanji/decompositions/aliases/stories."""
    kanji_rows = conn.execute(
        "SELECT id, character, keyword, visibility FROM kanji WHERE owner_id = ? ORDER BY id",
        (owner_id,)
    ).fetchall()
    decomp_rows = conn.execute(
        "SELECT d.id, d.kanji_id, d.visibility, d.label, k.keyword, k.character "
        "FROM decompositions d JOIN kanji k ON k.id = d.kanji_id "
        "WHERE d.owner_id = ? ORDER BY d.id",
        (owner_id,)
    ).fetchall()
    alias_rows = conn.execute(
        "SELECT a.id, a.kanji_id, a.alias, a.visibility, k.keyword, k.character "
        "FROM aliases a JOIN kanji k ON k.id = a.kanji_id "
        "WHERE a.owner_id = ? ORDER BY a.id",
        (owner_id,)
    ).fetchall()
    story_rows = conn.execute(
        "SELECT s.id, s.kanji_id, s.story, s.visibility, k.keyword, k.character "
        "FROM stories s JOIN kanji k ON k.id = s.kanji_id "
        "WHERE s.owner_id = ? ORDER BY s.id",
        (owner_id,)
    ).fetchall()
    return {
        "kanji": [dict(r) for r in kanji_rows],
        "decompositions": [dict(r) for r in decomp_rows],
        "aliases": [dict(r) for r in alias_rows],
        "stories": [dict(r) for r in story_rows],
    }
