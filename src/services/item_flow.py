"""Shared registration and matching logic for CLI and HTTP API."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy import ndarray

from ai import top_k
from src.config import Settings, get_settings
from src.models import Item, ItemStatus
from src.services.ai_service import describe_item, embed
from src.storage.blob_store import BlobStore, BlobValidationError
from src.storage.repository import ItemRepository
from src.validation import (
    validate_found_item_input,
    validate_lost_item_input,
    validate_search_matches_input,
)


class ItemFlowError(Exception):
    """Base error for item registration / matching."""


class ItemNotFoundError(ItemFlowError):
    """No item with the given id."""


class ItemNoEmbeddingError(ItemFlowError):
    """Item exists but has no stored embedding."""


def item_to_api_dict(item: Item) -> dict[str, Any]:
    """Serialize an item for JSON responses."""
    status = item.status if isinstance(item.status, str) else item.status.value
    vlm = item.vlm_description or {}
    return {
        "id": item.id,
        "status": status,
        "user_text": item.user_text,
        "image_path": item.image_path,
        "object_class": vlm.get("object_class"),
        "vlm_description": vlm,
        "created_at": item.created_at.isoformat(),
    }


def resolve_item_image_path(item: Item, settings: Settings | None = None) -> Path:
    """Return resolved image path if it lies under the configured storage root."""
    settings = settings or get_settings()
    root = settings.image_storage_dir.resolve()
    path = Path(item.image_path).resolve()
    if root not in path.parents and path != root:
        raise BlobValidationError("item image path escapes the storage directory")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


async def register_uploaded_item(
    *,
    status: ItemStatus,
    user_text: str,
    file_bytes: bytes,
    original_filename: str,
    repo: ItemRepository,
    store: BlobStore | None = None,
) -> Item:
    """Validate upload, run AI pipeline, persist item."""
    if status == ItemStatus.LOST:
        validate_lost_item_input({"user_text": user_text})
    elif status == ItemStatus.FOUND:
        validate_found_item_input({"user_text": user_text})
    else:
        raise ValueError(f"cannot register item with status {status!r}")

    blob_store = store or BlobStore()
    blob = blob_store.save(file_bytes, original_filename=original_filename)
    image_path = str(blob.path)

    desc = await asyncio.to_thread(describe_item, image_path, user_text)
    vec = await asyncio.to_thread(embed, desc.to_search_text())
    embedding = Item.pack_embedding(np.asarray(vec, dtype=np.float32))

    item = Item(
        status=status,
        user_text=user_text.strip(),
        image_path=image_path,
        vlm_description=desc.to_dict(),
        embedding=embedding,
    )
    return await repo.save_item(item)


async def register_item_from_file(
    *,
    status: ItemStatus,
    image_path: str,
    user_text: str,
    repo: ItemRepository,
    store: BlobStore | None = None,
) -> Item:
    """Register an item from a local file path (CLI)."""
    try:
        data = Path(image_path).read_bytes()
    except OSError as exc:
        raise ItemFlowError(f"could not read {image_path!r}: {exc}") from exc
    return await register_uploaded_item(
        status=status,
        user_text=user_text,
        file_bytes=data,
        original_filename=image_path,
        repo=repo,
        store=store,
    )


async def find_top_matches(
    *,
    item_id: int,
    k: int,
    repo: ItemRepository,
) -> tuple[Item, list[dict[str, Any]]]:
    """Return query item and top-k matches against the opposite pool."""
    validate_search_matches_input({"k": k})

    query_item = await repo.get_item(item_id)
    if query_item is None:
        raise ItemNotFoundError(f"no item with id {item_id}")

    query_vec = query_item.embedding_array()
    if query_vec is None:
        raise ItemNoEmbeddingError(f"item {item_id} has no stored embedding")

    opposite_status = (
        ItemStatus.FOUND if query_item.status == ItemStatus.LOST else ItemStatus.LOST
    )
    candidates = await repo.list_items(opposite_status)
    scored_candidates = [c for c in candidates if c.embedding_array() is not None]
    if not scored_candidates:
        return query_item, []

    cand_vecs = [cast(ndarray, c.embedding_array()) for c in scored_candidates]
    raw_matches = top_k(query_vec, cand_vecs, k=min(k, len(scored_candidates)))

    matches: list[dict[str, Any]] = []
    for m in raw_matches:
        cand = scored_candidates[m.candidate_id]
        vlm = cand.vlm_description or {}
        matches.append(
            {
                "item_id": cand.id,
                "status": cand.status.value,
                "score": m.score,
                "object_class": vlm.get("object_class"),
                "user_text": cand.user_text,
                "reason": m.reason,
            }
        )
    return query_item, matches
