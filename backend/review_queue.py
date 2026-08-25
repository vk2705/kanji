#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
review_queue.py — surface the in-app decomposition review queue for a maintainer
to act on (docs/2026-08-search-quality-audit.md has the full design rationale).

## What this is

The kanji detail page now has two buttons per decomposition: "approve" and
"dispute" (POST /decompositions/{id}/review, `database.set_decomposition_review`).
This is the "запомни этот метод и пользуйся им для окончательной верификации"
standing audit practice — actually looking at a decomposition and judging it
correct or not — exposed as something any logged-in user can do straight from
the page, not just something that happens inside a Claude session.

Clicking either button writes one row to `decomposition_reviews`
(decomposition_id, reviewer_id, verdict, created_at, processed_at). This
script is the other half: read the pending (processed_at IS NULL) rows,
decide what to do with each, then mark them processed so they drop out of
the queue ("после обработки этого список очистить" — clear the list after
processing, not by deleting the record, just by no longer showing it as
pending).

## What "processed" means per verdict

- **approved** — the decomposition is confirmed correct. Add a pinned entry
  to `test_regression_fixes.py`'s EXPECTED_DECOMPOSITIONS for that kanji_id
  (see that file's own docstring), so a future edit can't silently regress
  it without a loud test failure. Then mark the review row processed.
- **disputed** — a user thinks the decomposition looks wrong. Investigate it
  the same way any owner-reported bug in this audit gets investigated: CSV
  cross-check (heisig-kanjis.csv components) and, where the primitive's
  identity itself is in question, render_glyphs.py. Fix data.txt if the
  dispute is confirmed, or leave it and note why if it isn't. Either way,
  mark the review row processed once you've reached a verdict — a dispute
  that turns out to be a false alarm is still "handled", not still pending.

## Usage

    python3 review_queue.py                      # list all pending reviews
    python3 review_queue.py --verdict approved    # list only pending approvals
    python3 review_queue.py --verdict disputed    # list only pending disputes
    python3 review_queue.py --mark-processed 3 7 9   # clear specific review row ids

Listing is read-only. Marking processed is the only mutation this script
does, and only to the rows you name explicitly — never bulk-clears.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import database  # noqa: E402


def list_queue(conn, verdict: str | None):
    rows = database.get_review_queue(conn, verdict=verdict, only_unprocessed=True)
    if not rows:
        print(f"No pending {verdict or ''} reviews.".replace("  ", " "))
        return
    print(f"{len(rows)} pending review(s):\n")
    for r in rows:
        print(f"  [{r['id']}] {r['verdict']:9s} decomposition {r['decomposition_id']} "
              f"of {r['kanji_id']} ({r['character']}/{r['keyword']}) "
              f"by {r['reviewer']} at {r['created_at']}")
    print("\nAfter acting on these (pin approved ones in test_regression_fixes.py, "
          "investigate/fix disputed ones), clear them with:\n"
          f"  python3 review_queue.py --mark-processed {' '.join(str(r['id']) for r in rows)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verdict", choices=["approved", "disputed"], default=None,
                         help="Only list this verdict (default: both).")
    parser.add_argument("--mark-processed", nargs="+", type=int, metavar="ID",
                         help="Review row id(s) to mark processed, clearing them from the pending queue.")
    args = parser.parse_args()

    conn = database.get_db()
    try:
        if args.mark_processed:
            database.mark_reviews_processed(conn, args.mark_processed)
            print(f"Marked {len(args.mark_processed)} review(s) processed: {args.mark_processed}")
        else:
            list_queue(conn, args.verdict)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
