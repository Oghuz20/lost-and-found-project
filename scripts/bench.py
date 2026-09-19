import asyncio
import time


async def fake_processing_task(item_id: int) -> float:
    """Имитация вызова AI-сервиса (задержка 0.2 секунды)."""
    await asyncio.sleep(0.2)
    return item_id


async def run_sequential(items: list[int]) -> float:
    """Последовательная обработка элементов."""
    start_time = time.perf_counter()
    for item in items:
        await fake_processing_task(item)
    return time.perf_counter() - start_time


async def run_concurrent(items: list[int], max_concurrency: int = 5) -> float:
    """Параллельная обработка через Semaphore."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _worker(item: int):
        async with semaphore:
            return await fake_processing_task(item)

    start_time = time.perf_counter()
    await asyncio.gather(*[_worker(item) for item in items])
    return time.perf_counter() - start_time


async def main():
    items = list(range(10))  # 10 элементов для теста
    print("--- Running Benchmark ---")

    seq_time = await run_sequential(items)
    print(f"Sequential processing time: {seq_time:.2f} seconds")

    conc_time = await run_concurrent(items, max_concurrency=5)
    print(f"Concurrent processing time (max_concurrency=5): {conc_time:.2f} seconds")

    speedup = seq_time / conc_time if conc_time > 0 else 0
    print(f"Speedup factor: {speedup:.2f}x")


if __name__ == "__main__":
    asyncio.run(main())