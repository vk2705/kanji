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
            alias       TEXT NOT NULL
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
    # Entries with a parts field (col 3) are treated as decomposition overrides:
    # they replace the CSV components for that kanji.
    # Parts may be English names ("water", "mouth") or kanji chars ("口", "氵").
    prim_aliases:  dict[str, list[str]] = {}   # id -> [alias, ...]
    prim_chars:    dict[str, str]       = {}   # id -> character
    parts_override: dict[str, list[str]] = {}  # id -> [part_term, ...]

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
                parts_str = cols[3].strip() if len(cols) > 3 else ""
                aliases = [a.strip().lower() for a in alias_str.split(",") if a.strip()]
                prim_aliases[pid] = aliases
                if char and char not in ("?", "??", ""):
                    prim_chars[pid] = char
                # Store parts override if present
                if parts_str:
                    raw_parts = [p.strip() for p in parts_str.replace(";", ",").split(",") if p.strip()]
                    # Normalise: lowercase English names, keep kanji chars as-is
                    normalised = []
                    for p in raw_parts:
                        if all(ord(c) < 128 for c in p):
                            normalised.append(p.lower())   # ASCII → lowercase
                        else:
                            normalised.append(p)            # kanji char → keep
                    parts_override[pid] = normalised

    # ── 1b. Load parts from data_from_pdf.txt (lower priority than data.txt) ───
    # Entries here override CSV components but are themselves overridden by data.txt.
    pdf_parts: dict[str, list[str]] = {}  # id -> [part_term, ...]

    if PDF_PATH.exists():
        with open(PDF_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                cols = line.split(":")
                pid = cols[0].strip().lower()
                parts_str = cols[3].strip() if len(cols) > 3 else ""
                if pid and parts_str:
                    raw = [p.strip().lower() for p in parts_str.split(",") if p.strip()]
                    if raw:
                        pdf_parts[pid] = raw

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

            # component terms: "sun; day; moon; flesh" etc.
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

    # Insert kanji rows
    conn.executemany(
        "INSERT OR IGNORE INTO kanji (id, character, keyword, frame, stroke_count, jlpt) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(r["id"], r["char"], r["keyword"], r["frame"], r["strokes"], r["jlpt"])
         for r in rows_to_insert]
    )

    # Insert aliases (keyword as first alias)
    for r in rows_to_insert:
        _insert_alias(conn, r["id"], r["keyword"])
        # Also alias by frame number string and character
        _insert_alias(conn, r["id"], str(r["frame"]))
        if r["char"]:
            _insert_alias(conn, r["id"], r["char"])

    # Insert parts from CSV
    for r in rows_to_insert:
        for pos, term in enumerate(r["comp_terms"]):
            conn.execute(
                "INSERT INTO parts (kanji_id, part_term, position) VALUES (?, ?, ?)",
                (r["id"], term, pos)
            )

    # ── 4. Insert primitive entries from data.txt ─────────────────────────────
    # If the primitive has a real character that's already in the database as
    # an rtk entry, merge aliases into that entry instead of creating a duplicate.
    for pid, aliases in prim_aliases.items():
        char = prim_chars.get(pid, "?")
        keyword = aliases[0] if aliases else pid

        # Find the canonical id: prefer an existing rtk entry by character OR by alias
        canonical = pid
        if char and char not in ("?", "??"):
            row = conn.execute("SELECT id FROM kanji WHERE character = ?", (char,)).fetchone()
            if row:
                canonical = row["id"]
        if canonical == pid:
            # Check if any alias in this primitive's list is itself an existing kanji id
            for a in aliases:
                row = conn.execute("SELECT id FROM kanji WHERE id = ?", (a,)).fetchone()
                if row:
                    canonical = row["id"]
                    break

        # Create the primitive entry only if it has no real character (pure primitive)
        if canonical == pid:
            existing = conn.execute("SELECT id FROM kanji WHERE id = ?", (pid,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT OR IGNORE INTO kanji (id, character, keyword) VALUES (?, ?, ?)",
                    (pid, char, keyword)
                )

        # Add all aliases (including the rad id itself as an alias) to canonical
        for a in aliases:
            _insert_alias(conn, canonical, a)
        _insert_alias(conn, canonical, pid)   # rad id is an alias too
        if char and char not in ("?", "??"):
            _insert_alias(conn, canonical, char)

    # ── 5. Apply parts overrides from data.txt ────────────────────────────────
    # For any entry with a parts field in data.txt, replace the CSV-derived parts.
    # Also build a char→id map from what's now in the DB, so kanji chars in
    # parts fields (like 口, 氵) resolve to their canonical ids.
    char_to_db_id: dict[str, str] = {}
    for row in conn.execute("SELECT id, character FROM kanji WHERE character IS NOT NULL AND character != ''").fetchall():
        if row["character"] not in ("?", "??"):
            char_to_db_id[row["character"]] = row["id"]

    overrides_applied = 0
    for pid, parts in merged_parts_override.items():
        # Resolve the entry id: pid may be an rtk id or a rad id
        canonical = resolve_alias(conn, pid)
        if not canonical:
            continue
        if not parts:
            continue

        # Expand each part term: English name or kanji char → canonical alias
        expanded_terms = []
        for term in parts:
            if term in char_to_db_id:
                # It's a kanji character — add both the char and its keyword
                db_id = char_to_db_id[term]
                kw_row = conn.execute("SELECT keyword FROM kanji WHERE id=?", (db_id,)).fetchone()
                expanded_terms.append(term)             # kanji char itself
                if kw_row and kw_row["keyword"]:
                    expanded_terms.append(kw_row["keyword"])  # English keyword too
            else:
                expanded_terms.append(term)

        # Delete existing CSV parts and replace with override
        conn.execute("DELETE FROM parts WHERE kanji_id = ?", (canonical,))
        for pos, term in enumerate(expanded_terms):
            conn.execute(
                "INSERT INTO parts (kanji_id, part_term, position) VALUES (?, ?, ?)",
                (canonical, term, pos)
            )
        overrides_applied += 1

    conn.commit()
    conn.close()
    print(f"Import complete: {len(rows_to_insert)} kanji rows, {overrides_applied} parts overrides applied "
          f"({len(pdf_parts)} from PDF, {len(parts_override)} from data.txt, {len(pdf_parts) - len(set(pdf_parts) - set(parts_override))} PDF entries superseded by data.txt).")


def _insert_alias(conn, kanji_id: str, alias: str):
    alias = alias.strip().lower()
    if not alias:
        return
    existing = conn.execute(
        "SELECT 1 FROM aliases WHERE kanji_id = ? AND alias = ?",
        (kanji_id, alias)
    ).fetchone()
    if not existing:
        try:
            conn.execute(
                "INSERT INTO aliases (kanji_id, alias) VALUES (?, ?)",
                (kanji_id, alias)
            )
        except Exception:
            pass


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
    """
    Given a search term, return the full set of aliases for that primitive
    (so we can match any of them in the parts table).
    """
    term = term.strip().lower()
    cid = resolve_alias(conn, term)
    if not cid:
        return {term}
    rows = conn.execute(
        "SELECT alias FROM aliases WHERE kanji_id = ?", (cid,)
    ).fetchall()
    result = {r["alias"] for r in rows} | {term, cid}
    return result


def search_by_parts(conn, part_names: list[str]) -> list[dict]:
    """
    Find kanji containing ALL given primitives.
    Since component terms in the parts table are already recursively expanded,
    this is a flat set-intersection: find kanji_id that has at least one alias
    of EACH search term in its parts.
    """
    terms = [p.strip().lower() for p in part_names if p.strip()]
    if not terms:
        return []

    # For each search term, expand to all aliases of that primitive
    alias_sets = [get_all_aliases_for_term(conn, t) for t in terms]

    # Build SQL: for each alias set, the kanji must have at least one matching part
    # We use EXISTS subqueries for each condition
    conditions = []
    params = []
    for aliases in alias_sets:
        placeholders = ",".join("?" * len(aliases))
        conditions.append(
            f"EXISTS (SELECT 1 FROM parts p WHERE p.kanji_id = k.id AND p.part_term IN ({placeholders}))"
        )
        params.extend(aliases)

    sql = f"SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji k WHERE {' AND '.join(conditions)} ORDER BY frame NULLS LAST"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(conn, r) for r in rows]


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
    return [_row_to_dict(conn, r) for r in rows]


def search_by_char(conn, character: str) -> dict | None:
    """Find a kanji by its character glyph."""
    row = conn.execute(
        "SELECT id, character, keyword, frame, stroke_count, jlpt FROM kanji WHERE character = ?",
        (character,)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(conn, row)


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
    entry = _row_to_dict(conn, row)

    # Resolve each part term to a kanji entry
    part_rows = conn.execute(
        "SELECT part_term FROM parts WHERE kanji_id = ? ORDER BY position",
        (cid,)
    ).fetchall()

    resolved = []
    seen_ids = set()
    for pr in part_rows:
        term = pr["part_term"]
        pid = resolve_alias(conn, term)
        if pid and pid != cid and pid not in seen_ids:
            seen_ids.add(pid)
            prow = conn.execute(
                "SELECT id, character, keyword, frame FROM kanji WHERE id = ?", (pid,)
            ).fetchone()
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
    kid = row["id"]
    aliases = [
        r["alias"] for r in conn.execute(
            "SELECT alias FROM aliases WHERE kanji_id = ? ORDER BY id LIMIT 20", (kid,)
        ).fetchall()
    ]
    raw_parts = [
        r["part_term"] for r in conn.execute(
            "SELECT DISTINCT part_term FROM parts WHERE kanji_id = ? ORDER BY position", (kid,)
        ).fetchall()
    ]
    return {
        "id": kid,
        "character": row["character"],
        "keyword": row["keyword"],
        "frame": row["frame"] if "frame" in row.keys() else None,
        "stroke_count": row["stroke_count"] if "stroke_count" in row.keys() else None,
        "jlpt": row["jlpt"] if "jlpt" in row.keys() else None,
        "aliases": aliases,
        "parts": raw_parts,
    }
