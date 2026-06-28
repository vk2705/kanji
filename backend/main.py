from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import (
    init_db, import_data, get_db,
    search_by_parts, search_by_substring, search_by_char,
    get_kanji_detail, DB_PATH
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if not DB_PATH.exists() or DB_PATH.stat().st_size < 1000:
        import_data()
    yield


app = FastAPI(title="Kanji RTK Search API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db_conn():
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


class PartsSearchRequest(BaseModel):
    parts: list[str]


@app.post("/search/parts")
def search_parts(req: PartsSearchRequest, conn=Depends(db_conn)):
    parts = [p.strip() for p in req.parts if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Provide at least one part name")
    results = search_by_parts(conn, parts)
    return {"results": results, "count": len(results)}


@app.get("/search/text")
def search_text(q: str = Query(..., min_length=1), conn=Depends(db_conn)):
    results = search_by_substring(conn, q)
    return {"results": results, "count": len(results)}


@app.get("/search/char")
def search_char(c: str = Query(..., min_length=1, max_length=2), conn=Depends(db_conn)):
    result = search_by_char(conn, c)
    if not result:
        raise HTTPException(status_code=404, detail="Character not found")
    return result


@app.get("/kanji/{kanji_id}")
def kanji_detail(kanji_id: str, conn=Depends(db_conn)):
    result = get_kanji_detail(conn, kanji_id)
    if not result:
        raise HTTPException(status_code=404, detail="Kanji not found")
    return result


@app.post("/admin/reimport")
def reimport():
    init_db()
    import_data()
    return {"status": "ok"}
