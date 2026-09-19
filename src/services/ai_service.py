"""Wraps ai.* calls with retry, caching, timeout, and telemetry.

Only this module should import from `ai` directly. Everything else
(API, CLI, pipeline) calls the functions here instead.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import ai
from ai.providers.base import ProviderError
from ai.schemas import ItemDescription

from ..logging_config import get_logger, setup_logging
from ..services.cache import cached_embed
from ..telemetry.cost import record_cost
from ..telemetry.tracing import trace_ai_call

setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

DEFAULT_TIMEOUT = 30.0

# Reused across calls; also gives us a real timeout via future.result().
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ai-call")


def _current_provider_model(kind: str) -> tuple[str, str]:
    """Read provider/model from env vars (providers expose no metadata)."""
    if kind == "vlm":
        return os.getenv("LLM_PROVIDER", "unknown"), os.getenv("LLM_MODEL", "unknown")
    return os.getenv("EMBEDDING_PROVIDER", "unknown"), os.getenv("EMBEDDING_MODEL", "unknown")


class AIServiceError(RuntimeError):
    """Raised after retries are exhausted or on an unexpected error."""


@retry(
    retry=retry_if_exception_type(ProviderError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 1s, 2s, 4s
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _describe_item_with_retry(
    image_path: str,
    user_text: str,
    *,
    vlm=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ItemDescription:
    """Describe an item with retry and a real, enforced timeout."""
    future = _executor.submit(ai.describe_item, image_path, user_text, vlm=vlm)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        raise ProviderError(f"describe_item timed out after {timeout}s")


def describe_item(
    image_path: str,
    user_text: str,
    *,
    vlm=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ItemDescription:
    """Describe an item, retrying transient failures."""
    logger.info(
        "describe_item start",
        extra={"image_path": image_path, "text_len": len(user_text or "")},
    )
    provider, model = _current_provider_model("vlm")

    start_time = time.time()
    try:
        result = _describe_item_with_retry(image_path, user_text, vlm=vlm, timeout=timeout)
    except ProviderError as e:
        elapsed = time.time() - start_time
        logger.error("describe_item failed after retries: %s", e)
        record_cost("describe_item", elapsed, success=False, provider=provider, model=model)
        trace_ai_call(
            operation="describe_item", provider=provider, model=model,
            latency=elapsed, status="error", error=str(e),
        )
        raise AIServiceError(f"describe_item failed after 3 attempts: {e}") from e
    except (FileNotFoundError, ValueError):
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("describe_item failed with unexpected error: %s", e)
        record_cost("describe_item", elapsed, success=False, provider=provider, model=model)
        trace_ai_call(
            operation="describe_item", provider=provider, model=model,
            latency=elapsed, status="error", error=str(e),
        )
        raise AIServiceError(f"describe_item failed unexpectedly: {e}") from e

    elapsed = time.time() - start_time
    logger.info(
        "describe_item ok",
        extra={
            "object_class": result.object_class,
            "confidence": result.confidence,
            "duration_ms": round(elapsed * 1000, 2),
        },
    )
    record_cost("describe_item", elapsed, success=True, provider=provider, model=model)
    trace_ai_call(
        operation="describe_item", provider=provider, model=model,
        latency=elapsed, status="success",
        input_length=len(user_text or ""),
        output_fields={"object_class": result.object_class, "confidence": result.confidence},
    )
    return result


@retry(
    retry=retry_if_exception_type(ProviderError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _embed_with_retry(text: str, *, embedder=None, timeout: float = DEFAULT_TIMEOUT):
    """Embed text with retry and a real, enforced timeout."""
    future = _executor.submit(cached_embed, text, embedder)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        raise ProviderError(f"embed timed out after {timeout}s")


def embed(text: str, *, embedder=None, timeout: float = DEFAULT_TIMEOUT) -> list[float]:
    """Embed text with retry, real timeout, and caching."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty string")

    logger.info("embed start", extra={"text_len": len(text)})
    provider, model = _current_provider_model("embedding")

    start_time = time.time()
    try:
        result = _embed_with_retry(text, embedder=embedder, timeout=timeout)
    except ProviderError as e:
        elapsed = time.time() - start_time
        logger.error("embed failed after retries: %s", e)
        record_cost("embed", elapsed, success=False, provider=provider, model=model)
        trace_ai_call(operation="embed", provider=provider, model=model,
                       latency=elapsed, status="error", error=str(e))
        raise AIServiceError(f"embed failed after 3 attempts: {e}") from e
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("embed failed with unexpected error: %s", e)
        record_cost("embed", elapsed, success=False, provider=provider, model=model)
        trace_ai_call(operation="embed", provider=provider, model=model,
                       latency=elapsed, status="error", error=str(e))
        raise AIServiceError(f"embed failed unexpectedly: {e}") from e

    elapsed = time.time() - start_time
    embedding_list = result.tolist() if hasattr(result, "tolist") else list(result or [])

    logger.info(
        "embed ok",
        extra={"text_len": len(text), "dimension": len(embedding_list), "duration_ms": round(elapsed * 1000, 2)},
    )
    record_cost("embed", elapsed, success=True, provider=provider, model=model)
    trace_ai_call(
        operation="embed", provider=provider, model=model,
        latency=elapsed, status="success",
        input_length=len(text), output_dimension=len(embedding_list),
    )
    return embedding_list