#!/home/ec2-user/apps/kanji/backend/venv/bin/python3
"""
visit_stats.py — owner-facing read side of the page_views counter added 2026-08-29
(see database.py's _migrate_v5 docstring for why this exists: nginx access logs
turned out to be almost entirely bots/scanners, with no quick way to tell how many
real visitors the site actually gets). Same "one-off script reads kanji.db directly"
convention as review_queue.py/coverage_status.py, rather than a public HTTP stats
endpoint — there's no admin-role concept in this schema.

A "visit" here means one frontend app load that successfully called
POST /analytics/pageview -- a bot that only ever hits URLs directly (the vast
majority of this site's raw traffic, per the nginx-log analysis that prompted this)
never runs the page's JS and never shows up here at all, unlike an IP-based count.

Usage:
    ./visit_stats.py              # summary: today / 7d / 30d / all-time
    ./visit_stats.py --days 14    # daily breakdown for the last N days
"""
import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "kanji.db"


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def summary(conn):
    for label, days in [("Today", 1), ("Last 7 days", 7), ("Last 30 days", 30)]:
        cutoff = _since(days)
        views = conn.execute("SELECT COUNT(*) FROM page_views WHERE viewed_at >= ?", (cutoff,)).fetchone()[0]
        visitors = conn.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM page_views WHERE viewed_at >= ?", (cutoff,)
        ).fetchone()[0]
        print(f"{label:<14} {views:>6} page views, {visitors:>4} unique visitors")

    # All-time totals combine live page_views rows with whatever prune_page_views.py
    # has already rolled up into daily_visit_summary/known_visitors -- reading
    # page_views alone would silently understate "all-time" once pruning has run
    # (architecture review finding #4, 2026-08-31: page_views previously had no
    # retention at all). A visitor counted in both the live rows and
    # known_visitors (i.e. they visited both before and after the last prune) is
    # only counted once, via the UNION below.
    live_views = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    pruned_views = conn.execute("SELECT COALESCE(SUM(view_count), 0) FROM daily_visit_summary").fetchone()[0]
    total_views = live_views + pruned_views

    total_visitors = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT visitor_id FROM page_views
            UNION
            SELECT visitor_id FROM known_visitors
        )
    """).fetchone()[0]
    print(f"{'All-time':<14} {total_views:>6} page views, {total_visitors:>4} unique visitors")

    first = conn.execute("""
        SELECT MIN(t) FROM (
            SELECT MIN(viewed_at) AS t FROM page_views
            UNION ALL
            SELECT MIN(day) AS t FROM daily_visit_summary
        )
    """).fetchone()[0]
    if first:
        print(f"\nTracking since {first}")
    else:
        print("\nNo visits recorded yet.")


def daily_breakdown(conn, days: int):
    """Per-day view/visitor counts for the requested window. Days still covered by
    live page_views rows get an exact distinct-visitor count; any older days that
    prune_page_views.py has already rolled up (architecture review finding #4,
    2026-08-31) fall back to daily_visit_summary's per-day counts instead of
    silently vanishing from the breakdown -- those are still exact for that single
    day (COUNT(DISTINCT visitor_id) *within* one day is unaffected by pruning;
    only cross-day dedup, i.e. the all-time total in summary() above, needs
    known_visitors)."""
    cutoff = _since(days)
    live_rows = {
        r["day"]: (r["views"], r["visitors"]) for r in conn.execute(
            """SELECT date(viewed_at) AS day, COUNT(*) AS views, COUNT(DISTINCT visitor_id) AS visitors
               FROM page_views WHERE viewed_at >= ? GROUP BY day""",
            (cutoff,)
        ).fetchall()
    }
    summary_rows = {
        r["day"]: (r["view_count"], r["distinct_visitor_count"]) for r in conn.execute(
            "SELECT day, view_count, distinct_visitor_count FROM daily_visit_summary WHERE day >= ?",
            (cutoff[:10],)
        ).fetchall()
    }
    # live_rows wins on any day present in both (shouldn't normally overlap --
    # prune_page_views.py only rolls up days older than its retention window --
    # but prefer the exact live figure if it ever does).
    merged = {**summary_rows, **live_rows}
    rows = sorted(merged.items())
    if not rows:
        print(f"No visits in the last {days} day(s).")
        return
    print(f"{'Date':<12} {'Views':>7} {'Visitors':>10}")
    for day, (views, visitors) in rows:
        print(f"{day:<12} {views:>7} {visitors:>10}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, help="Show a daily breakdown for the last N days instead of the summary")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if args.days:
        daily_breakdown(conn, args.days)
    else:
        summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
