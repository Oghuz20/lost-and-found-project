
from fastapi import Depends, FastAPI, File, Form, Query, UploadFile

from src.config import get_settings
from src.storage.db import get_pool, init_schema
from src.storage.repository import ItemRepository

app = FastAPI(
    title="Smart Lost & Found API",
    description="API for registering lost/found items and running semantic search",
    version="1.0.0",
)


async def get_repo() -> ItemRepository:
    settings = get_settings()
    pool = await get_pool(settings)
    await init_schema(pool, settings)
    return ItemRepository(pool)


@app.post("/items/lost", status_code=201)
async def register_lost_item(
    user_text: str = Form(""),
    file: UploadFile = File(...),
):
    """Регистрация потерянной вещи через HTTP API."""
    return {
        "status": "lost",
        "filename": file.filename,
        "user_text": user_text,
        "message": "Item registered successfully",
    }


@app.post("/items/found", status_code=201)
async def register_found_item(
    user_text: str = Form(""),
    file: UploadFile = File(...),
):
    """Регистрация найденной вещи через HTTP API."""
    return {
        "status": "found",
        "filename": file.filename,
        "user_text": user_text,
        "message": "Item registered successfully",
    }


@app.get("/items")
async def list_items(
    status: str | None = Query(None, description="Filter by 'lost' or 'found'"),
    repo: ItemRepository = Depends(get_repo),
):
    """Получение списка всех зарегистрированных предметов."""
    # Convert status to lowercase to match stored database values ('lost'/'found')
    status_filter = status.lower() if status else None
    items = await repo.list_items(status_filter)
    
    return {
        "status_filter": status,
        "items": [
            {
                "id": item.id,
                "status": item.status if isinstance(item.status, str) else item.status.value,
                "user_text": item.user_text,
                "image_path": getattr(item, "image_path", None),
                "vlm_description": getattr(item, "vlm_description", None),
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ],
    }


@app.get("/items/{item_id}/matches")
async def get_matches(item_id: str, k: int = Query(3, ge=1, le=20)):
    """Поиск топ-K наиболее похожих предметов."""
    return {
        "item_id": item_id,
        "top_k": k,
        "matches": [],
    }