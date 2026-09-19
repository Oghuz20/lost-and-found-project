"""Tests for telemetry functionality including cost tracking and tracing."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from src.telemetry.cost import (
    CostRecord,
    CostTracker,
    get_cost_report,
    record_cost,
)
from src.telemetry.tracing import (
    is_tracing_enabled,
    trace_ai_call,
    trace_describe_item,
    trace_embed,
)


@pytest.fixture(autouse=True)
def _no_otlp_endpoint(monkeypatch):
    """Ensure tests never attempt a real OTLP export, regardless of the
    host machine's environment."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

class TestCostTracker:
    """Test the CostTracker class."""

    def test_cost_tracker_initialization(self):
        """Test that CostTracker initializes correctly."""
        tracker = CostTracker()
        assert tracker._records == []
        assert len(tracker._pricing) > 0  # Should have pricing data

    def test_record_call_basic(self):
        """Test recording a basic AI call."""
        tracker = CostTracker()

        tracker.record_call(
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_text="Hello world",
            output_text="Hello world description",
            latency_ms=100.0,
            success=True
        )

        assert len(tracker._records) == 1
        record = tracker._records[0]
        assert record.operation == "describe_item"
        assert record.provider == "openai"
        assert record.model == "gpt-4o"
        assert record.latency_ms == 100.0
        assert record.success is True
        assert record.input_tokens > 0
        assert record.output_tokens > 0
        assert record.total_tokens == record.input_tokens + record.output_tokens
        assert record.cost_usd >= 0

    def test_record_call_failure(self):
        """Test recording a failed AI call."""
        tracker = CostTracker()

        tracker.record_call(
            operation="embed",
            provider="anthropic",
            model="claude-3-haiku-20240307",
            input_text="Test text",
            latency_ms=50.0,
            success=False
        )

        assert len(tracker._records) == 1
        record = tracker._records[0]
        assert record.operation == "embed"
        assert record.success is False

    def test_get_records_since(self):
        """Test getting records from the last N hours."""
        tracker = CostTracker()

        # Record an old record (simulate by manually setting timestamp)
        old_record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=0.001,
            latency_ms=100.0,
            success=True
        )

        # Record a recent record
        recent_record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="embed",
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=20,
            output_tokens=0,
            total_tokens=20,
            cost_usd=0.0005,
            latency_ms=50.0,
            success=True
        )

        tracker._records = [old_record, recent_record]

        # Get records from last 24 hours
        recent_records = tracker.get_records_since(hours=24)
        assert len(recent_records) == 1
        assert recent_records[0].operation == "embed"

        # Get records from last 30 hours (should include both)
        all_records = tracker.get_records_since(hours=30)
        assert len(all_records) == 2

    def test_get_total_cost(self):
        """Test calculating total cost."""
        tracker = CostTracker()

        # Add two records with known costs
        record1 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            latency_ms=100.0,
            success=True
        )

        record2 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="embed",
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=200,
            output_tokens=0,
            total_tokens=200,
            cost_usd=0.0005,
            latency_ms=50.0,
            success=True
        )

        tracker._records = [record1, record2]

        total_cost = tracker.get_total_cost(hours=24)
        assert abs(total_cost - 0.0015) < 1e-6  # 0.001 + 0.0005

    def test_get_token_usage(self):
        """Test getting token usage statistics."""
        tracker = CostTracker()

        record1 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            latency_ms=100.0,
            success=True
        )

        record2 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="embed",
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=200,
            output_tokens=0,
            total_tokens=200,
            cost_usd=0.0005,
            latency_ms=50.0,
            success=True
        )

        tracker._records = [record1, record2]

        usage = tracker.get_token_usage(hours=24)
        assert usage["input_tokens"] == 300  # 100 + 200
        assert usage["output_tokens"] == 50   # 50 + 0
        assert usage["total_tokens"] == 350   # 150 + 200

    def test_get_call_count(self):
        """Test getting API call counts."""
        tracker = CostTracker()

        record1 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            latency_ms=100.0,
            success=True
        )

        record2 = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="embed",
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=200,
            output_tokens=0,
            total_tokens=200,
            cost_usd=0.0005,
            latency_ms=50.0,
            success=False  # Failed call
        )

        tracker._records = [record1, record2]

        counts = tracker.get_call_count(hours=24)
        assert counts["total"] == 2
        assert counts["successful"] == 1
        assert counts["failed"] == 1

    def test_clear_old_records(self):
        """Test clearing old records."""
        tracker = CostTracker()

        # Add old and recent records
        old_record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cost_usd=0.001,
            latency_ms=100.0,
            success=True
        )

        recent_record = CostRecord(
            timestamp=datetime.now(timezone.utc),
            operation="embed",
            provider="openai",
            model="text-embedding-3-small",
            input_tokens=20,
            output_tokens=0,
            total_tokens=20,
            cost_usd=0.0005,
            latency_ms=50.0,
            success=True
        )

        tracker._records = [old_record, recent_record]

        # Clear records older than 24 hours
        cleared = tracker.clear_old_records(hours=24)
        assert cleared == 1  # One old record cleared
        assert len(tracker._records) == 1  # Only recent record remains
        assert tracker._records[0].operation == "embed"

    def test_record_cost_function(self):
        """Test the record_cost convenience function."""
        with patch('src.telemetry.cost._cost_tracker') as mock_tracker:
            record_cost(
                operation="describe_item",
                latency_seconds=1.5,
                success=True,
                provider="google",
                model="gemini-1.5-pro",
                input_text="Test input",
                output_text="Test output"
            )

            # Verify the tracker's record_call method was called
            mock_tracker.record_call.assert_called_once()
            _, kwargs = mock_tracker.record_call.call_args
            assert kwargs["operation"] == "describe_item"
            assert kwargs["provider"] == "google"
            assert kwargs["model"] == "gemini-1.5-pro"
            assert kwargs["input_text"] == "Test input"
            assert kwargs["output_text"] == "Test output"
            assert kwargs["latency_ms"] == 1500.0  # 1.5 seconds * 1000
            assert kwargs["success"] is True

    def test_get_cost_report_empty(self):
        """Test getting cost report when no records exist."""
        with patch('src.telemetry.cost._cost_tracker') as mock_tracker:
            mock_tracker.get_records_since.return_value = []

            report = get_cost_report(hours=24)
            assert "No AI API calls recorded" in report
            assert "24 hours" in report

    def test_get_cost_report_with_data(self):
        """Test getting cost report with sample data."""
        from datetime import datetime

        with patch('src.telemetry.cost._cost_tracker') as mock_tracker:
            # Mock some records
            mock_records = [
                CostRecord(
                    timestamp=datetime.now(timezone.utc),
                    operation="describe_item",
                    provider="openai",
                    model="gpt-4o",
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                    cost_usd=0.001,
                    latency_ms=100.0,
                    success=True
                ),
                CostRecord(
                    timestamp=datetime.now(timezone.utc),
                    operation="embed",
                    provider="openai",
                    model="text-embedding-3-small",
                    input_tokens=200,
                    output_tokens=0,
                    total_tokens=200,
                    cost_usd=0.0005,
                    latency_ms=50.0,
                    success=True
                )
            ]
            mock_tracker.get_records_since.return_value = mock_records
            mock_tracker.get_total_cost.return_value = 0.0015
            mock_tracker.get_token_usage.return_value = {
                "input_tokens": 300,
                "output_tokens": 50,
                "total_tokens": 350
            }
            mock_tracker.get_call_count.return_value = {
                "total": 2,
                "successful": 2,
                "failed": 0
            }

            report = get_cost_report(hours=24)
            assert "AI Usage Cost Report" in report
            assert "Last 24 hours" in report
            assert "Total Calls: 2" in report
            assert "Total Cost: $0.0015" in report
            assert "describe_item:" in report
            assert "embed:" in report


class TestTracing:
    """Test OpenTelemetry tracing functionality."""

    def test_is_tracing_enabled_when_not_available(self):
        """Test is_tracing_enabled when OpenTelemetry is not installed."""
        # This test runs in an environment where we don't know if OTel is available
        # The function should return a boolean
        result = is_tracing_enabled()
        assert isinstance(result, bool)

    @patch('src.telemetry.tracing.OPENTELEMETRY_AVAILABLE', False)
    def test_trace_functions_noop_when_otel_not_available(self):
        """Test that tracing functions are no-ops when OTel not available."""
        # These should not raise exceptions
        trace_ai_call(
            operation="describe_item",
            provider="openai",
            model="gpt-4o",
            latency=1.0,
            status="success"
        )

        trace_describe_item(
            image_path="/test/image.jpg",
            user_text="test",
            latency=1.0,
            success=True
        )

        trace_embed(
            text="test text",
            latency=0.5,
            success=True
        )

        # Should return False when OTel not available
        assert is_tracing_enabled() is False

    def test_trace_ai_call_sets_attributes(self):
        """Test that trace_ai_call sets the correct attributes."""
        # Mock the tracer to capture what attributes are set
        with patch('src.telemetry.tracing.get_tracer') as mock_get_tracer:
            mock_tracer = Mock()
            mock_context_manager = Mock()
            mock_span = Mock()

            # Set up the context manager mock properly
            mock_tracer.start_as_current_span.return_value = mock_context_manager
            mock_context_manager.__enter__ = Mock(return_value=mock_span)
            mock_context_manager.__exit__ = Mock(return_value=None)

            mock_get_tracer.return_value = mock_tracer

            trace_ai_call(
                operation="describe_item",
                provider="anthropic",
                model="claude-3-5-sonnet-20241022",
                latency=1.5,
                status="success",
                text_length=10,
                result_confidence=0.85
            )

            # Verify span was created
            mock_tracer.start_as_current_span.assert_called_once_with("ai.describe_item")

            # Verify attributes were set
            calls = mock_span.set_attribute.call_args_list
            call_dict = {call[0][0]: call[0][1] for call in calls}

            assert call_dict["ai.operation"] == "describe_item"
            assert call_dict["ai.provider"] == "anthropic"
            assert call_dict["ai.model"] == "claude-3-5-sonnet-20241022"
            assert call_dict["ai.latency"] == 1.5
            assert call_dict["ai.status"] == "success"
            assert call_dict["ai.text_length"] == 10
            assert call_dict["ai.result_confidence"] == 0.85

            # Verify status was set
            mock_span.set_status.assert_called_once()

    def test_trace_describe_item_integration(self):
        """Test trace_describe_item function."""
        with patch('src.telemetry.tracing.trace_ai_call') as mock_trace:
            trace_describe_item(
                image_path="/lost/umbrella.jpg",
                user_text="Lost my black umbrella",
                latency=2.3,
                success=True,
                provider="openai",
                model="gpt-4o",
                result=Mock(object_class="umbrella", confidence=0.9),
                error=None
            )

            mock_trace.assert_called_once()
            _, kwargs = mock_trace.call_args
            assert kwargs["operation"] == "describe_item"
            assert kwargs["provider"] == "openai"
            assert kwargs["model"] == "gpt-4o"
            assert kwargs["latency"] == 2.3
            assert kwargs["status"] == "success"
            assert kwargs["image_path"] == "/lost/umbrella.jpg"
            assert kwargs["text_length"] == 22  # Length of user_text
            assert kwargs["result.object_class"] == "umbrella"
            assert kwargs["result.confidence"] == 0.9

    def test_trace_embed_integration(self):
        """Test trace_embed function."""
        with patch('src.telemetry.tracing.trace_ai_call') as mock_trace:
            trace_embed(
                text="Black umbrella with bent rib",
                latency=0.8,
                success=True,
                provider="openai",
                model="text-embedding-3-small",
                embedding=[0.1, 0.2, 0.3],  # Mock embedding
                error=None
            )

            mock_trace.assert_called_once()
            _, kwargs = mock_trace.call_args
            assert kwargs["operation"] == "embed"
            assert kwargs["provider"] == "openai"
            assert kwargs["model"] == "text-embedding-3-small"
            assert kwargs["latency"] == 0.8
            assert kwargs["status"] == "success"
            assert kwargs["text_length"] == 28  # Length of text
            assert kwargs["embedding.has_value"] is True
            assert kwargs["embedding.dimension"] == 3

    def test_trace_embed_error(self):
        """Test trace_embed with error."""
        with patch('src.telemetry.tracing.trace_ai_call') as mock_trace:
            trace_embed(
                text="test",
                latency=0.5,
                success=False,
                provider="openai",
                model="text-embedding-3-small",
                embedding=None,
                error="API timeout"
            )

            mock_trace.assert_called_once()
            _, kwargs = mock_trace.call_args
            assert kwargs["operation"] == "embed"
            assert kwargs["status"] == "error"
            assert kwargs["error.message"] == "API timeout"


if __name__ == "__main__":
    # Allow running the test file directly for debugging
    pytest.main([__file__, "-v"])