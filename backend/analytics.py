import re
import secrets
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
