#!/usr/bin/env python3
"""
RTK Kanji Search — CLI
Usage:
  rtk.py parts sun moon          # kanji containing all given primitives
  rtk.py text marsh              # kanji whose keyword/alias contains substring
  rtk.py char 明                 # look up by character
  rtk.py detail rtk145          # full detail for one entry
"""
import sys
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "backend" / "kanji.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_alias(conn, term):
    term = term.strip().lower()
    row = conn.execute("SELECT id FROM kanji WHERE id = ?", (term,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        "SELECT kanji_id FROM aliases WHERE alias = ? LIMIT 1", (term,)
    ).fetchone()
    return row["kanji_id"] if row else None


def search_parts(conn, terms):
    sets = []
    for term in terms:
        canonical = resolve_alias(conn, term) or term.lower()
        alias_rows = conn.execute(
            "SELECT alias FROM aliases WHERE kanji_id = ?", (canonical,)
        ).fetchall()
        search_terms = {canonical} | {r["alias"] for r in alias_rows} | {term.lower()}

        placeholders = ",".join("?" * len(search_terms))
        rows = conn.execute(
            f"SELECT DISTINCT kanji_id FROM parts WHERE part_term IN ({placeholders})",
            list(search_terms),
        ).fetchall()
        sets.append({r["kanji_id"] for r in rows})

    if not sets:
        return []
    result_ids = sets[0]
    for s in sets[1:]:
        result_ids &= s

    rows = []
    for kid in sorted(result_ids, key=lambda x: int(x[3:]) if x.startswith("rtk") and x[3:].isdigit() else 9999):
        row = conn.execute("SELECT * FROM kanji WHERE id = ?", (kid,)).fetchone()
        if row:
            rows.append(row)
    return rows


def search_text(conn, q):
    q = q.strip().lower()
    pattern = f"%{q}%"
    rows = conn.execute(
        """
        SELECT DISTINCT k.* FROM kanji k
        LEFT JOIN aliases a ON a.kanji_id = k.id
        WHERE k.id LIKE ? OR a.alias LIKE ?
        ORDER BY k.frame
        """,
        (pattern, pattern),
    ).fetchall()
    return rows


def search_char(conn, c):
    row = conn.execute("SELECT * FROM kanji WHERE character = ?", (c,)).fetchone()
    return [row] if row else []


def get_detail(conn, kid):
    canonical = resolve_alias(conn, kid)
    if not canonical:
        return None
    row = conn.execute("SELECT * FROM kanji WHERE id = ?", (canonical,)).fetchone()
    if not row:
        return None
    aliases = conn.execute(
        "SELECT alias FROM aliases WHERE kanji_id = ?", (canonical,)
    ).fetchall()
    parts = conn.execute(
        "SELECT part_term FROM parts WHERE kanji_id = ? ORDER BY position", (canonical,)
    ).fetchall()
    return dict(row), [r["alias"] for r in aliases], [r["part_term"] for r in parts]


def print_rows(rows, limit=20):
    if not rows:
        print("  (no results)")
        return
    for row in rows[:limit]:
        char = row["character"] or "?"
        kw   = row["keyword"] or ""
        fnum = f"[{row['frame']}]" if row["frame"] else ""
        jlpt = f"JLPT {row['jlpt']}" if row["jlpt"] else ""
        print(f"  {char}  {kw:<25} {row['id']:<12} {fnum:<8} {jlpt}")
    if len(rows) > limit:
        print(f"  … {len(rows) - limit} more results")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    if not DB.exists():
        print(f"Database not found: {DB}", file=sys.stderr)
        sys.exit(1)

    conn = get_db()
    cmd  = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "parts":
        print(f"Searching by parts: {args}")
        rows = search_parts(conn, args)
        print(f"{len(rows)} result(s):")
        print_rows(rows)

    elif cmd == "text":
        q = " ".join(args)
        print(f"Searching by text: '{q}'")
        rows = search_text(conn, q)
        print(f"{len(rows)} result(s):")
        print_rows(rows)

    elif cmd == "char":
        c = args[0]
        print(f"Searching by character: {c}")
        rows = search_char(conn, c)
        print_rows(rows)

    elif cmd == "detail":
        kid = args[0]
        result = get_detail(conn, kid)
        if not result:
            print(f"Not found: {kid}")
        else:
            row, aliases, parts = result
            print(f"\n  {row['character']}  {row['keyword']}")
            print(f"  ID: {row['id']}   Frame: {row['frame']}   Strokes: {row['stroke_count']}   JLPT: {row['jlpt']}")
            print(f"  Aliases : {', '.join(aliases)}")
            print(f"  Parts   : {', '.join(parts)}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

    conn.close()


if __name__ == "__main__":
    main()
