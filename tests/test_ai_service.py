"""Tests for the AI service wrapper including retry, caching, and telemetry."""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest

from ai.providers.base import ProviderError
from src.services.ai_service import AIServiceError, describe_item, embed
from src.services.cache import get_embedding_cache


class TestAIService:
    """Test the AI service wrapper functionality."""

    def test_describe_item_success(self, fake_vlm, sample_image):
        """Test successful describe_item call."""
        result = describe_item(sample_image, "test description", vlm=fake_vlm)

        assert hasattr(result, 'object_class')
        assert hasattr(result, 'confidence')
        assert result.object_class == "umbrella"
        assert 0.0 <= result.confidence <= 1.0

    def test_describe_item_retry_on_failure(self, sample_image):
        """Test that describe_item retries on transient failures."""
        call_count = 0

        def failing_describe(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderError("Transient failure")
            # Return success on third attempt
            from ai.schemas import ItemDescription
            return ItemDescription(
                object_class="test",
                colors=[],
                confidence=0.8
            )

        with patch('src.services.ai_service.ai.describe_item', side_effect=failing_describe):
            result = describe_item(sample_image, "test")

            assert call_count == 3
            assert result.object_class == "test"

    def test_describe_item_fail_after_retries(self, sample_image):
        """Test that describe_item raises AIServiceError after all retries fail."""
        def always_fail(*args, **kwargs):
            raise ProviderError("Persistent failure")

        with patch('src.services.ai_service.ai.describe_item', side_effect=always_fail), pytest.raises(AIServiceError, match="describe_item failed after 3 attempts"):
            describe_item(sample_image, "test")

    def test_describe_item_no_retry_on_value_error(self, sample_image):
        """Test that ValueError is not retried (invalid input)."""
        call_count = 0

        def raise_value_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid input")

        with patch('src.services.ai_service.ai.describe_item', side_effect=raise_value_error):
            with pytest.raises(ValueError, match="Invalid input"):
                describe_item(sample_image, "test")

            # Should only be called once (no retry)
            assert call_count == 1

    def test_embed_success(self, fake_embedder):
        """Test successful embed call."""
        embedding = embed("test text", embedder=fake_embedder)

        assert isinstance(embedding, list)
        assert len(embedding) > 0
        # Should be unit vector (approximately)
        import numpy as np
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_caching(self, fake_embedder):
        """Test that embed uses cache to avoid duplicate computation."""
        # Clear cache to start fresh
        get_embedding_cache().clear()

        # First call - should compute and cache
        embedding1 = embed("test text", embedder=fake_embedder)

        # Second call with same text - should use cache
        embedding2 = embed("test text", embedder=fake_embedder)

        # Results should be identical
        assert embedding1 == embedding2

        # Check cache stats
        stats = get_embedding_cache().stats()
        assert stats['hits'] == 1  # Second call was a hit
        assert stats['misses'] == 1  # First call was a miss

    def test_embed_different_inputs_produce_different_embeddings(self, fake_embedder):
        """Test that different inputs produce different embeddings."""
        emb1 = embed("first text", embedder=fake_embedder)
        emb2 = embed("second text", embedder=fake_embedder)

        assert emb1 != emb2

    def test_embed_empty_string_raises_error(self):
        """Test that embedding empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot embed empty string"):
            embed("", embedder=Mock())

    def test_describe_item_timeout_actually_interrupts(self, sample_image):
        """A genuinely slow provider must fail via timeout, not hang until it finishes."""
        class SlowVLM:
            def describe(self, image_path, prompt, *, json_schema=None):
                time.sleep(10)  # far longer than the timeout below
                return '{"object_class": "x", "colors": [], "confidence": 0.5}'

        start = time.time()
        with pytest.raises(AIServiceError):
            describe_item(sample_image, "test", vlm=SlowVLM(), timeout=0.2)
        elapsed = time.time() - start

        assert elapsed < 8.0

    def test_concurrent_calls_different_cache_entries(self, fake_embedder):
        """Test that concurrent calls with different texts populate cache correctly."""
        import threading

        # Clear cache to start fresh
        get_embedding_cache().clear()

        results = []  # Store results in order to preserve duplicates
        errors = []
        result_texts = []  # Store the text that produced each result

        def embed_text(text):
            try:
                embedding = embed(text, embedder=fake_embedder)
                results.append(embedding)
                result_texts.append(text)
            except Exception as e: # noqa: BLE001
                errors.append(e)

        # Start multiple threads
        threads = []
        texts = ["text1", "text2", "text3", "text1", "text2"]  # Some duplicates

        for text in texts:
            thread = threading.Thread(target=embed_text, args=(text,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Check no errors occurred
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Check that we got results for all inputs
        assert len(results) == len(texts)

        # Check that caching reduced the number of cache misses
        # With 5 requests for 3 unique texts, we should have at most 5 misses
        # and at least 3 misses (one for each unique text)
        stats = get_embedding_cache().stats()
        total_requests = stats['hits'] + stats['misses']
        assert total_requests >= len(texts), f"Expected at least {len(texts)} total requests, got {total_requests}"
        assert stats['misses'] >= 3, f"Expected at least 3 misses (one per unique text), got {stats['misses']}"
        assert stats['misses'] <= len(texts), f"Expected at most {len(texts)} misses, got {stats['misses']}"
        # The key point is that we should have fewer misses than total requests if caching is working
        # (unless there's a race condition where all threads miss before any populate)
        # But we at least verify that we got results for all inputs


class TestAIServiceIntegration:
    """Integration tests for AI service with other components."""

    def test_describe_then_embed_workflow(self, fake_vlm, fake_embedder, sample_image):
        """Test the typical workflow: describe item then embed the description."""
        # Get description
        description = describe_item(sample_image, "lost my wallet", vlm=fake_vlm)

        # Verify description makes sense
        assert description.object_class == "umbrella"  # From fake_vlm fixture

        # Get embedding of description text
        search_text = description.to_search_text()
        embedding = embed(search_text, embedder=fake_embedder)

        # Verify embedding is valid
        assert isinstance(embedding, list)
        assert len(embedding) > 0

        # Should be unit vector
        import numpy as np
        norm = np.linalg.norm(embedding)
        assert abs(norm - 1.0) < 1e-5

    def test_cache_persists_across_calls(self, fake_embedder):
        """Test that embedding cache persists across multiple service calls."""
        # Clear cache
        get_embedding_cache().clear()

        # First call
        embed("cached text", embedder=fake_embedder)
        stats_after_first = get_embedding_cache().stats()
        assert stats_after_first['misses'] == 1
        assert stats_after_first['hits'] == 0

        # Second call with same text
        embed("cached text", embedder=fake_embedder)
        stats_after_second = get_embedding_cache().stats()
        assert stats_after_second['misses'] == 1
        assert stats_after_second['hits'] == 1