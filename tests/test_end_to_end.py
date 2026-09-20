"""End-to-end tests for the Smart Lost & Found system.

These tests verify the complete workflow from item registration through
matching, using the AI service with caching, retries, and validation.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai import top_k
from src.services.ai_service import describe_item, embed
from src.services.cache import get_embedding_cache
from src.validation import (
    validate_description_fields,
    validate_found_item_input,
    validate_lost_item_input,
)


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    def test_register_and_match_workflow_offline(
        self, fake_vlm, fake_embedder, sample_image
    ):
        """Test the complete workflow: register items, get descriptions, embed, match."""
        # Clear cache for clean test
        get_embedding_cache().clear()

        # Simulate registering a lost item
        lost_image_path = sample_image
        lost_user_text = "lost my black umbrella"

        # Validate input
        lost_input = validate_lost_item_input({"user_text": lost_user_text})
        assert lost_input.user_text == lost_user_text

        # Get VLM description
        lost_description = describe_item(
            lost_image_path,
            lost_input.user_text,
            vlm=fake_vlm
        )

        # Validate description
        desc_errors = validate_description_fields(lost_description)
        assert desc_errors == []

        # Get embedding for lost item
        lost_search_text = lost_description.to_search_text()
        lost_embedding = embed(lost_search_text, embedder=fake_embedder)

        # Simulate registering a found item (similar to lost item)
        found_image_path = sample_image  # Same image for simplicity in test
        found_user_text = "found black umbrella"

        # Validate input
        found_input = validate_found_item_input({"user_text": found_user_text})
        assert found_input.user_text == found_user_text

        # Get VLM description
        found_description = describe_item(
            found_image_path,
            found_input.user_text,
            vlm=fake_vlm
        )

        # Validate description
        desc_errors = validate_description_fields(found_description)
        assert desc_errors == []

        # Get embedding for found item
        found_search_text = found_description.to_search_text()
        found_embedding = embed(found_search_text, embedder=fake_embedder)

        # Verify that similar items have similar embeddings (high cosine similarity)
        # Since we're using the same image and similar text, embeddings should be similar
        import numpy as np

        # Convert to numpy arrays for cosine similarity
        lost_vec = np.array(lost_embedding)
        found_vec = np.array(found_embedding)

        # Compute cosine similarity
        cosine_sim = np.dot(lost_vec, found_vec) / (
            np.linalg.norm(lost_vec) * np.linalg.norm(found_vec)
        )

        # Should be very similar (close to 1.0) since inputs are similar
        assert cosine_sim > 0.8  # Reasonable threshold for similar items

        # Test using the top_k function as the system would
        query_vec = lost_embedding
        candidate_vecs = [found_embedding]
        

        matches = top_k(query_vec, candidate_vecs, k=1)

        assert len(matches) == 1
        assert matches[0].candidate_id == 0
        assert matches[0].score > 0.8  # High similarity score

    def test_caching_prevents_duplicate_computation(
        self, fake_vlm, fake_embedder, sample_image
    ):
        """Test that embedding cache prevents duplicate API calls."""
        # Clear cache
        get_embedding_cache().clear()

        # Track calls to the fake embedder
        original_embed = fake_embedder.embed
        call_count = 0

        def counting_embed(text):
            nonlocal call_count
            call_count += 1
            return original_embed(text)

        fake_embedder.embed = counting_embed

        try:
            # Process the same image text twice
            description1 = describe_item(sample_image, "test", vlm=fake_vlm)
            search_text1 = description1.to_search_text()
            embedding1 = embed(search_text1, embedder=fake_embedder)

            description2 = describe_item(sample_image, "test", vlm=fake_vlm)
            search_text2 = description2.to_search_text()
            embedding2 = embed(search_text2, embedder=fake_embedder)

            # Results should be identical
            assert embedding1 == embedding2

            # With caching, the embedder should only be called once
            # (first call computes, second call uses cache)
            assert call_count == 1

            # Verify cache statistics
            stats = get_embedding_cache().stats()
            assert stats['hits'] == 1   # Second call was cache hit
            assert stats['misses'] == 1 # First call was cache miss

        finally:
            # Restore original method
            fake_embedder.embed = original_embed

    def test_error_handling_and_graceful_degradation(
        self, sample_image
    ):
        """Test that the system handles errors gracefully."""
        # Clear cache
        get_embedding_cache().clear()

        # Test with a provider that consistently fails
        class FailingVLM:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                from ai.providers.base import ProviderError
                raise ProviderError("Provider unavailable")

        failing_vlm = FailingVLM()

        # The service should convert provider errors to AIServiceError after retries
        from src.services.ai_service import AIServiceError

        with pytest.raises(AIServiceError):
            describe_item(sample_image, "test", vlm=failing_vlm)

        # Test that validation catches bad inputs before they reach AI service
        # Empty user text should be caught by validation, not passed to AI
        with pytest.raises(ValidationError):  # ValidationError from pydantic
            validate_lost_item_input({"user_text": ""})

        # Whitespace-only text should also be caught
        with pytest.raises(ValidationError):  # ValidationError from pydantic
            validate_lost_item_input({"user_text": "   "})

    def test_concurrent_registration_simulation(
        self, fake_vlm, fake_embedder, sample_image
    ):
        """Simulate concurrent registration of multiple items."""
        import threading
        import time

        # Clear cache
        get_embedding_cache().clear()

        results = []
        errors = []

        def register_item(item_id: int, is_lost: bool):
            try:
                # Simulate slight variations in user text
                user_text = f"{'Lost' if is_lost else 'Found'} item {item_id}"

                # Validate input
                if is_lost:
                    validate_lost_item_input({"user_text": user_text})
                else:
                    validate_found_item_input({"user_text": user_text})

                # Get description
                description = describe_item(
                    sample_image,
                    user_text,
                    vlm=fake_vlm
                )

                # Get embedding
                search_text = description.to_search_text()
                embedding = embed(search_text, embedder=fake_embedder)

                results.append({
                    'id': item_id,
                    'type': 'lost' if is_lost else 'found',
                    'description': description,
                    'embedding': embedding
                })

            except Exception as e: # noqa: BLE001
                errors.append({'id': item_id, 'error': str(e)})

        # Create threads for concurrent registration
        threads = []
        num_items = 5

        for i in range(num_items):
            # Create lost item thread
            t1 = threading.Thread(target=register_item, args=(i, True))
            threads.append(t1)

            # Create found item thread
            t2 = threading.Thread(target=register_item, args=(i + num_items, False))
            threads.append(t2)

        # Start all threads
        for thread in threads:
            thread.start()
            # Small stagger to increase chance of concurrency
            time.sleep(0.01)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify results
        assert len(errors) == 0, f"Errors occurred during concurrent registration: {errors}"
        assert len(results) == num_items * 2  # 5 lost + 5 found = 10 items

        # Verify that we got descriptions and embeddings for all items
        for result in results:
            assert 'description' in result
            assert 'embedding' in result
            assert result['description'] is not None
            assert result['embedding'] is not None
            assert len(result['embedding']) > 0

        # Verify cache effectiveness
        stats = get_embedding_cache().stats()
        total_requests = stats['hits'] + stats['misses']
        assert total_requests == 10, f"Expected 10 total requests, got {total_requests}"
        assert stats['misses'] >= 1, f"Expected at least 1 miss, got {stats['misses']}"
        assert stats['hits'] + stats['misses'] == total_requests
        
    def test_system_performance_with_caching(
        self, fake_vlm, fake_embedder, sample_image
    ):
        # Clear cache
        get_embedding_cache().clear()



        description1 = describe_item(sample_image, "test perf", vlm=fake_vlm)
        search_text1 = description1.to_search_text()
        embedding1 = embed(search_text1, embedder=fake_embedder)

        description2 = describe_item(sample_image, "test perf", vlm=fake_vlm)
        search_text2 = description2.to_search_text()
        embedding2 = embed(search_text2, embedder=fake_embedder)

        

        # Results should be identical
        assert description1.object_class == description2.object_class
        assert embedding1 == embedding2

        # Second execution should be faster due to caching
        # (though the difference might be small with fast fakes)
        # At minimum, we can verify the cache was used
        stats = get_embedding_cache().stats()
        assert stats['hits'] >= 1  # At least one cache hit
        assert stats['misses'] >= 1  # At least one cache miss


class TestFailureInjection:
    """Test failure injection and graceful degradation."""

    def test_simulated_provider_failure_5xx(self, sample_image):
        """Test handling of simulated 5xx errors from provider."""

        class Error5xxVLM:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                from ai.providers.base import ProviderError
                raise ProviderError("500 Internal Server Error")

        error_vlm = Error5xxVLM()

        # Should retry and eventually fail with AIServiceError
        from src.services.ai_service import AIServiceError

        with pytest.raises(AIServiceError):
            describe_item(sample_image, "test", vlm=error_vlm)

        # Verify that we attempted multiple calls (retries)
        # Note: Hard to test exact count with current mock setup,
        # but we verified the error handling works in test_ai_service.py

    def test_simulated_malformed_vlm_response(self, sample_image):
        """Test handling of malformed VLM response."""

        class MalformedResponseVLM:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                # Return invalid JSON that doesn't match schema
                return '{"invalid": "response", "missing": "required_fields"}'

        malformed_vlm = MalformedResponseVLM()

        # Should retry and eventually fail with AIServiceError
        from src.services.ai_service import AIServiceError

        with pytest.raises(AIServiceError):
            describe_item(sample_image, "test", vlm=malformed_vlm)

    def test_graceful_degradation_continues_operation(self, sample_image, fake_embedder):
        """Test that failure in one operation doesn't break others."""
        from src.services.ai_service import AIServiceError

        # Clear cache
        get_embedding_cache().clear()

        # First, a successful operation
        class WorkingVLM1:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                return '{"object_class": "test1", "colors": ["red"], "confidence": 0.8}'

        working_vlm1 = WorkingVLM1()

        # This should succeed
        desc1 = describe_item(sample_image, "working", vlm=working_vlm1)
        assert desc1.object_class == "test1"
        

        # Then a failing operation
        class FailingVLM:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                from ai.providers.base import ProviderError
                raise ProviderError("Service temporarily unavailable")

        failing_vlm = FailingVLM()

        # This should fail after retries
        with pytest.raises(AIServiceError):
            describe_item(sample_image, "failing", vlm=failing_vlm)

        # Finally, another successful operation should still work
        # Finally, another successful operation should still work
        class WorkingVLM2:
            def describe(self, image_path: str, prompt: str, *, json_schema=None):
                return '{"object_class": "test2", "colors": ["blue"], "confidence": 0.8}'

        working_vlm2 = WorkingVLM2()
        desc2 = describe_item(sample_image, "working again", vlm=working_vlm2)
        assert desc2.object_class == "test2"
        
        # Call embed for both descriptions to populate the embedding cache
        embed(desc1.to_search_text(), embedder=fake_embedder)
        embed(desc2.to_search_text(), embedder=fake_embedder)

        # Cache should still be functional
        stats = get_embedding_cache().stats()
        # We had 2 successful embed calls with different texts, expecting 2 misses
        assert stats['misses'] >= 2
        assert stats['hits'] == 0

if __name__ == "__main__":
    # Allow running the test file directly for debugging
    pytest.main([__file__, "-v"])