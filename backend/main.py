from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import (
    init_db, import_data, get_db, db_conn, migrate_schema,
    search_by_parts, search_by_substring, search_by_char,
    get_kanji_detail
)
from auth import router as auth_router, current_user
from contributions import router as contributions_router


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


class PartsSearchRequest(BaseModel):
    parts: list[str]


@app.post("/search/parts")
def search_parts(req: PartsSearchRequest, conn=Depends(db_conn), user=Depends(current_user)):
    parts = [p.strip() for p in req.parts if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Provide at least one part name")
    results = search_by_parts(conn, parts, user["id"] if user else None)
    return {"results": results, "count": len(results)}


@app.get("/search/text")
def search_text(q: str = Query(..., min_length=1), conn=Depends(db_conn), user=Depends(current_user)):
    results = search_by_substring(conn, q, user["id"] if user else None)
    return {"results": results, "count": len(results)}


@app.get("/search/char")
def search_char(c: str = Query(..., min_length=1, max_length=2), conn=Depends(db_conn), user=Depends(current_user)):
    result = search_by_char(conn, c, user["id"] if user else None)
    if not result:
        raise HTTPException(status_code=404, detail="Character not found")
    return result


@app.get("/kanji/{kanji_id}")
def kanji_detail(kanji_id: str, conn=Depends(db_conn), user=Depends(current_user)):
    result = get_kanji_detail(conn, kanji_id, user["id"] if user else None)
    if not result:
        raise HTTPException(status_code=404, detail="Kanji not found")
    return result
