from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from src.config import Settings, get_settings
from src.models import ItemStatus
from src.services.ai_service import AIServiceError
from src.services.item_flow import (
    ItemNoEmbeddingError,
    ItemNotFoundError,
    find_top_matches,
    item_to_api_dict,
    register_uploaded_item,
    resolve_item_image_path,
)
from src.storage.blob_store import BlobValidationError
from src.storage.db import get_pool, init_schema
from src.storage.repository import ItemRepository

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Smart Lost & Found API",
    description="API for registering lost/found items and running semantic search",
    version="1.0.0",
)

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


async def get_repo() -> ItemRepository:
    settings = get_settings()
    pool = await get_pool(settings)
    await init_schema(pool, settings)
    return ItemRepository(pool)


def _item_summary(item) -> dict:
    data = item_to_api_dict(item)
    return data


@app.get("/")
async def web_ui() -> FileResponse:
    index = _STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Web UI not installed")
    return FileResponse(index)


@app.post("/items/lost", status_code=201)
async def register_lost_item(
    user_text: str = Form(...),
    file: UploadFile = File(...),
    repo: ItemRepository = Depends(get_repo),
):
    data = await file.read()
    try:
        saved = await register_uploaded_item(
            status=ItemStatus.LOST,
            user_text=user_text,
            file_bytes=data,
            original_filename=file.filename or "upload",
            repo=repo,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except BlobValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"message": "Item registered successfully", "item": _item_summary(saved)}


@app.post("/items/found", status_code=201)
async def register_found_item(
    user_text: str = Form(...),
    file: UploadFile = File(...),
    repo: ItemRepository = Depends(get_repo),
):
    data = await file.read()
    try:
        saved = await register_uploaded_item(
            status=ItemStatus.FOUND,
            user_text=user_text,
            file_bytes=data,
            original_filename=file.filename or "upload",
            repo=repo,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except BlobValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"message": "Item registered successfully", "item": _item_summary(saved)}


@app.get("/items")
async def list_items(
    status: str | None = Query(None, description="Filter by 'lost' or 'found'"),
    repo: ItemRepository = Depends(get_repo),
):
    status_filter = status.lower() if status else None
    items = await repo.list_items(status_filter)
    return {
        "status_filter": status,
        "items": [_item_summary(item) for item in items],
    }


@app.get("/items/{item_id}/matches")
async def get_matches(
    item_id: int,
    k: int = Query(3, ge=1, le=20),
    repo: ItemRepository = Depends(get_repo),
):
    try:
        query_item, matches = await find_top_matches(item_id=item_id, k=k, repo=repo)
    except ItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ItemNoEmbeddingError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    return {
        "item_id": item_id,
        "query": _item_summary(query_item),
        "top_k": k,
        "matches": matches,
    }


@app.get("/items/{item_id}/image")
async def get_item_image(
    item_id: int,
    repo: ItemRepository = Depends(get_repo),
    settings: Settings = Depends(get_settings),
):
    item = await repo.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"no item with id {item_id}")
    try:
        path = resolve_item_image_path(item, settings)
    except BlobValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="image file not found") from exc

    media = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    return FileResponse(path, media_type=media)
