"""Tests for input validation functionality."""

from __future__ import annotations

import pytest

from src.validation import (
    validate_lost_item_input,
    validate_found_item_input,
    validate_search_matches_input,
    validate_description_fields,
    safe_json_loads,
    extract_user_text_from_request,
    LostItemInput,
    FoundItemInput,
    SearchMatchesInput
)
from ai.schemas import ItemDescription


class TestValidationModels:
    """Test Pydantic validation models."""

    def test_lost_item_input_valid(self):
        """Test valid lost item input."""
        data = {"user_text": "Lost my black umbrella"}
        validated = validate_lost_item_input(data)
        assert validated.user_text == "Lost my black umbrella"

    def test_lost_item_input_whitespace_stripped(self):
        """Test that whitespace is stripped from user text."""
        data = {"user_text": "  Lost my umbrella  "}
        validated = validate_lost_item_input(data)
        assert validated.user_text == "Lost my umbrella"

    def test_lost_item_input_empty_fails(self):
        """Test that empty user text fails validation."""
        data = {"user_text": ""}
        with pytest.raises(Exception):  # ValidationError
            validate_lost_item_input(data)

        data = {"user_text": "   "}
        with pytest.raises(Exception):  # ValidationError
            validate_lost_item_input(data)

    def test_lost_item_input_too_long_fails(self):
        """Test that overly long user text fails."""
        data = {"user_text": "x" * 501}
        with pytest.raises(Exception):  # ValidationError
            validate_lost_item_input(data)

    def test_found_item_input_valid(self):
        """Test valid found item input."""
        data = {"user_text": "Found green backpack"}
        validated = validate_found_item_input(data)
        assert validated.user_text == "Found green backpack"

    def test_search_matches_input_valid(self):
        """Test valid search matches input."""
        data = {"k": 5}
        validated = validate_search_matches_input(data)
        assert validated.k == 5

    def test_search_matches_input_default(self):
        """Test default value for k."""
        data = {}
        validated = validate_search_matches_input(data)
        assert validated.k == 3

    def test_search_matches_input_too_low_fails(self):
        """Test that k < 1 fails."""
        data = {"k": 0}
        with pytest.raises(Exception):  # ValidationError
            validate_search_matches_input(data)

    def test_search_matches_input_too_high_fails(self):
        """Test that k > 20 fails."""
        data = {"k": 25}
        with pytest.raises(Exception):  # ValidationError
            validate_search_matches_input(data)


class TestDescriptionFieldValidation:
    """Test validation of ItemDescription fields."""

    def test_valid_description_passes(self):
        """Test that a valid description passes validation."""
        desc = ItemDescription(
            object_class="umbrella",
            colors=["black"],
            brand="Fulton",
            distinguishing_marks=["bent rib"],
            location_hints=["library entrance"],
            confidence=0.85
        )
        errors = validate_description_fields(desc)
        assert errors == []

    def test_description_empty_object_class_after_strip_fails(self):
        """Test that object_class with only whitespace fails validation."""
        # Create a valid description first
        desc = ItemDescription(
            object_class="valid",
            colors=["black"],
            confidence=0.8
        )
        # Manually set invalid object_class to test our validation
        desc.object_class = "   "  # Whitespace only
        errors = validate_description_fields(desc)
        assert any("object_class" in err.lower() for err in errors)

    def test_description_invalid_confidence_fails(self):
        """Test that invalid confidence values fail."""
        # Note: Pydantic already validates confidence range, so these
        # constructions will fail before reaching our validation function.
        # We test the validation logic directly for completeness.

        # Too low - should fail our validation
        from ai.schemas import ItemDescription
        # Create a valid description first, then test validation logic
        desc = ItemDescription(
            object_class="umbrella",
            colors=["black"],
            confidence=0.8  # Valid
        )
        # Temporarily set invalid confidence to test our validation
        desc.confidence = -0.1
        errors = validate_description_fields(desc)
        assert any("confidence" in err.lower() for err in errors)

        # Too high - should fail our validation
        desc.confidence = 1.5
        errors = validate_description_fields(desc)
        assert any("confidence" in err.lower() for err in errors)

    def test_description_non_string_colors_fails(self):
        """Test that non-string colors in the list fail validation."""
        desc = ItemDescription(
            object_class="umbrella",
            colors=["black"],
            confidence=0.8
        )
        # Temporarily set invalid colors to test our validation
        desc.colors = ["black", 123]  # Integer in list
        errors = validate_description_fields(desc)
        assert any("colors" in err.lower() and "string" in err.lower() for err in errors)

    def test_description_empty_string_colors_fails(self):
        """Test that empty string colors in the list fail validation."""
        desc = ItemDescription(
            object_class="umbrella",
            colors=["black"],
            confidence=0.8
        )
        # Temporarily set colors with empty string to test our validation
        desc.colors = ["black", ""]  # Empty string
        errors = validate_description_fields(desc)
        assert any("colors" in err.lower() and "empty" in err.lower() for err in errors)

    def test_description_optional_fields_none_ok(self):
        """Test that optional fields can be None or empty."""
        # Create a valid description first
        desc = ItemDescription(
            object_class="umbrella",
            colors=["black"],
            confidence=0.8
        )
        # Set optional fields to test our validation
        desc.brand = None  # This should be allowed
        desc.distinguishing_marks = []  # Empty list instead of None
        desc.location_hints = []  # Empty list instead of None
        errors = validate_description_fields(desc)
        assert errors == []


class TestUtilityFunctions:
    """Test utility validation functions."""

    def test_safe_json_loads_valid(self):
        """Test safe_json_loads with valid JSON."""
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_safe_json_loads_invalid_returns_empty_dict(self):
        """Test that invalid JSON returns empty dict."""
        result = safe_json_loads('{"key": "value"')
        assert result == {}

        result = safe_json_loads('not json at all')
        assert result == {}

        result = safe_json_loads('')
        assert result == {}

    def test_extract_user_text_from_request_string(self):
        """Test extracting user text from string."""
        result = extract_user_text_from_request("Lost my wallet")
        assert result == "Lost my wallet"

        result = extract_user_text_from_request("   ")
        assert result is None  # Whitespace only

        result = extract_user_text_from_request("")
        assert result is None  # Empty string

    def test_extract_user_text_from_request_dict(self):
        """Test extracting user text from dictionary."""
        # Test various field names
        for key in ['user_text', 'text', 'description', 'description_text']:
            data = {key: "Found my keys"}
            result = extract_user_text_from_request(data)
            assert result == "Found my keys"

        # Test whitespace stripping
        data = {'user_text': '  Found keys  '}
        result = extract_user_text_from_request(data)
        assert result == "Found keys"

        # Test empty/whitespace values
        data = {'user_text': ''}
        result = extract_user_text_from_request(data)
        assert result is None

        data = {'user_text': '   '}
        result = extract_user_text_from_request(data)
        assert result is None

        # Test missing key
        data = {'other_field': 'value'}
        result = extract_user_text_from_request(data)
        assert result is None

        # Test non-string value
        data = {'user_text': 123}
        result = extract_user_text_from_request(data)
        assert result is None

    def test_extract_user_text_from_request_other_types(self):
        """Test extracting from other types returns None."""
        assert extract_user_text_from_request(123) is None
        assert extract_user_text_from_request(['list']) is None
        assert extract_user_text_from_request({'nested': {'dict'}}) is None