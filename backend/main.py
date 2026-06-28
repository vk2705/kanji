from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from database import (
    init_db, import_data, get_db,
    search_by_parts, search_by_substring, search_by_char,
    get_kanji_detail, DB_PATH
)

app = FastAPI(title="Kanji RTK Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()
    if not DB_PATH.exists() or DB_PATH.stat().st_size < 1000:
        import_data()


class PartsSearchRequest(BaseModel):
    parts: list[str]


@app.post("/search/parts")
def search_parts(req: PartsSearchRequest):
    parts = [p.strip() for p in req.parts if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Provide at least one part name")
    conn = get_db()
    try:
        results = search_by_parts(conn, parts)
    finally:
        conn.close()
    return {"results": results, "count": len(results)}


@app.get("/search/text")
def search_text(q: str = Query(..., min_length=1)):
    conn = get_db()
    try:
        results = search_by_substring(conn, q)
    finally:
        conn.close()
    return {"results": results, "count": len(results)}


@app.get("/search/char")
def search_char(c: str = Query(..., min_length=1, max_length=2)):
    conn = get_db()
    try:
        result = search_by_char(conn, c)
    finally:
        conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="Character not found")
    return result


@app.get("/kanji/{kanji_id}")
def kanji_detail(kanji_id: str):
    conn = get_db()
    try:
        result = get_kanji_detail(conn, kanji_id)
    finally:
        conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="Kanji not found")
    return result


@app.post("/admin/reimport")
def reimport():
    init_db()
    import_data()
    return {"status": "ok"}
