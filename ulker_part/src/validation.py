"""Input validation for API and CLI boundaries.

This module provides validation functions for checking user inputs beyond
basic file type and size checks (which are handled in the storage layer).
It ensures that malformed JSON, missing fields, and invalid data types
result in clean error messages rather than stack traces.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from ai.schemas import ItemDescription


class LostItemInput(BaseModel):
    """Input model for registering a lost item."""
    user_text: str = Field(..., min_length=1, max_length=500,
                           description="User's free-text description of the lost item")

    @field_validator('user_text')
    @classmethod
    def user_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('User text must not be empty or only whitespace')
        return v.strip()


class FoundItemInput(BaseModel):
    """Input model for registering a found item."""
    user_text: str = Field(..., min_length=1, max_length=500,
                           description="User's free-text description of the found item")

    @field_validator('user_text')
    @classmethod
    def user_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('User text must not be empty or only whitespace')
        return v.strip()


class SearchMatchesInput(BaseModel):
    """Input model for searching matches."""
    k: int = Field(default=3, ge=1, le=20,
                   description="Number of top matches to return")

    @field_validator('k')
    @classmethod
    def k_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError('k must be at least 1')
        return v


def validate_lost_item_input(data: Dict[str, Any]) -> LostItemInput:
    """Validate input for registering a lost item.

    Args:
        data: Dictionary containing input data

    Returns:
        Validated LostItemInput model

    Raises:
        ValidationError: If input is invalid
    """
    return LostItemInput(**data)


def validate_found_item_input(data: Dict[str, Any]) -> FoundItemInput:
    """Validate input for registering a found item.

    Args:
        data: Dictionary containing input data

    Returns:
        Validated FoundItemInput model

    Raises:
        ValidationError: If input is invalid
    """
    return FoundItemInput(**data)


def validate_search_matches_input(data: Dict[str, Any]) -> SearchMatchesInput:
    """Validate input for searching matches.

    Args:
        data: Dictionary containing input data

    Returns:
        Validated SearchMatchesInput model

    Raises:
        ValidationError: If input is invalid
    """
    return SearchMatchesInput(**data)


def validate_description_fields(description: ItemDescription) -> List[str]:
    """Validate that an ItemDescription has reasonable values.

    Args:
        description: ItemDescription to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Check object_class is not empty
    if not description.object_class or not description.object_class.strip():
        errors.append("object_class must not be empty")

    # Check confidence is in valid range
    if not 0.0 <= description.confidence <= 1.0:
        errors.append(f"confidence must be between 0.0 and 1.0, got {description.confidence}")

    # Check colors is a list of strings
    if not isinstance(description.colors, list):
        errors.append("colors must be a list")
    else:
        for i, color in enumerate(description.colors):
            if not isinstance(color, str):
                errors.append(f"colors[{i}] must be a string, got {type(color).__name__}")
            elif not color.strip():
                errors.append(f"colors[{i}] must not be empty or only whitespace")

    # Check optional string fields are actually strings if present
    optional_string_fields = ['brand', 'distinguishing_marks', 'location_hints']
    for field_name in optional_string_fields:
        field_value = getattr(description, field_name, None)
        if field_value is not None:
            if isinstance(field_value, list):
                # For list fields, check each element
                for i, item in enumerate(field_value):
                    if not isinstance(item, str):
                        errors.append(f"{field_name}[{i}] must be a string, got {type(item).__name__}")
            elif not isinstance(field_value, str):
                errors.append(f"{field_name} must be a string or list of strings, got {type(field_value).__name__}")

    return errors


def safe_json_loads(json_string: str) -> Dict[str, Any]:
    """Safely parse JSON string, returning empty dict on failure.

    Args:
        json_string: JSON string to parse

    Returns:
        Parsed dictionary or empty dict if parsing fails
    """
    try:
        import json
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError):
        return {}


def extract_user_text_from_request(request_data: Any) -> Optional[str]:
    """Extract user text from various request formats.

    Args:
        request_data: Request data in various possible formats

    Returns:
        Extracted user text string, or None if not found/invalid
    """
    # Handle direct string
    if isinstance(request_data, str):
        return request_data.strip() if request_data.strip() else None

    # Handle dictionary with common field names
    if isinstance(request_data, dict):
        for key in ['user_text', 'text', 'description', 'description_text']:
            if key in request_data and isinstance(request_data[key], str):
                text = request_data[key].strip()
                return text if text else None

    return None