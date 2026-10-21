import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Header, Response
from pydantic import BaseModel, Field

from database import db_conn, record_engagement, record_page_view

router = APIRouter(tags=["analytics"])

VISITOR_COOKIE = "kanji_visitor"
VISITOR_TTL_DAYS = 365

# Self-declared crawlers and automation. Google's renderer runs the app's
# JavaScript (Googlebot, Google-InspectionTool), so without this every crawl
# counted as a visitor. Anything that lies about its user agent still gets
# through here, which is what the engagement events below are for.
BOT_USER_AGENT = re.compile(
    r"bot|crawl|spider|slurp|google-inspectiontool|googleother|headless|lighthouse"
    r"|facebookexternalhit|preview|python|curl|wget|httpclient|go-http|java/|okhttp",
    re.IGNORECASE,
)


def is_bot(user_agent: str | None) -> bool:
    return not user_agent or bool(BOT_USER_AGENT.search(user_agent))


def _visitor_id(kanji_visitor: str | None, response: Response) -> str:
    if kanji_visitor:
        return kanji_visitor
    visitor_id = secrets.token_hex(16)
    response.set_cookie(
        VISITOR_COOKIE, visitor_id,
        secure=True, samesite="lax",
        max_age=VISITOR_TTL_DAYS * 24 * 3600, path="/",
    )
    return visitor_id


class PageView(BaseModel):
    # No auth required on this endpoint (see pageview() below), so path is the one
    # attacker-controlled field written to page_views on every call — bounded to stop
    # someone using it to stuff arbitrarily large strings into the DB one row at a
    # time (architecture review finding #4).
    path: str | None = Field(default=None, max_length=500)


@router.post("/analytics/pageview")
def pageview(
    body: PageView,
    response: Response,
    kanji_visitor: str | None = Cookie(default=None),
    user_agent: str | None = Header(default=None),
    conn=Depends(db_conn),
):
    """Record one page load. Deliberately minimal: no auth required (most visitors
    are anonymous), no IP stored — just a random first-party visitor_id, issued once
    and read back on later visits via a long-lived cookie, same cookie flags as the
    session cookie in auth.py minus httponly (nothing sensitive in it, and there's no
    need to keep it from client JS). Called once per app load from the frontend; see
    database.py's _migrate_v5 docstring for why this exists instead of parsing nginx
    logs, and visit_stats.py for the read side."""
    if is_bot(user_agent):
        return {"ok": True}
    record_page_view(conn, _visitor_id(kanji_visitor, response), body.path)
    return {"ok": True}


class Engagement(BaseModel):
    kind: Literal["search", "detail"]


@router.post("/analytics/event")
def event(
    body: Engagement,
    response: Response,
    kanji_visitor: str | None = Cookie(default=None),
    user_agent: str | None = Header(default=None),
    conn=Depends(db_conn),
):
    """Record that a visitor *did* something: ran a search, or opened a kanji.
    Crawlers load the page and leave, so this is the "real person" signal that
    visit_stats.py reports separately from raw page views. The frontend sends each
    kind at most once per page load. Only the kind is stored, never the query."""
    if is_bot(user_agent):
        return {"ok": True}
    record_engagement(conn, _visitor_id(kanji_visitor, response), body.kind)
    return {"ok": True}


@router.get("/analytics/stats")
def stats(days: int = 30, conn=Depends(db_conn)):
    """Aggregate visit counts for the unlisted /stats page (owner request,
    2026-10-21: "let anyone access it if they know the URL"). Counts only — no
    visitor ids, paths or anything per-visitor leaves this function. The same
    numbers visit_stats.py prints; "people" (visitor_engagement) is the one that
    means real humans, the view/visitor columns still include anything that ran
    the app's JavaScript without a bot user agent."""
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    today = now.date()

    def views_since(cutoff: datetime) -> tuple[int, int]:
        row = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT visitor_id) FROM page_views WHERE viewed_at >= ?",
            (cutoff.isoformat(),),
        ).fetchone()
        return row[0], row[1]

    def people_since(day: date | None) -> dict:
        where, params = ("WHERE day >= ?", (day.isoformat(),)) if day else ("", ())
        row = conn.execute(
            f"""SELECT COUNT(DISTINCT visitor_id),
                       COALESCE(SUM(CASE WHEN kind = 'search' THEN count END), 0),
                       COALESCE(SUM(CASE WHEN kind = 'detail' THEN count END), 0)
                FROM visitor_engagement {where}""",
            params,
        ).fetchone()
        return {"people": row[0], "searches": row[1], "kanji_opened": row[2]}

    periods = []
    for label, span in [("today", 1), ("7d", 7), ("30d", 30)]:
        views, visitors = views_since(now - timedelta(days=span))
        periods.append({"period": label, "views": views, "visitors": visitors,
                        **people_since(today - timedelta(days=span - 1))})
    total_views = conn.execute("SELECT COUNT(*) FROM page_views").fetchone()[0] + conn.execute(
        "SELECT COALESCE(SUM(view_count), 0) FROM daily_visit_summary").fetchone()[0]
    total_visitors = conn.execute(
        "SELECT COUNT(*) FROM (SELECT visitor_id FROM page_views UNION SELECT visitor_id FROM known_visitors)"
    ).fetchone()[0]
    periods.append({"period": "all", "views": total_views, "visitors": total_visitors, **people_since(None)})

    first_day = (today - timedelta(days=days - 1)).isoformat()
    daily: dict[str, dict] = {}
    for row in conn.execute(
        "SELECT day, view_count, distinct_visitor_count FROM daily_visit_summary WHERE day >= ?", (first_day,)
    ):
        daily[row[0]] = {"views": row[1], "visitors": row[2]}
    for row in conn.execute(
        """SELECT date(viewed_at), COUNT(*), COUNT(DISTINCT visitor_id) FROM page_views
           WHERE date(viewed_at) >= ? GROUP BY date(viewed_at)""", (first_day,)
    ):
        daily[row[0]] = {"views": row[1], "visitors": row[2]}
    for row in conn.execute(
        """SELECT day, COUNT(DISTINCT visitor_id),
                  COALESCE(SUM(CASE WHEN kind = 'search' THEN count END), 0),
                  COALESCE(SUM(CASE WHEN kind = 'detail' THEN count END), 0)
           FROM visitor_engagement WHERE day >= ? GROUP BY day""", (first_day,)
    ):
        daily.setdefault(row[0], {"views": 0, "visitors": 0}).update(
            {"people": row[1], "searches": row[2], "kanji_opened": row[3]})
    days_list = []
    for offset in range(days):
        day = (today - timedelta(days=offset)).isoformat()
        entry = {"day": day, "views": 0, "visitors": 0, "people": 0, "searches": 0, "kanji_opened": 0}
        entry.update(daily.get(day, {}))
        days_list.append(entry)

    people_since_row = conn.execute("SELECT MIN(day) FROM visitor_engagement").fetchone()[0]
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "people_tracked_since": people_since_row or today.isoformat(),
        "periods": periods,
        "daily": days_list,
    }
