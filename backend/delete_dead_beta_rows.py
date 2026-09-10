#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""delete_dead_beta_rows.py — remove the two orphaned pre-migration 阝 placeholders.

`rad3.39` ("rightside beta") and `rad3.40` ("leftside beta") were the KRADFILE-era
placeholders for the two 阝 radicals. The 2026-08 `kangxi{n}` migration created
*new* ids (`kangxi170` left / "pinnacle", `kangxi163` right / "walls") rather than
renaming these, so both rows have sat dead ever since: no aliases, no
decompositions, never referenced as a part_term, nothing points `variant_of` at
them. Their only remaining effect is polluting the "By Text" search for "beta"
with two glyph-less junk hits.

`sync_system_data.py` deliberately never auto-deletes a system row that's absent
from the source files (it only warns), so this is the manual counterpart. Refuses
to run if either row turns out to still be referenced.

    ./venv/bin/python3 delete_dead_beta_rows.py --dry-run
    ./venv/bin/python3 delete_dead_beta_rows.py --confirm
"""
import argparse
import sqlite3
import sys

import database

DEAD_IDS = ("rad3.39", "rad3.40")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually delete")
    ap.add_argument("--dry-run", action="store_true", help="report only (default)")
    args = ap.parse_args()

    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    for kid in DEAD_IDS:
        row = conn.execute("SELECT id, character, keyword FROM kanji WHERE id = ?", (kid,)).fetchone()
        if row is None:
            print(f"{kid}: already gone")
            continue

        as_part = [r["kanji_id"] for r in conn.execute(
            "SELECT DISTINCT kanji_id FROM parts WHERE part_term = ?", (kid,))]
        decs = conn.execute("SELECT COUNT(*) FROM decompositions WHERE kanji_id = ?", (kid,)).fetchone()[0]
        variants = [r["id"] for r in conn.execute(
            "SELECT id FROM kanji WHERE variant_of = ?", (kid,))]
        aliases = [r["alias"] for r in conn.execute(
            "SELECT alias FROM aliases WHERE kanji_id = ?", (kid,))]

        print(f"{kid}: char={row['character']!r} keyword={row['keyword']!r}")
        print(f"   used as part_term in: {as_part or 'nothing'}")
        print(f"   own decompositions:   {decs}")
        print(f"   variant_of targets:   {variants or 'nothing'}")
        print(f"   own alias rows:        {aliases or 'none'}")

        if as_part or decs or variants:
            print(f"   !! {kid} is still referenced — refusing to delete anything.")
            sys.exit(1)

    if not args.confirm:
        print("\n[dry run] pass --confirm to delete.")
        return

    with conn:
        conn.execute(
            f"DELETE FROM aliases WHERE kanji_id IN ({','.join('?' * len(DEAD_IDS))})", DEAD_IDS)
        cur = conn.execute(
            f"DELETE FROM kanji WHERE id IN ({','.join('?' * len(DEAD_IDS))})", DEAD_IDS)
    print(f"\nDeleted {cur.rowcount} kanji row(s) + their aliases.")

    still = conn.execute(
        f"SELECT id FROM kanji WHERE id IN ({','.join('?' * len(DEAD_IDS))})", DEAD_IDS).fetchall()
    print("remaining:", [r["id"] for r in still] or "none")


if __name__ == "__main__":
    main()
