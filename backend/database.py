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


def migrate_schema(conn):
    """
    Idempotent schema upgrades gated by PRAGMA user_version — safe to call on every
    startup, on both a fresh DB and an existing populated one. Each version's body is
    guarded by its own `if version < N` so re-running against a DB already past that
    version never re-issues a non-idempotent statement (e.g. a bare ALTER TABLE ADD
    COLUMN, which errors on a second run unlike CREATE TABLE IF NOT EXISTS).
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]

    if version < 1:
        _migrate_v1(conn)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        version = 1

    if version < 2:
        _migrate_v2(conn)
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
        version = 2


def _migrate_v1(conn):
    """"DB is a disposable cache" -> "DB is the source of truth": adds
    users/sessions/decompositions/stories tables and owner_id/visibility/script/
    variant_of columns on kanji/aliases/parts."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            username          TEXT NOT NULL UNIQUE,
            password_hash     TEXT,
            auth_provider     TEXT NOT NULL DEFAULT 'local',
            provider_user_id  TEXT,
            display_name      TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

        CREATE TABLE IF NOT EXISTS user_entry_seq (id INTEGER PRIMARY KEY AUTOINCREMENT);

        CREATE TABLE IF NOT EXISTS decompositions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            owner_id    INTEGER NOT NULL REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('public','private')),
            label       TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_decomp_kanji ON decompositions(kanji_id);
        CREATE INDEX IF NOT EXISTS idx_decomp_owner ON decompositions(owner_id);

        CREATE TABLE IF NOT EXISTS stories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            owner_id    INTEGER NOT NULL REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('public','private')),
            story       TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(kanji_id, owner_id)
        );
        CREATE INDEX IF NOT EXISTS idx_stories_kanji ON stories(kanji_id);
    """)

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
    conn.executescript("""
        ALTER TABLE kanji ADD COLUMN owner_id   INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE kanji ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private'));
        ALTER TABLE kanji ADD COLUMN script     TEXT NOT NULL DEFAULT 'ja-kanji' CHECK(script IN ('ja-kanji','zh-Hans','zh-Hant','zh-Hani'));
        ALTER TABLE kanji ADD COLUMN variant_of TEXT REFERENCES kanji(id);

        ALTER TABLE parts ADD COLUMN decomposition_id INTEGER REFERENCES decompositions(id);
    """)

    # aliases: relax UNIQUE(kanji_id, alias) -> UNIQUE(kanji_id, alias, owner_id) so two
    # different users can submit the same alias text. SQLite can't alter a UNIQUE
    # constraint in place, so rebuild the table.
    conn.executescript("""
        CREATE TABLE aliases_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kanji_id    TEXT NOT NULL REFERENCES kanji(id),
            alias       TEXT NOT NULL,
            owner_id    INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
            visibility  TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private')),
            UNIQUE(kanji_id, alias, owner_id)
        );
        INSERT INTO aliases_new (id, kanji_id, alias, owner_id, visibility)
            SELECT id, kanji_id, alias, 1, 'public' FROM aliases;
        DROP TABLE aliases;
        ALTER TABLE aliases_new RENAME TO aliases;
        CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
        CREATE INDEX IF NOT EXISTS idx_aliases_kanji ON aliases(kanji_id);
    """)

    _backfill_decompositions(conn)


def _migrate_v2(conn):
    """Adds per-account UI language and study-language (script) preferences."""
    conn.executescript("""
        ALTER TABLE users ADD COLUMN ui_language  TEXT NOT NULL DEFAULT 'en' CHECK(ui_language IN ('en','ru'));
        ALTER TABLE users ADD COLUMN study_script TEXT CHECK(study_script IN ('ja-kanji','zh-Hans','zh-Hant'));
    """)


def _backfill_decompositions(conn):
    """
    Ensure every kanji_id present in `parts` has a system decomposition row, and every
    parts row is linked to it. Idempotent — safe to call after migrate_schema() (upgrading
    a populated DB, where parts already has rows) and after import_data() (seeding a fresh
    DB, where parts gets populated only after migrate_schema() already ran).
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
    conn.commit()


def _load_parts_file(path: Path) -> dict[str, list[str]]:
    """Load {id: [part_terms]} from a data file. ASCII parts are lowercased; kanji chars kept as-is."""
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
            parts_str = cols[3].strip() if len(cols) > 3 else ""
            if not pid or not parts_str:
                continue
            raw = [p.strip() for p in parts_str.replace(";", ",").split(",") if p.strip()]
            normalised = [p.lower() if p.isascii() else p for p in raw]
            if normalised:
                result[pid] = normalised
    return result


def _build_char_lookup(conn) -> tuple[dict[str, str], dict[str, str]]:
    """Build (character -> kanji_id, kanji_id -> keyword) lookups for expand_part_terms."""
    char_to_db_id: dict[str, str] = {}
    for r in conn.execute("SELECT id, character FROM kanji WHERE character IS NOT NULL AND character != ''").fetchall():
        if r["character"] not in ("?", "??"):
            char_to_db_id[r["character"]] = r["id"]
    id_to_keyword: dict[str, str] = {
        r["id"]: r["keyword"]
        for r in conn.execute("SELECT id, keyword FROM kanji WHERE keyword IS NOT NULL").fetchall()
    }
    return char_to_db_id, id_to_keyword


def expand_part_terms(conn, terms: list[str], char_lookup: tuple[dict, dict] | None = None) -> list[str]:
    """
    If a part term is itself a kanji CHARACTER (rather than a primitive name), also
    include that character's keyword right after it, so keyword-based search matches
    without the contributor having to type both. char_lookup can be passed in (from
    _build_char_lookup) to avoid rebuilding it on every call in a bulk loop like
    import_data()'s; for a single one-off submission it's built fresh here, which is
    cheap at that scale.
    """
    char_to_db_id, id_to_keyword = char_lookup if char_lookup else _build_char_lookup(conn)
    expanded = []
    for term in terms:
        if term in char_to_db_id:
            expanded.append(term)
            kw = id_to_keyword.get(char_to_db_id[term])
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
        if not canonical or not parts:
            continue

        expanded_terms = expand_part_terms(conn, parts, char_lookup)

        conn.execute("DELETE FROM parts WHERE kanji_id = ?", (canonical,))
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
    public/system match over the viewer's own private one, as before."""
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
        "WHERE a.alias = ? AND (a.visibility = 'public' OR a.owner_id = ?)",
        (term, viewer_id)
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


def search_by_parts(conn, part_names: list[str], viewer_id: int | None = None,
                     script: str | None = None) -> list[dict]:
    """Find kanji containing ALL given primitives (flat set-intersection). A primitive
    counts as present if it appears in ANY decomposition visible to the viewer, not just
    the system one — once a user adds their own decomposition it participates in search too.
    script (one of SCRIPT_VISIBILITY's keys) scopes both which kanji are returned and,
    for terms ambiguous across scripts, which alias set they expand to."""
    terms = [p.strip().lower() for p in part_names if p.strip()]
    if not terms:
        return []

    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    alias_sets = [get_all_aliases_for_term(conn, t, viewer_id, script_scope) for t in terms]

    conditions = ["(k.visibility = 'public' OR k.owner_id = ?)"]
    params = [viewer_id]
    if script_scope:
        conditions.append(f"k.script IN ({','.join('?' * len(script_scope))})")
        params.extend(script_scope)
    for aliases in alias_sets:
        placeholders = ",".join("?" * len(aliases))
        conditions.append(
            "EXISTS (SELECT 1 FROM parts p JOIN decompositions d ON d.id = p.decomposition_id "
            f"WHERE p.kanji_id = k.id AND p.part_term IN ({placeholders}) "
            "AND (d.visibility = 'public' OR d.owner_id = ?))"
        )
        params.extend(aliases)
        params.append(viewer_id)

    sql = (
        f"SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji k "
        f"WHERE {' AND '.join(conditions)} ORDER BY frame NULLS LAST"
    )
    rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(conn, rows, viewer_id)


def search_by_substring(conn, substring: str, viewer_id: int | None = None,
                         script: str | None = None) -> list[dict]:
    """Find kanji whose id, keyword, or any visible alias contains the substring."""
    sub = substring.strip().lower()
    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    script_cond = ""
    script_params: list[str] = []
    if script_scope:
        script_cond = f" AND k.script IN ({','.join('?' * len(script_scope))})"
        script_params = list(script_scope)
    rows = conn.execute(
        f"""
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt
        FROM kanji k
        WHERE (k.id LIKE ? OR k.keyword LIKE ?) AND (k.visibility = 'public' OR k.owner_id = ?){script_cond}
        UNION
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt
        FROM kanji k
        JOIN aliases a ON a.kanji_id = k.id
        WHERE a.alias LIKE ? AND (a.visibility = 'public' OR a.owner_id = ?)
              AND (k.visibility = 'public' OR k.owner_id = ?){script_cond}
        ORDER BY frame NULLS LAST
        """,
        (f"%{sub}%", f"%{sub}%", viewer_id, *script_params,
         f"%{sub}%", viewer_id, viewer_id, *script_params)
    ).fetchall()
    return _rows_to_dicts(conn, rows, viewer_id)


def search_by_char(conn, character: str, viewer_id: int | None = None,
                    script: str | None = None) -> dict | None:
    """Find a kanji by its character glyph. A user's own private duplicate of an
    existing public glyph (if any) takes precedence over the public one for that user."""
    script_scope = SCRIPT_VISIBILITY.get(script) if script else None
    script_cond = ""
    params: list = [character, viewer_id]
    if script_scope:
        script_cond = f" AND script IN ({','.join('?' * len(script_scope))})"
        params.extend(script_scope)
    rows = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt, owner_id FROM kanji "
        f"WHERE character = ? AND (visibility = 'public' OR owner_id = ?){script_cond}",
        params
    ).fetchall()
    if not rows:
        return None
    row = next((r for r in rows if viewer_id is not None and r["owner_id"] == viewer_id), rows[0])
    return _rows_to_dicts(conn, [row], viewer_id)[0]


def get_kanji_detail(conn, kanji_id: str, viewer_id: int | None = None) -> dict | None:
    """
    Return full detail for one kanji: the canonical entry plus every decomposition,
    alias, and story visible to the viewer (system + public + the viewer's own private),
    each tagged with its owner. A kanji can have contributions from multiple owners, so
    this is owner-grouped rather than the old flat single-decomposition shape.
    """
    cid = resolve_alias(conn, kanji_id, viewer_id)
    if not cid:
        return None
    row = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt, script, variant_of, owner_id "
        "FROM kanji WHERE id = ? AND (visibility = 'public' OR owner_id = ?)",
        (cid, viewer_id)
    ).fetchone()
    if not row:
        return None

    entry = {
        "id": row["id"], "character": row["character"], "keyword": row["keyword"],
        "frame": row["frame"], "stroke_count": row["stroke_count"], "jlpt": row["jlpt"],
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

    decomp_rows = conn.execute(
        "SELECT d.id, d.owner_id, d.visibility, d.label, u.username FROM decompositions d "
        "JOIN users u ON u.id = d.owner_id "
        "WHERE d.kanji_id = ? AND (d.visibility = 'public' OR d.owner_id = ?) "
        "ORDER BY (d.owner_id = 1) DESC, d.id",
        (cid, viewer_id)
    ).fetchall()
    entry["decompositions"] = [
        {
            "id": d["id"], "owner": d["username"],
            "is_mine": viewer_id is not None and d["owner_id"] == viewer_id,
            "visibility": d["visibility"], "label": d["label"],
            "parts_detail": _resolve_parts_detail(conn, cid, d["id"]),
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


def _resolve_parts_detail(conn, cid: str, decomposition_id: int) -> list[dict]:
    """Resolve one decomposition's part terms to their kanji rows (batched, not N*3).
    A part term shared across scripts (e.g. '一' as both an rtk row and a hanzi row)
    is resolved within the same script group as the kanji it's a part of (cid), not
    an arbitrary one — see _script_group / SCRIPT_VISIBILITY."""
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

    ph = ",".join("?" * len(part_terms))
    term_to_id: dict[str, str] = {}
    for r in conn.execute(f"SELECT id FROM kanji WHERE id IN ({ph})", part_terms).fetchall():
        term_to_id[r["id"]] = r["id"]

    alias_candidates: dict[str, list[tuple[str, str]]] = {}
    for r in conn.execute(
        f"SELECT a.alias, a.kanji_id, k.script FROM aliases a "
        f"JOIN kanji k ON k.id = a.kanji_id WHERE a.alias IN ({ph})", part_terms
    ).fetchall():
        alias_candidates.setdefault(r["alias"], []).append((r["kanji_id"], r["script"]))

    for term, candidates in alias_candidates.items():
        if term in term_to_id:
            continue
        preferred = None
        if parent_group:
            preferred = next((kid for kid, script in candidates if _script_group(script) == parent_group), None)
        term_to_id[term] = preferred or candidates[0][0]

    resolved_ids = list({term_to_id[t] for t in part_terms if t in term_to_id and term_to_id[t] != cid})
    if not resolved_ids:
        return []

    ph2 = ",".join("?" * len(resolved_ids))
    prow_map = {
        r["id"]: r for r in conn.execute(
            f"SELECT id, character, keyword, frame FROM kanji WHERE id IN ({ph2})", resolved_ids
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
                resolved.append({
                    "id": prow["id"],
                    "character": prow["character"],
                    "keyword": prow["keyword"],
                    "frame": prow["frame"],
                    "term": term,
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
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, character or None, keyword.strip().lower(), owner_id, visibility, script)
    )
    conn.commit()
    return new_id


def create_decomposition(conn, kanji_id: str, owner_id: int, parts: list[str],
                          label: str | None, visibility: str) -> int:
    terms = [p.strip().lower() for p in parts if p.strip()]
    expanded_terms = expand_part_terms(conn, terms)
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
