"""AsyncPG connection pool + schema management.

Owner: Person A.

Keep this the *only* module that calls `asyncpg.create_pool` — everything
else (repository, API, CLI) should ask `get_pool()` for a pool rather than
opening its own connections, so there's one lifecycle to reason about and
one place a test needs to patch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from src.config import Settings, get_settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def get_pool(settings: Settings | None = None) -> asyncpg.Pool:
    """Return the process-wide connection pool, creating it on first use.

    Safe to call concurrently: a lock guards pool creation so a burst of
    concurrent requests at startup doesn't open the pool twice.
    """
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            settings = settings or get_settings()
            _pool = await asyncpg.create_pool(
                dsn=settings.asyncpg_dsn, min_size=1, max_size=10
            )
    return _pool


async def close_pool() -> None:
    """Close the pool and drop the cached reference. Call on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_schema(
    pool: asyncpg.Pool | None = None, settings: Settings | None = None
) -> None:
    """Idempotently create tables/indexes. Safe to call on every startup.

    `pool` can be passed explicitly (tests do this with a fake pool);
    otherwise it's fetched via `get_pool`.
    """
    pool = pool or await get_pool(settings)
    ddl = _SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(ddl)
