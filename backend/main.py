from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import (
    init_db, import_data, get_db, db_conn, migrate_schema,
    search_by_parts, search_by_substring, search_by_char,
    get_kanji_detail, SCRIPT_VISIBILITY, SOURCE_SCOPES
)
from auth import router as auth_router, current_user
from contributions import router as contributions_router

UPLOAD_DIR = Path(__file__).parent / "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    conn = get_db()
    migrate_schema(conn)
    is_empty = conn.execute("SELECT COUNT(*) FROM kanji").fetchone()[0] == 0
    conn.close()
    if is_empty:
        import_data()
    yield


app = FastAPI(title="Kanji RTK Search API", lifespan=lifespan)

# Wildcard origins can't be combined with allow_credentials=True (browsers reject
# credentialed cross-origin requests against a wildcard) — the session cookie needs
# allow_credentials, so this lists the dev frontend explicitly. Production is
# same-origin (nginx proxies /kanji/api/ -> this app under the same domain), so
# CORS doesn't come into play there at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(contributions_router)

# Created eagerly (not deferred to the lifespan handler) because StaticFiles needs the
# directory to exist at mount time, which happens at import — before lifespan runs.
UPLOAD_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def _validate_script(script: str | None) -> str | None:
    if script is not None and script not in SCRIPT_VISIBILITY:
        raise HTTPException(status_code=400, detail=f"Invalid script; must be one of {list(SCRIPT_VISIBILITY)}")
    return script


def _validate_sources(sources: list[str] | None) -> set[str] | None:
    if sources is None:
        return None
    invalid = set(sources) - set(SOURCE_SCOPES)
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid sources {sorted(invalid)}; must be a subset of {list(SOURCE_SCOPES)}")
    return set(sources)


class PartsSearchRequest(BaseModel):
    parts: list[str]
    script: str | None = None
    sources: list[str] | None = None


@app.post("/search/parts")
def search_parts(req: PartsSearchRequest, conn=Depends(db_conn), user=Depends(current_user)):
    parts = [p.strip() for p in req.parts if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Provide at least one part name")
    script = _validate_script(req.script)
    sources = _validate_sources(req.sources)
    results = search_by_parts(conn, parts, user["id"] if user else None, script, sources)
    return {"results": results, "count": len(results)}


@app.get("/search/text")
def search_text(q: str = Query(..., min_length=1), script: str | None = Query(None),
                sources: list[str] | None = Query(None),
                conn=Depends(db_conn), user=Depends(current_user)):
    script = _validate_script(script)
    sources = _validate_sources(sources)
    results = search_by_substring(conn, q, user["id"] if user else None, script, sources)
    return {"results": results, "count": len(results)}


@app.get("/search/char")
def search_char(c: str = Query(..., min_length=1, max_length=2), script: str | None = Query(None),
                sources: list[str] | None = Query(None),
                conn=Depends(db_conn), user=Depends(current_user)):
    script = _validate_script(script)
    sources = _validate_sources(sources)
    result = search_by_char(conn, c, user["id"] if user else None, script, sources)
    if not result:
        raise HTTPException(status_code=404, detail="Character not found")
    return result


@app.get("/kanji/{kanji_id}")
def kanji_detail(kanji_id: str, sources: list[str] | None = Query(None),
                  conn=Depends(db_conn), user=Depends(current_user)):
    sources = _validate_sources(sources)
    result = get_kanji_detail(conn, kanji_id, user["id"] if user else None, sources)
    if not result:
        raise HTTPException(status_code=404, detail="Kanji not found")
    return result
