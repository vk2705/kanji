import secrets

from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel, Field

from database import db_conn, record_page_view

router = APIRouter(tags=["analytics"])

VISITOR_COOKIE = "kanji_visitor"
VISITOR_TTL_DAYS = 365


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
    conn=Depends(db_conn),
):
    """Record one page load. Deliberately minimal: no auth required (most visitors
    are anonymous), no IP stored — just a random first-party visitor_id, issued once
    and read back on later visits via a long-lived cookie, same cookie flags as the
    session cookie in auth.py minus httponly (nothing sensitive in it, and there's no
    need to keep it from client JS). Called once per app load from the frontend; see
    database.py's _migrate_v5 docstring for why this exists instead of parsing nginx
    logs, and visit_stats.py for the read side."""
    visitor_id = kanji_visitor or secrets.token_hex(16)
    record_page_view(conn, visitor_id, body.path)
    if not kanji_visitor:
        response.set_cookie(
            VISITOR_COOKIE, visitor_id,
            secure=True, samesite="lax",
            max_age=VISITOR_TTL_DAYS * 24 * 3600, path="/",
        )
    return {"ok": True}
