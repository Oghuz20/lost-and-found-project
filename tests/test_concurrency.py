import pytest
import asyncio
from src.services.concurrency.batch_runner import BatchRunner


@pytest.mark.asyncio
async def test_batch_runner_partial_failure_does_not_lose_other_results():
    async def maybe_fail(x):
        if x == 2:
            raise ValueError("boom")
        return x * 10

    runner = BatchRunner(max_concurrency=3)
    results = await runner.run_batch([1, 2, 3], maybe_fail)

    assert results[0] == 10
    assert isinstance(results[1], ValueError)
    assert results[2] == 30