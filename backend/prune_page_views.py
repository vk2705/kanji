#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
prune_page_views.py — bounds the growth of the `page_views` table (architecture
review finding #4, 2026-08-31: POST /analytics/pageview needs no auth, making it
the easiest unbounded-DB-growth vector in this app, and the table had no pruning
at all until now).

Aggregates before deleting, so pruning never loses accuracy, unlike a naive
"DELETE WHERE viewed_at < cutoff":
  - Every raw page_views row older than the retention window gets rolled up into
    `daily_visit_summary` (one row per calendar day: view_count, distinct_visitor_
    count) before its row is deleted — visit_stats.py's per-day breakdown stays
    correct forever, just less granular (day, not individual events) past the
    window.
  - Every visitor_id ever seen is recorded in `known_visitors` (first/last-seen)
    before any of their rows are pruned — this is what keeps the *all-time*
    distinct-visitor count accurate: a visitor who returns across many days can't
    be correctly deduped from per-day summaries alone once the raw rows backing
    earlier days are gone, so this needs its own standing record.

Same "one-off script, run on a schedule, reads/writes kanji.db directly" convention
as backup_db.py — meant to run daily/weekly via a systemd timer (or cron), not as
part of the app's request path.

Usage:
    ./prune_page_views.py               # prune rows older than RETAIN_DAYS (default 90)
    ./prune_page_views.py --dry-run      # report what would be pruned, change nothing
    ./prune_page_views.py --retain-days 30
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "kanji.db"
RETAIN_DAYS = 90


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be pruned without changing anything")
    parser.add_argument("--retain-days", type=int, default=RETAIN_DAYS,
                         help=f"Keep raw page_views rows newer than this many days (default {RETAIN_DAYS})")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"No database at {DB_PATH}")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.retain_days)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    old_row_count = conn.execute(
        "SELECT COUNT(*) FROM page_views WHERE viewed_at < ?", (cutoff,)
    ).fetchone()[0]
    if old_row_count == 0:
        print(f"No page_views rows older than {args.retain_days} days ({cutoff}) — nothing to prune.")
        conn.close()
        return

    daily_rows = conn.execute(
        """SELECT date(viewed_at) AS day, COUNT(*) AS views, COUNT(DISTINCT visitor_id) AS visitors
           FROM page_views WHERE viewed_at < ? GROUP BY day ORDER BY day""",
        (cutoff,)
    ).fetchall()
    visitor_rows = conn.execute(
        """SELECT visitor_id, MIN(viewed_at) AS first_seen, MAX(viewed_at) AS last_seen
           FROM page_views WHERE viewed_at < ? GROUP BY visitor_id""",
        (cutoff,)
    ).fetchall()

    print(f"{old_row_count} page_views rows older than {args.retain_days} days "
          f"({len(daily_rows)} distinct days, {len(visitor_rows)} distinct visitors) "
          f"{'would be' if args.dry_run else 'will be'} rolled up and pruned.")

    if args.dry_run:
        conn.close()
        return

    with conn:
        # ON CONFLICT rather than INSERT OR REPLACE: a day/visitor already
        # summarised from an earlier prune run needs its counts added to, not
        # overwritten (running this script twice against overlapping data, e.g. a
        # shortened --retain-days later, must not lose the first run's numbers).
        conn.executemany(
            """INSERT INTO daily_visit_summary (day, view_count, distinct_visitor_count)
               VALUES (?, ?, ?)
               ON CONFLICT(day) DO UPDATE SET view_count = view_count + excluded.view_count,
                   distinct_visitor_count = MAX(distinct_visitor_count, excluded.distinct_visitor_count)""",
            [(r["day"], r["views"], r["visitors"]) for r in daily_rows]
        )
        conn.executemany(
            """INSERT INTO known_visitors (visitor_id, first_seen, last_seen)
               VALUES (?, ?, ?)
               ON CONFLICT(visitor_id) DO UPDATE SET
                   first_seen = MIN(first_seen, excluded.first_seen),
                   last_seen = MAX(last_seen, excluded.last_seen)""",
            [(r["visitor_id"], r["first_seen"], r["last_seen"]) for r in visitor_rows]
        )
        conn.execute("DELETE FROM page_views WHERE viewed_at < ?", (cutoff,))

    remaining = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    print(f"Pruned. {remaining} page_views rows remain (within the last {args.retain_days} days).")
    conn.close()


if __name__ == "__main__":
    main()
