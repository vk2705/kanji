from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from database import (
    db_conn, resolve_alias,
    create_kanji_entry, create_decomposition, create_alias, upsert_story,
    set_visibility, set_kanji_image, get_my_contributions,
)
from auth import require_user

router = APIRouter(tags=["contributions"])

Visibility = Literal["public", "private"]
Script = Literal["ja-kanji", "zh-Hans", "zh-Hant", "zh-Hani"]

UPLOAD_DIR = Path(__file__).parent / "uploads"
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/gif": "gif",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def _visible_kanji_id(conn, kanji_id: str, viewer_id: int) -> str:
    """Resolve kanji_id to its canonical id, 404ing if it doesn't exist or isn't
    visible to the caller (private data from someone else)."""
    cid = resolve_alias(conn, kanji_id, viewer_id)
    if not cid:
        raise HTTPException(status_code=404, detail="Kanji not found")
    return cid


class NewKanji(BaseModel):
    keyword: str
    character: str | None = None
    script: Script = "ja-kanji"
    visibility: Visibility = "private"


@router.post("/kanji")
def add_kanji(body: NewKanji, conn=Depends(db_conn), user=Depends(require_user)):
    if not body.keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword required")
    new_id = create_kanji_entry(
        conn, user["id"], body.keyword, body.character, body.script, body.visibility
    )
    return {"id": new_id}


@router.post("/kanji/{kanji_id}/image")
def upload_kanji_image(kanji_id: str, file: UploadFile = File(...),
                        conn=Depends(db_conn), user=Depends(require_user)):
    """Attach/replace a picture for a kanji you own — for user-invented primitives with
    no real Unicode glyph. Filename is always derived from the DB-resolved canonical id
    plus a whitelisted extension, never from client-supplied input.

    Sync (not async) so FastAPI runs dependency resolution and the handler body on the
    same threadpool thread — the sqlite3 connection from db_conn() is thread-affine
    (check_same_thread=True) and errors ("SQLite objects created in a thread can only
    be used in that same thread") if an async def here lets the handler body run on
    the event loop while conn was created on a worker thread."""
    cid = _visible_kanji_id(conn, kanji_id, user["id"])
    ext = IMAGE_EXTENSIONS.get(file.content_type)
    if not ext:
        raise HTTPException(status_code=400, detail="Unsupported image type; use gif, png, jpeg, or webp")
    data = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 2MB)")
    image_url = f"/uploads/{cid}.{ext}"
    if not set_kanji_image(conn, cid, user["id"], image_url):
        raise HTTPException(status_code=403, detail="Not found or not owned by you")
    for other_ext in IMAGE_EXTENSIONS.values():
        old = UPLOAD_DIR / f"{cid}.{other_ext}"
        if other_ext != ext and old.exists():
            old.unlink()
    (UPLOAD_DIR / f"{cid}.{ext}").write_bytes(data)
    return {"image_url": image_url}


class NewDecomposition(BaseModel):
    parts: list[str] = Field(min_length=1)
    label: str | None = None
    visibility: Visibility = "private"


@router.post("/kanji/{kanji_id}/decompositions")
def add_decomposition(kanji_id: str, body: NewDecomposition, conn=Depends(db_conn), user=Depends(require_user)):
    cid = _visible_kanji_id(conn, kanji_id, user["id"])
    parts = [p for p in body.parts if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="At least one part required")
    decomp_id = create_decomposition(conn, cid, user["id"], parts, body.label, body.visibility)
    return {"id": decomp_id, "kanji_id": cid}


class NewAlias(BaseModel):
    kanji_id: str
    alias: str
    visibility: Visibility = "private"


@router.post("/aliases")
def add_alias(body: NewAlias, conn=Depends(db_conn), user=Depends(require_user)):
    cid = _visible_kanji_id(conn, body.kanji_id, user["id"])
    if not body.alias.strip():
        raise HTTPException(status_code=400, detail="Alias required")
    create_alias(conn, cid, user["id"], body.alias, body.visibility)
    return {"kanji_id": cid, "alias": body.alias.strip().lower()}


class NewStory(BaseModel):
    kanji_id: str
    story: str
    visibility: Visibility = "private"


@router.post("/stories")
def add_story(body: NewStory, conn=Depends(db_conn), user=Depends(require_user)):
    cid = _visible_kanji_id(conn, body.kanji_id, user["id"])
    if not body.story.strip():
        raise HTTPException(status_code=400, detail="Story text required")
    story_id = upsert_story(conn, cid, user["id"], body.story.strip(), body.visibility)
    return {"id": story_id, "kanji_id": cid}


class VisibilityUpdate(BaseModel):
    visibility: Visibility


def _patch_visibility(table: str):
    def handler(row_id: int, body: VisibilityUpdate, conn=Depends(db_conn), user=Depends(require_user)):
        ok = set_visibility(conn, table, row_id, user["id"], body.visibility)
        if not ok:
            raise HTTPException(status_code=403, detail="Not found or not owned by you")
        return {"status": "ok"}
    handler.__name__ = f"patch_{table}_visibility"
    return handler


router.add_api_route("/aliases/{row_id}/visibility", _patch_visibility("aliases"), methods=["PATCH"])
router.add_api_route("/decompositions/{row_id}/visibility", _patch_visibility("decompositions"), methods=["PATCH"])
router.add_api_route("/stories/{row_id}/visibility", _patch_visibility("stories"), methods=["PATCH"])


@router.patch("/kanji/{kanji_id}/visibility")
def patch_kanji_visibility(kanji_id: str, body: VisibilityUpdate, conn=Depends(db_conn), user=Depends(require_user)):
    ok = set_visibility(conn, "kanji", kanji_id, user["id"], body.visibility)
    if not ok:
        raise HTTPException(status_code=403, detail="Not found or not owned by you")
    return {"status": "ok"}


@router.get("/me/contributions")
def my_contributions(conn=Depends(db_conn), user=Depends(require_user)):
    return get_my_contributions(conn, user["id"])
