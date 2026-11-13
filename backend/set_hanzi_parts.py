#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""set_hanzi_parts.py -- replace the parts of one system hanzi decomposition.

Hanzi rows have no data.txt (see CLAUDE.md, "Import pipeline"), so a fix to one
is a direct DB write. This does that write the same way import_hanzi.py made
the row in the first place -- each glyph followed by its keyword, via
database.expand_part_terms(..., script_group="zh") -- so a fixed row is
indistinguishable in shape from an imported one and searchable by name too.

    ./venv/bin/python3 set_hanzi_parts.py hanzi-8004 耂,毛            # dry run
    ./venv/bin/python3 set_hanzi_parts.py hanzi-8004 耂,毛 --apply    # write

Only touches owner_id=1 rows whose script is not ja-kanji (Japanese rows are
fixed in data.txt and synced instead), and only the decomposition with the
given --label (default "ids", the label import_hanzi.py gives its rows). Back
up first on prod (backup_db.py). Record the why in
docs/2026-08-search-quality-audit.md, as for any data fix.
"""
import argparse
import sys

import database


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kanji_id")
    ap.add_argument("parts", help="comma-separated glyphs, e.g. 耂,毛")
    ap.add_argument("--label", default="ids")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = database.get_db()
    row = conn.execute("SELECT character, script FROM kanji WHERE id = ? AND owner_id = 1",
                       (args.kanji_id,)).fetchone()
    if row is None or row["script"] == "ja-kanji":
        sys.exit(f"{args.kanji_id}: not a system hanzi row")
    decs = conn.execute("SELECT id FROM decompositions WHERE kanji_id = ? AND owner_id = 1 AND label IS ?",
                        (args.kanji_id, args.label)).fetchall()
    if len(decs) != 1:
        sys.exit(f"{args.kanji_id}: expected one system decomposition labelled {args.label!r}, found {len(decs)}")
    dec_id = decs[0]["id"]

    terms = [t.strip() for t in args.parts.split(",") if t.strip()]
    for t in terms:
        if not conn.execute("SELECT 1 FROM kanji WHERE character = ? AND visibility = 'public'", (t,)).fetchone():
            sys.exit(f"part {t!r} has no public row; it would not resolve")
    old = [r["part_term"] for r in conn.execute(
        "SELECT part_term FROM parts WHERE decomposition_id = ? ORDER BY position", (dec_id,))]
    new = database.expand_part_terms(conn, terms, script_group="zh")
    print(f"{args.kanji_id} {row['character']} (decomposition {dec_id})")
    print(f"  was: {old}")
    print(f"  now: {new}")
    if not args.apply:
        print("  dry run -- pass --apply to write")
        return
    with conn:
        conn.execute("DELETE FROM parts WHERE decomposition_id = ?", (dec_id,))
        conn.executemany(
            "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
            [(args.kanji_id, t, i, dec_id) for i, t in enumerate(new)])
    print("  written")


if __name__ == "__main__":
    main()
