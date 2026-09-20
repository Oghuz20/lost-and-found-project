"""OpenTelemetry tracing for AI API calls.

This module provides tracing capabilities for AI service calls using
OpenTelemetry. It creates spans for each external AI call with relevant
attributes for monitoring and debugging.
"""

from __future__ import annotations

import os
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.trace import Status, StatusCode
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

from ..logging_config import get_logger

logger = get_logger(__name__)

# Global tracer instance
_tracer = None


def _initialize_tracer() -> None:
    """Initialize the OpenTelemetry tracer if available."""
    global _tracer

    if not OPENTELEMETRY_AVAILABLE:
        logger.debug("OpenTelemetry not available, tracing disabled")
        return

    try:
        resource = Resource.create({
            ResourceAttributes.SERVICE_NAME: "smart-lost-and-found",
            ResourceAttributes.SERVICE_VERSION: "1.0.0",
        })
        provider = TracerProvider(resource=resource)

        # Only attempt a real OTLP export if the user explicitly configured
        # an endpoint (e.g. a Jaeger/Tempo collector running via docker-compose).
        # OTLPSpanExporter() succeeds at construction time even with nothing
        # listening — the connection is lazy — so checking for the env var
        # up front is the only reliable way to avoid silent background
        # export failures/retries when no collector exists.
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        processor: SpanProcessor
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            processor = BatchSpanProcessor(otlp_exporter)
            logger.info("OpenTelemetry initialized with OTLP exporter at %s", otlp_endpoint)
        else:
            from opentelemetry.sdk.trace.export import (
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )
            console_exporter = ConsoleSpanExporter()
            processor = SimpleSpanProcessor(console_exporter)
            logger.info("OpenTelemetry initialized with console exporter (no OTEL_EXPORTER_OTLP_ENDPOINT set)")

        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(__name__)

    except Exception as e: # noqa: BLE001
        logger.warning("Failed to initialize OpenTelemetry: %s", e)
        _tracer = None

def get_tracer():
    """Get the OpenTelemetry tracer instance.

    Initializes the tracer on first call if needed.

    Returns:
        Tracer instance or None if OpenTelemetry is not available
    """
    
    if _tracer is None:
        _initialize_tracer()
    return _tracer


def trace_ai_call(
    operation: str,
    provider: str,
    model: str,
    latency: float,
    status: str,
    **attributes
) -> None:
    """Trace an AI API call with OpenTelemetry.

    Creates a span for the AI call with relevant attributes for monitoring.

    Args:
        operation: Type of operation ("describe_item", "embed")
        provider: AI provider name ("openai", "anthropic", "google")
        model: Model name used
        latency: Call latency in seconds
        status: Call status ("success", "error", "timeout")
        **attributes: Additional attributes to attach to the span
    """
    tracer = get_tracer()
    if tracer is None:
        # OpenTelemetry not available, skip tracing
        return

    try:
        with tracer.start_as_current_span(f"ai.{operation}") as span:
            # Set standard attributes
            span.set_attribute("ai.operation", operation)
            span.set_attribute("ai.provider", provider)
            span.set_attribute("ai.model", model)
            span.set_attribute("ai.latency", latency)
            span.set_attribute("ai.status", status)

            # Set additional attributes
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(f"ai.{key}", value)

            # Set span status based on call outcome
            if status == "success":
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, f"AI call failed: {status}"))

    except Exception as e: # noqa: BLE001
        logger.warning("Failed to create OpenTelemetry span: %s", e)


def trace_describe_item(
    image_path: str,
    user_text: str,
    latency: float,
    success: bool,
    provider: str = "unknown",
    model: str = "unknown",
    result: Any | None = None,
    error: str | None = None
) -> None:
    """Trace a describe_item AI call.

    Args:
        image_path: Path to the image file
        user_text: User's free-text description
        latency: Call latency in seconds
        success: Whether the call succeeded
        provider: AI provider name
        model: Model name used
        result: Result object from the call (if successful)
        error: Error message (if failed)
    """
    status = "success" if success else "error"
    attributes = {
        "image_path": image_path,
        "text_length": len(user_text) if user_text else 0,
    }

    if result and hasattr(result, 'object_class'):
        attributes.update({
            "result.object_class": getattr(result, 'object_class', None),
            "result.confidence": getattr(result, 'confidence', None),
        })

    if error:
        attributes["error.message"] = error

    trace_ai_call(
        operation="describe_item",
        provider=provider,
        model=model,
        latency=latency,
        status=status,
        **attributes
    )


def trace_embed(
    text: str,
    latency: float,
    success: bool,
    provider: str = "unknown",
    model: str = "unknown",
    embedding: Any | None = None,
    error: str | None = None
) -> None:
    """Trace an embed AI call.

    Args:
        text: Input text that was embedded
        latency: Call latency in seconds
        success: Whether the call succeeded
        provider: AI provider name
        model: Model name used
        embedding: Embedding vector result (if successful)
        error: Error message (if failed)
    """
    status = "success" if success else "error"
    attributes: dict[str, Any] = {
        "text_length": len(text) if text else 0,
    }

    if embedding is not None:
        if hasattr(embedding, '__len__'):
            attributes["embedding.dimension"] = len(embedding)
        attributes["embedding.has_value"] = True

    if error:
        attributes["error.message"] = error

    trace_ai_call(
        operation="embed",
        provider=provider,
        model=model,
        latency=latency,
        status=status,
        **attributes
    )


def is_tracing_enabled() -> bool:
    """Check if OpenTelemetry tracing is available and enabled.

    Returns:
        True if tracing is available, False otherwise
    """
    return OPENTELEMETRY_AVAILABLE and get_tracer() is not None