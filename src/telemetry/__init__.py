"""Telemetry package for Smart Lost & Found.

This package contains modules for cost tracking and OpenTelemetry tracing.
"""
from __future__ import annotations

from .cost import get_cost_report, record_cost
from .tracing import (
    trace_ai_call,
    trace_describe_item,
    trace_embed,
    is_tracing_enabled
)

__all__ = [
    "get_cost_report",
    "record_cost",
    "trace_ai_call",
    "trace_describe_item",
    "trace_embed",
    "is_tracing_enabled"
]