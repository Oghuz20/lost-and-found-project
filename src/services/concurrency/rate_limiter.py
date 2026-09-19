import asyncio
import time
from typing import Any


class TokenBucketRateLimiter:
    """
    Token-aware rate limiter (Token Bucket), отслеживающий
    лимиты запросов в минуту (RPM) и токенов в минуту (TPM).
    """

    def __init__(self, requests_per_minute: int = 60, tokens_per_minute: int = 90000) -> None:
        self.rpm = requests_per_minute
        self.tpm = tokens_per_minute

        self.req_capacity = float(requests_per_minute)
        self.token_capacity = float(tokens_per_minute)

        self.req_tokens = float(requests_per_minute)
        self.token_tokens = float(tokens_per_minute)

        self.req_fill_rate = requests_per_minute / 60.0
        self.token_fill_rate = tokens_per_minute / 60.0

        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int = 500) -> None:
        """
        Запрашивает разрешение на отправку запроса.
        При недостатке токенов асинхронно ждет пополнения.
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now

                # Пополняем токены пропорционально прошедшему времени
                self.req_tokens = min(self.req_capacity, self.req_tokens + elapsed * self.req_fill_rate)
                self.token_tokens = min(self.token_capacity, self.token_tokens + elapsed * self.token_fill_rate)

                # Проверяем, достаточно ли лимита
                if self.req_tokens >= 1.0 and self.token_tokens >= estimated_tokens:
                    self.req_tokens -= 1.0
                    self.token_tokens -= estimated_tokens
                    return

                # Расчет времени ожидания
                req_wait = (1.0 - self.req_tokens) / self.req_fill_rate if self.req_tokens < 1.0 else 0.0
                token_wait = (estimated_tokens - self.token_tokens) / self.token_fill_rate if self.token_tokens < estimated_tokens else 0.0
                sleep_time = max(req_wait, token_wait, 0.05)

                await asyncio.sleep(sleep_time)

    def get_state(self) -> dict[str, Any]:
        """Возвращает текущий баланс токенов для логов/демонстрации."""
        return {
            "available_requests": round(self.req_tokens, 2),
            "available_tokens": round(self.token_tokens, 2),
            "rpm_limit": self.rpm,
            "tpm_limit": self.tpm,
        }