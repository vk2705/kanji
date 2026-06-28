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


def import_data():
    """
    Import all RTK kanji from heisig-kanjis.csv, then overlay
    primitive definitions from data.txt (for missing chars / extra aliases).

    Component terms in the CSV are already fully expanded (all sub-levels
    included), so search is a simple flat set-intersection after alias expansion.
    """
    conn = get_db()
    conn.executescript("""
        DELETE FROM parts;
        DELETE FROM aliases;
        DELETE FROM kanji;
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
    char_to_db_id: dict[str, str] = {}
    for r in conn.execute("SELECT id, character FROM kanji WHERE character IS NOT NULL AND character != ''").fetchall():
        if r["character"] not in ("?", "??"):
            char_to_db_id[r["character"]] = r["id"]

    # Pre-build id→keyword to avoid a SELECT per kanji-char part in the loop.
    id_to_keyword: dict[str, str] = {
        r["id"]: r["keyword"]
        for r in conn.execute("SELECT id, keyword FROM kanji WHERE keyword IS NOT NULL").fetchall()
    }

    overrides_applied = 0
    for pid, parts in merged_parts_override.items():
        canonical = resolve_alias(conn, pid)
        if not canonical or not parts:
            continue

        expanded_terms = []
        for term in parts:
            if term in char_to_db_id:
                db_id = char_to_db_id[term]
                expanded_terms.append(term)
                kw = id_to_keyword.get(db_id)
                if kw:
                    expanded_terms.append(kw)
            else:
                expanded_terms.append(term)

        conn.execute("DELETE FROM parts WHERE kanji_id = ?", (canonical,))
        conn.executemany(
            "INSERT INTO parts (kanji_id, part_term, position) VALUES (?, ?, ?)",
            [(canonical, term, pos) for pos, term in enumerate(expanded_terms)]
        )
        overrides_applied += 1

    conn.commit()
    conn.close()
    print(f"Import complete: {len(rows_to_insert)} kanji rows, {overrides_applied} parts overrides applied "
          f"({len(pdf_parts)} from PDF, {len(parts_override)} from data.txt, "
          f"{len(pdf_parts) - len(set(pdf_parts) - set(parts_override))} PDF entries superseded by data.txt).")


def _insert_alias(conn, kanji_id: str, alias: str):
    alias = alias.strip().lower()
    if alias:
        conn.execute(
            "INSERT OR IGNORE INTO aliases (kanji_id, alias) VALUES (?, ?)",
            (kanji_id, alias)
        )


# ── Query helpers ─────────────────────────────────────────────────────────────

def resolve_alias(conn, term: str) -> str | None:
    """Return canonical kanji id for a term (alias or id)."""
    term = term.strip().lower()
    row = conn.execute("SELECT id FROM kanji WHERE id = ?", (term,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT kanji_id FROM aliases WHERE alias = ? LIMIT 1", (term,)
    ).fetchone()
    return row["kanji_id"] if row else None


def get_all_aliases_for_term(conn, term: str) -> set[str]:
    """Return the full alias set for a primitive (for parts-table matching)."""
    term = term.strip().lower()
    cid = resolve_alias(conn, term)
    if not cid:
        return {term}
    rows = conn.execute("SELECT alias FROM aliases WHERE kanji_id = ?", (cid,)).fetchall()
    return {r["alias"] for r in rows} | {term, cid}


def search_by_parts(conn, part_names: list[str]) -> list[dict]:
    """Find kanji containing ALL given primitives (flat set-intersection)."""
    terms = [p.strip().lower() for p in part_names if p.strip()]
    if not terms:
        return []

    alias_sets = [get_all_aliases_for_term(conn, t) for t in terms]

    conditions, params = [], []
    for aliases in alias_sets:
        placeholders = ",".join("?" * len(aliases))
        conditions.append(
            f"EXISTS (SELECT 1 FROM parts p WHERE p.kanji_id = k.id AND p.part_term IN ({placeholders}))"
        )
        params.extend(aliases)

    sql = (
        f"SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji k "
        f"WHERE {' AND '.join(conditions)} ORDER BY frame NULLS LAST"
    )
    rows = conn.execute(sql, params).fetchall()
    return _rows_to_dicts(conn, rows)


def search_by_substring(conn, substring: str) -> list[dict]:
    """Find kanji whose id, keyword, or any alias contains the substring."""
    sub = substring.strip().lower()
    rows = conn.execute(
        """
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt
        FROM kanji k
        WHERE k.id LIKE ? OR k.keyword LIKE ?
        UNION
        SELECT DISTINCT k.id, k.character, k.keyword, k.frame, k.stroke_count, k.jlpt
        FROM kanji k
        JOIN aliases a ON a.kanji_id = k.id
        WHERE a.alias LIKE ?
        ORDER BY frame NULLS LAST
        """,
        (f"%{sub}%", f"%{sub}%", f"%{sub}%")
    ).fetchall()
    return _rows_to_dicts(conn, rows)


def search_by_char(conn, character: str) -> dict | None:
    """Find a kanji by its character glyph."""
    row = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji WHERE character = ?",
        (character,)
    ).fetchone()
    return _rows_to_dicts(conn, [row])[0] if row else None


def get_kanji_detail(conn, kanji_id: str) -> dict | None:
    """Return full detail for one kanji, with resolved parts."""
    cid = resolve_alias(conn, kanji_id)
    if not cid:
        return None
    row = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji WHERE id = ?",
        (cid,)
    ).fetchone()
    if not row:
        return None
    entry = _rows_to_dicts(conn, [row])[0]

    part_terms = entry["parts"]
    if not part_terms:
        entry["parts_detail"] = []
        return entry

    # Batch-resolve all part terms in two queries instead of N*3.
    ph = ",".join("?" * len(part_terms))
    term_to_id: dict[str, str] = {}
    for r in conn.execute(f"SELECT id FROM kanji WHERE id IN ({ph})", part_terms).fetchall():
        term_to_id[r["id"]] = r["id"]
    for r in conn.execute(f"SELECT alias, kanji_id FROM aliases WHERE alias IN ({ph})", part_terms).fetchall():
        term_to_id.setdefault(r["alias"], r["kanji_id"])

    resolved_ids = list({term_to_id[t] for t in part_terms if t in term_to_id and term_to_id[t] != cid})
    if not resolved_ids:
        entry["parts_detail"] = []
        return entry

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

    entry["parts_detail"] = resolved
    return entry


def _row_to_dict(conn, row) -> dict:
    return _rows_to_dicts(conn, [row])[0]


def _rows_to_dicts(conn, rows) -> list[dict]:
    """Convert a list of kanji rows to dicts, batching alias and parts lookups."""
    if not rows:
        return []
    kids = [r["id"] for r in rows]
    ph = ",".join("?" * len(kids))

    alias_map: dict[str, list[str]] = {k: [] for k in kids}
    for r in conn.execute(
        f"SELECT kanji_id, alias FROM aliases WHERE kanji_id IN ({ph}) ORDER BY id", kids
    ).fetchall():
        alias_map[r["kanji_id"]].append(r["alias"])

    parts_map: dict[str, list[str]] = {k: [] for k in kids}
    seen: dict[str, set[str]] = {k: set() for k in kids}
    for r in conn.execute(
        f"SELECT kanji_id, part_term FROM parts WHERE kanji_id IN ({ph}) ORDER BY position", kids
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
