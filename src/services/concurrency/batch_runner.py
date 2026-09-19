from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")
R = TypeVar("R")


class BatchRunner:
    """Runs an async function over a list of items concurrently, bounded
    by a semaphore.
    """

    def __init__(self, max_concurrency: int = 5) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def run_batch(
        self,
        items: list[T],
        async_func: Callable[[T], Any],
        *,
        raise_on_error: bool = False,
    ) -> list[R | BaseException]:
        async def _worker(item: T) -> R:
            async with self.semaphore:
                return await async_func(item)

        tasks = [_worker(item) for item in items]
        results: list[R | BaseException] = await asyncio.gather(*tasks, return_exceptions=True)

        if raise_on_error:
            for res in results:
                if isinstance(res, BaseException):
                    raise res

        return results