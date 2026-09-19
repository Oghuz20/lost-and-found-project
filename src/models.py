"""Domain models for Person A's storage and registration scope."""

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
    vlm_description: dict[str, Any] = Field(default_factory=dict)
    embedding: bytes | None = None
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def embedding_array(self) -> np.ndarray | None:
        """Unpack `embedding` back into the float32 vector."""
        if self.embedding is None:
            return None
        return np.frombuffer(self.embedding, dtype=np.float32)

    @staticmethod
    def pack_embedding(vec: np.ndarray) -> bytes:
        """Pack an embedding vector for storage."""
        return np.asarray(vec, dtype=np.float32).tobytes()


class MatchRecord(BaseModel):
    """A single persisted match between a lost item and a found item."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    lost_item_id: int
    found_item_id: int
    score: float
    reason: str = ""
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))