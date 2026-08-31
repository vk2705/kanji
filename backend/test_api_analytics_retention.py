"""
Isolated tests for prune_page_views.py and visit_stats.py's all-time accuracy after
pruning (architecture review finding #4, 2026-08-31: page_views had no retention at
all). Uses the same db_path temp-DB fixture as the rest of the isolated suite, but
doesn't need the app/client fixtures since these are plain-sqlite maintenance
scripts, not API endpoints.
"""
from datetime import datetime, timedelta, timezone

import database
import prune_page_views
import visit_stats


def _seed_page_view(conn, visitor_id, days_ago, path="/kanji/rtk1"):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn.execute(
        "INSERT INTO page_views (visitor_id, path, viewed_at) VALUES (?, ?, ?)",
        (visitor_id, path, ts)
    )


def test_dry_run_changes_nothing(db_path):
    conn = database.get_db()
    _seed_page_view(conn, "v1", days_ago=200)
    conn.commit()

    before = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    prune_page_views.DB_PATH = db_path
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["prune_page_views.py", "--dry-run", "--retain-days", "90"]
        prune_page_views.main()
    finally:
        sys.argv = old_argv
    after = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    assert after == before == 1
    summary_rows = conn.execute("SELECT COUNT(*) FROM daily_visit_summary").fetchone()[0]
    assert summary_rows == 0, "dry-run must not write to daily_visit_summary"
    conn.close()


def test_prune_rolls_up_old_rows_and_deletes_them(db_path):
    conn = database.get_db()
    _seed_page_view(conn, "old_visitor_a", days_ago=200)
    _seed_page_view(conn, "old_visitor_b", days_ago=200)
    _seed_page_view(conn, "recent_visitor", days_ago=1)
    conn.commit()
    conn.close()

    import sys
    prune_page_views.DB_PATH = db_path
    old_argv = sys.argv
    try:
        sys.argv = ["prune_page_views.py", "--retain-days", "90"]
        prune_page_views.main()
    finally:
        sys.argv = old_argv

    conn = database.get_db()
    remaining = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    assert remaining == 1, "only the recent row should survive pruning"

    summary = conn.execute("SELECT day, view_count, distinct_visitor_count FROM daily_visit_summary").fetchall()
    assert len(summary) == 1
    assert summary[0]["view_count"] == 2
    assert summary[0]["distinct_visitor_count"] == 2

    known = {r["visitor_id"] for r in conn.execute("SELECT visitor_id FROM known_visitors").fetchall()}
    assert known == {"old_visitor_a", "old_visitor_b"}
    conn.close()


def test_all_time_visitor_count_survives_pruning(db_path):
    """The actual bug a naive delete-old-rows approach would introduce: an all-time
    unique-visitor count that silently drops a visitor whose only rows got pruned."""
    conn = database.get_db()
    _seed_page_view(conn, "ancient_visitor", days_ago=200)
    _seed_page_view(conn, "recent_visitor", days_ago=1)
    conn.commit()
    conn.close()

    before_conn = database.get_db()
    total_before = before_conn.execute(
        "SELECT COUNT(DISTINCT visitor_id) FROM page_views"
    ).fetchone()[0]
    assert total_before == 2
    before_conn.close()

    import sys
    prune_page_views.DB_PATH = db_path
    old_argv = sys.argv
    try:
        sys.argv = ["prune_page_views.py", "--retain-days", "90"]
        prune_page_views.main()
    finally:
        sys.argv = old_argv

    conn = database.get_db()
    naive_count = conn.execute("SELECT COUNT(DISTINCT visitor_id) FROM page_views").fetchone()[0]
    assert naive_count == 1, "raw page_views alone now understates -- this is exactly why visit_stats.py unions known_visitors"

    accurate_count = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT visitor_id FROM page_views
            UNION
            SELECT visitor_id FROM known_visitors
        )
    """).fetchone()[0]
    assert accurate_count == 2, "ancient_visitor must still count via known_visitors after pruning"
    conn.close()


def test_returning_visitor_deduped_across_pruned_days(db_path):
    """A visitor who appears on two different (both old) days must be counted once
    in known_visitors, not twice."""
    conn = database.get_db()
    _seed_page_view(conn, "returning", days_ago=200)
    _seed_page_view(conn, "returning", days_ago=150)
    conn.commit()
    conn.close()

    import sys
    prune_page_views.DB_PATH = db_path
    old_argv = sys.argv
    try:
        sys.argv = ["prune_page_views.py", "--retain-days", "90"]
        prune_page_views.main()
    finally:
        sys.argv = old_argv

    conn = database.get_db()
    rows = conn.execute("SELECT * FROM known_visitors WHERE visitor_id = 'returning'").fetchall()
    assert len(rows) == 1
    conn.close()


def test_visit_stats_summary_runs_clean_after_pruning(db_path, capsys):
    """End-to-end smoke test: visit_stats.py's summary() must not error and must
    report a plausible all-time total after a prune has happened."""
    conn = database.get_db()
    _seed_page_view(conn, "a", days_ago=200)
    _seed_page_view(conn, "b", days_ago=1)
    conn.commit()
    conn.close()

    import sys
    prune_page_views.DB_PATH = db_path
    old_argv = sys.argv
    try:
        sys.argv = ["prune_page_views.py", "--retain-days", "90"]
        prune_page_views.main()
    finally:
        sys.argv = old_argv

    visit_stats.DB_PATH = db_path
    try:
        sys.argv = ["visit_stats.py"]
        visit_stats.main()
    finally:
        sys.argv = old_argv
    out = capsys.readouterr().out
    assert "All-time" in out
    assert "2 page views" in out or "2  page views" in out or "  2 page views" in out
