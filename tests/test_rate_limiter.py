import pytest
import asyncio
from src.services.concurrency.rate_limiter import TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_acquire():
    limiter = TokenBucketRateLimiter(requests_per_minute=60, tokens_per_minute=1000)
    await limiter.acquire(estimated_tokens=100)
    
    state = limiter.get_state()
    assert state["available_requests"] < 60
    assert state["available_tokens"] < 1000