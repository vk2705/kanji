#!/usr/bin/env python3
"""
fix_kradfile_proxies.py — remove KRADFILE JIS-substitute glyphs from system decompositions.

Background (see docs/2026-08-search-quality-audit.md "Finding 2"): five characters
(乞 化 刈 買 犯) were flagged as "real kanji misused as unaliased visual proxies" —
part terms that resolve only because they coincidentally match an unrelated, fully-
fledged kanji, polluting search with irrelevant hits (e.g. searching "beg" matches
牧/攻/敗/... which have nothing to do with begging).

Root cause, confirmed by fetching the actual upstream KRADFILE and checking its own
header comment: "[...] Where the element alone is not in JIS X 0208, a kanji which
contains the element is used instead." These five are KRADFILE's own stand-in index
glyphs for small stroke shapes with no JIS X 0208 codepoint of their own — not errors
introduced by this project's import pipeline, and not a fixed 1:1 mapping to any one
real primitive (they show up across visually unrelated hosts). Since `import_rtk.py`
pulled KRADFILE's radical lists directly into `data.txt`'s parts fields, they ended up
seeded into `kanji.db` too. `data.txt` itself has already been corrected (they're
stripped from all ~397 affected lines); this script applies the equivalent fix
directly against an already-seeded database, since `kanji.db` is the source of truth
post-launch and re-running the import pipeline is not an available fix path (see
CLAUDE.md "Architecture").

Scope: only deletes rows from *system* decompositions (owner_id = 1) on `ja-kanji`
rows — a user's own contributed decomposition is left untouched even if it happens to
use one of these characters, since that's a real per-user editorial choice, not this
import artifact. Scoping to `ja-kanji` also matters because it's not just a users-vs-
system distinction: `zh-*` (hanzi) rows are seeded by `import_hanzi.py` from cjkvi-ids
IDS data, a genuinely different and stricter decomposition source where these same
five characters can be real drawn components, not a JIS-substitution artifact — so
they must not be touched there.

Usage:
    python3 fix_kradfile_proxies.py [--db kanji.db] [--dry-run]
"""

import argparse
import sqlite3
from pathlib import Path

PROXY_GLYPHS = ["乞", "化", "刈", "買", "犯"]
# expand_part_terms() auto-expands each raw glyph into an extra sibling row holding
# its own keyword, at import time — so the keyword row is an orphaned symptom of the
# same bug and must be removed alongside the glyph, not left behind.
PROXY_KEYWORDS = ["beg", "change", "reap", "buy", "crime"]
PROXY_TERMS = PROXY_GLYPHS + PROXY_KEYWORDS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(__file__).parent / "kanji.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    c = conn.cursor()

    placeholders = ",".join("?" * len(PROXY_TERMS))
    c.execute(
        f"""
        SELECT p.kanji_id, p.part_term, k.character, k.keyword
        FROM parts p
        JOIN decompositions d ON d.id = p.decomposition_id
        JOIN kanji k ON k.id = p.kanji_id
        WHERE d.owner_id = 1 AND k.script = 'ja-kanji' AND p.part_term IN ({placeholders})
        ORDER BY p.kanji_id
        """,
        PROXY_TERMS,
    )
    rows = c.fetchall()

    print(f"DB: {args.db}")
    print(f"Rows to delete: {len(rows)}")
    by_term = {}
    for kanji_id, term, char, keyword in rows:
        by_term.setdefault(term, []).append(f"{kanji_id}({char}/{keyword})")
    for term, hosts in by_term.items():
        print(f"  {term}: {len(hosts)} hosts, e.g. {', '.join(hosts[:5])}")

    if args.dry_run:
        print("Dry run, no changes made.")
        return

    c.execute(
        f"""
        DELETE FROM parts
        WHERE id IN (
            SELECT p.id FROM parts p
            JOIN decompositions d ON d.id = p.decomposition_id
            JOIN kanji k ON k.id = p.kanji_id
            WHERE d.owner_id = 1 AND k.script = 'ja-kanji' AND p.part_term IN ({placeholders})
        )
        """,
        PROXY_TERMS,
    )
    deleted = c.rowcount
    conn.commit()
    print(f"Deleted {deleted} rows.")


if __name__ == "__main__":
    main()
