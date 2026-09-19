from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api import app, get_repo

client = TestClient(app)


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.list_items.return_value = []
    
    mock_match = MagicMock()
    mock_match.item_id = 456
    mock_match.score = 0.95
    
    repo.find_matches.return_value = [mock_match]
    return repo


def test_list_items(mock_repo):
    app.dependency_overrides[get_repo] = lambda: mock_repo
    try:
        response = client.get("/items")
        assert response.status_code == 200
        assert response.json() == {"status_filter": None, "items": []}
    finally:
        app.dependency_overrides.clear()


def test_get_matches(mock_repo):
    app.dependency_overrides[get_repo] = lambda: mock_repo
    try:
        response = client.get("/items/123/matches?k=5")
        assert response.status_code == 200
        assert response.json()["top_k"] == 5
    finally:
        app.dependency_overrides.clear()