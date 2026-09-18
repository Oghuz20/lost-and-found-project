"""Shared pydantic domain models: `Item` and `MatchRecord`.

Joint ownership (per the team plan): whoever needs a new field opens a
small PR and tags the other two for review. Kept storage-shaped (matches
`ItemRepository`) rather than API-shaped, since the storage layer is the
one thing every other layer depends on being stable.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class ItemStatus(str, Enum):
    """Lifecycle state of a registered item."""

    LOST = "lost"
    FOUND = "found"
    MATCHED = "matched"
    CLOSED = "closed"


class Item(BaseModel):
    """A single lost or found item, as persisted by `ItemRepository`."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    status: ItemStatus
    user_text: str = ""
    image_path: str
    # `ai.ItemDescription.to_dict()` — kept as a plain dict (stored as JSONB)
    # rather than importing the ai/ pydantic model here, so this file never
    # needs to change if the AI module's schema gains fields.
    vlm_description: dict[str, Any] = Field(default_factory=dict)
    # Packed via `Item.pack_embedding`; a raw float32 buffer, not base64,
    # to keep it compact in Postgres BYTEA.
    embedding: bytes | None = None
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )

    def embedding_array(self) -> np.ndarray | None:
        """Unpack `embedding` back into the float32 vector `ai.embed` returned."""
        if self.embedding is None:
            return None
        return np.frombuffer(self.embedding, dtype=np.float32)

    @staticmethod
    def pack_embedding(vec: np.ndarray) -> bytes:
        """Pack an embedding vector for storage. Inverse of `embedding_array`."""
        return np.asarray(vec, dtype=np.float32).tobytes()

    def is_active(self) -> bool:
        """True if this item is still open for matching (not matched/closed)."""
        return self.status in (ItemStatus.LOST, ItemStatus.FOUND)


class MatchRecord(BaseModel):
    """A single persisted match between a lost item and a found item."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    lost_item_id: int
    found_item_id: int
    score: float
    reason: str = ""
    created_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )

    def is_strong_match(self, threshold: float = 0.7) -> bool:
        """True if `score` clears a confidence threshold worth surfacing to a user."""
        return self.score >= threshold
