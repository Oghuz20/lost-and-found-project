"""ItemRepository: the only module allowed to speak SQL to Postgres.

Owner: Person A.

Business logic (matching, the HTTP API, the CLI) should call this class,
never issue its own queries — that keeps the SQL, and any future schema
migration, in one place.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from src.models import Item, ItemStatus, MatchRecord


class ItemRepository:
    """CRUD + query access over the `items` and `matches` tables."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save_item(self, item: Item) -> Item:
        row = await self._pool.fetchrow(
            """
            INSERT INTO items (status, user_text, image_path, vlm_description, embedding, created_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6)
            RETURNING id, status, user_text, image_path, vlm_description, embedding, created_at
            """,
            item.status.value,
            item.user_text,
            item.image_path,
            json.dumps(item.vlm_description),
            item.embedding,
            item.created_at,
        )
        return self._row_to_item(row)

    async def get_item(self, item_id: int) -> Item | None:
        row = await self._pool.fetchrow("SELECT * FROM items WHERE id = $1", item_id)
        return self._row_to_item(row) if row else None

    async def list_items(self, status: ItemStatus | str | None = None) -> list[Item]:
        if status is None:
            rows = await self._pool.fetch("SELECT * FROM items ORDER BY created_at DESC")
        else:
            status_value = status.value if isinstance(status, ItemStatus) else status
            rows = await self._pool.fetch(
                "SELECT * FROM items WHERE status = $1 ORDER BY created_at DESC",
                status_value,
            )
        return [self._row_to_item(r) for r in rows]

    async def save_match(self, match: MatchRecord) -> MatchRecord:
        row = await self._pool.fetchrow(
            """
            INSERT INTO matches (lost_item_id, found_item_id, score, reason, created_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, lost_item_id, found_item_id, score, reason, created_at
            """,
            match.lost_item_id,
            match.found_item_id,
            match.score,
            match.reason,
            match.created_at,
        )
        return MatchRecord(**dict(row))

    @staticmethod
    def _row_to_item(row: asyncpg.Record) -> Item:
        data: dict[str, Any] = dict(row)
        vlm = data["vlm_description"]
        # asyncpg returns JSONB as a raw string unless a codec is registered;
        # accept both so this keeps working whether or not the app sets one up.
        if isinstance(vlm, str):
            vlm = json.loads(vlm)
        data["vlm_description"] = vlm
        data["status"] = ItemStatus(data["status"])
        return Item(**data)
