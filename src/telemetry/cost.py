"""Cost telemetry for tracking AI API usage and expenses.

This module tracks token counts and estimated costs for AI provider calls,
enabling cost reporting and budget monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from ..logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CostRecord:
    """Record of a single AI API call with associated cost."""
    timestamp: datetime
    operation: str  # "describe_item" or "embed"
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class CostTracker:
    """Tracks AI API usage and costs over time."""

    def __init__(self) -> None:
        self._records: list[CostRecord] = []
        self._lock = Lock()
        # Pricing table (USD per 1K tokens) - these should be configurable
        # Based on typical free-tier/trial pricing as of 2024
        self._pricing: dict[str, dict[str, dict[str, float]]] = {
            "openai": {
                "gpt-4o": {"input": 0.005, "output": 0.015},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
                "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
            },
            "anthropic": {
                "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
                "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
            },
            "google": {
                "gemini-1.5-pro": {"input": 0.00125, "output": 0.00375},
                "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
                "text-embedding-004": {"input": 0.000025, "output": 0.0},
            }
        }

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count from text.

        This is a simplified estimation. In production, you'd use the
        actual tokenizer for each provider.
        """
        if not text:
            return 0
        # Very rough approximation: 1 token ≈ 4 characters for English
        return max(1, len(text) // 4)

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate cost in USD based on token usage and provider pricing."""
        provider_pricing = self._pricing.get(provider.lower(), {})
        model_pricing = provider_pricing.get(model.lower(), {})

        if not model_pricing:
            # Unknown model/provider - use a default estimate
            logger.warning(
                "Unknown provider/model for cost calculation: %s/%s",
                provider, model
            )
            # Default estimate: $0.001 per 1K tokens
            return (input_tokens + output_tokens) * 0.001 / 1000

        input_cost = (input_tokens / 1000) * model_pricing.get("input", 0.0)
        output_cost = (output_tokens / 1000) * model_pricing.get("output", 0.0)
        return input_cost + output_cost

    def record_call(
        self,
        operation: str,
        provider: str,
        model: str,
        input_text: str,
        output_text: str | None = None,
        latency_ms: float = 0.0,
        success: bool = True,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """Record an AI API call for cost tracking.

        Args:
            operation: Type of operation ("describe_item", "embed")
            provider: AI provider name ("openai", "anthropic", "google")
            model: Model name used
            input_text: Input text to the API call
            output_text: Output text from the API call (if applicable)
            latency_ms: Call latency in milliseconds
            success: Whether the call succeeded
            metadata: Additional metadata to store with the record
        """
        input_tokens = self._estimate_tokens(input_text)
        output_tokens = self._estimate_tokens(output_text) if output_text else 0
        total_tokens = input_tokens + output_tokens
        cost_usd = self._calculate_cost(provider, model, input_tokens, output_tokens)

        record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation=operation,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            metadata=metadata or {}
        )

        with self._lock:
            self._records.append(record)

        logger.debug(
            "Recorded AI call: %s %s/%s - %d tokens, $%.6f, %.2fms",
            operation, provider, model, total_tokens, cost_usd, latency_ms
        )

    def get_records_since(self, hours: int = 24) -> list[CostRecord]:
        """Get records from the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of CostRecord objects from the specified time period
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self._lock:
            return [
                record for record in self._records
                if record.timestamp >= cutoff_time
            ]

    def get_total_cost(self, hours: int = 24) -> float:
        """Get total cost in USD for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Total cost in USD
        """
        records = self.get_records_since(hours)
        return sum(record.cost_usd for record in records)

    def get_token_usage(self, hours: int = 24) -> dict[str, int]:
        """Get token usage statistics for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with input_tokens, output_tokens, total_tokens
        """
        records = self.get_records_since(hours)
        return {
            "input_tokens": sum(r.input_tokens for r in records),
            "output_tokens": sum(r.output_tokens for r in records),
            "total_tokens": sum(r.total_tokens for r in records)
        }

    def get_call_count(self, hours: int = 24) -> dict[str, int]:
        """Get API call counts for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with total, successful, and failed call counts
        """
        records = self.get_records_since(hours)
        return {
            "total": len(records),
            "successful": sum(1 for r in records if r.success),
            "failed": sum(1 for r in records if not r.success)
        }

    def clear_old_records(self, hours: int = 168) -> int:  # Default 1 week
        """Clear records older than N hours.

        Args:
            hours: Number of hours to keep records for

        Returns:
            Number of records removed
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self._lock:
            initial_count = len(self._records)
            self._records = [
                record for record in self._records
                if record.timestamp >= cutoff_time
            ]
            removed = initial_count - len(self._records)
            logger.info("Cleared %d old cost records (older than %d hours)", removed, hours)
            return removed


# Global cost tracker instance
_cost_tracker = CostTracker()


def record_cost(
    operation: str,
    latency_seconds: float,
    success: bool = True,
    provider: str = "unknown",
    model: str = "unknown",
    input_text: str = "",
    output_text: str | None = None,
    metadata: dict[str, Any] | None = None
) -> None:
    """Record cost information for an AI call.

    This is the main interface for recording AI call costs.

    Args:
        operation: Type of operation ("describe_item", "embed")
        latency_seconds: Call latency in seconds
        success: Whether the call succeeded
        provider: AI provider name
        model: Model name used
        input_text: Input text to the API call
        output_text: Output text from the API call
        metadata: Additional metadata
    """
    _cost_tracker.record_call(
        operation=operation,
        provider=provider,
        model=model,
        input_text=input_text,
        output_text=output_text,
        latency_ms=latency_seconds * 1000,
        success=success,
        metadata=metadata
    )


def get_cost_report(hours: int = 24) -> str:
    """Generate a formatted cost report for the last N hours.

    Args:
        hours: Number of hours to look back

    Returns:
        Formatted string report
    """
    records = _cost_tracker.get_records_since(hours)
    if not records:
        return f"No AI API calls recorded in the last {hours} hours."

    total_cost = _cost_tracker.get_total_cost(hours)
    token_usage = _cost_tracker.get_token_usage(hours)
    call_counts = _cost_tracker.get_call_count(hours)

    # Group by operation and provider for detailed breakdown
    breakdown: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        if record.operation not in breakdown:
            breakdown[record.operation] = {}
        if record.provider not in breakdown[record.operation]:
            breakdown[record.operation][record.provider] = {
                "model": record.model,
                "count": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "total_latency_ms": 0.0
            }

        group = breakdown[record.operation][record.provider]
        group["count"] += 1
        group["total_tokens"] += record.total_tokens
        group["total_cost"] += record.cost_usd
        group["total_latency_ms"] += record.latency_ms

    # Format the report
    lines = [
        f"AI Usage Cost Report (Last {hours} hours)",
        "=" * 50,
        f"Total Calls: {call_counts['total']} ",
        f"(Successful: {call_counts['successful']}, Failed: {call_counts['failed']})",
        f"Total Tokens: {token_usage['total_tokens']:,} ",
        f"(Input: {token_usage['input_tokens']:,}, Output: {token_usage['output_tokens']:,})",
        f"Total Cost: ${total_cost:.6f}",
        "",
        "Breakdown by Operation and Provider:",
        "-" * 40
    ]

    for operation, providers in breakdown.items():
        lines.append(f"{operation}:")
        for provider, stats in providers.items():
            avg_latency = stats["total_latency_ms"] / stats["count"] if stats["count"] > 0 else 0
            lines.append(
                f"  {provider} ({stats['model']}): "
                f"{stats['count']} calls, {stats['total_tokens']:,} tokens, "
                f"${stats['total_cost']:.6f}, {avg_latency:.1f}ms avg latency"
            )
        lines.append("")

    return "\n".join(lines)


def get_cost_tracker() -> CostTracker:
    """Get the global cost tracker instance.

    Returns:
        The global CostTracker instance
    """
    return _cost_tracker