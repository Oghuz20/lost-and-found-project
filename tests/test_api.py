from io import BytesIO
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.api import app, get_repo
from src.models import Item, ItemStatus

client = TestClient(app)

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x01\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_item(**overrides) -> Item:
    vec = np.array([1.0, 0.0], dtype=np.float32)
    defaults = {
        "id": 1,
        "status": ItemStatus.LOST,
        "user_text": "lost keys",
        "image_path": "/tmp/fake.png",
        "vlm_description": {"object_class": "keys", "confidence": 0.8},
        "embedding": Item.pack_embedding(vec),
    }
    defaults.update(overrides)
    return Item(**defaults)


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.list_items.return_value = []
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
    query = _make_item(id=1)
    match_payload = [
        {
            "item_id": 2,
            "status": "found",
            "score": 0.95,
            "object_class": "keys",
            "user_text": "found keys",
            "reason": "",
        }
    ]
    app.dependency_overrides[get_repo] = lambda: mock_repo
    with patch("src.api.find_top_matches", new_callable=AsyncMock) as mock_find:
        mock_find.return_value = (query, match_payload)
        try:
            response = client.get("/items/1/matches?k=5")
            assert response.status_code == 200
            body = response.json()
            assert body["top_k"] == 5
            assert len(body["matches"]) == 1
            assert body["matches"][0]["score"] == 0.95
        finally:
            app.dependency_overrides.clear()


def test_register_lost(mock_repo):
    saved = _make_item(id=42, status=ItemStatus.LOST)
    app.dependency_overrides[get_repo] = lambda: mock_repo
    with patch("src.api.register_uploaded_item", new_callable=AsyncMock) as mock_reg:
        mock_reg.return_value = saved
        try:
            response = client.post(
                "/items/lost",
                data={"user_text": "silver keys"},
                files={"file": ("keys.png", BytesIO(_MIN_PNG), "image/png")},
            )
            assert response.status_code == 201
            body = response.json()
            assert body["item"]["id"] == 42
            assert body["item"]["status"] == "lost"
        finally:
            app.dependency_overrides.clear()


def test_get_item_image_not_found(mock_repo):
    mock_repo.get_item.return_value = None
    app.dependency_overrides[get_repo] = lambda: mock_repo
    try:
        response = client.get("/items/999/image")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_web_ui_served():
    response = client.get("/")
    assert response.status_code == 200
    assert "Smart Lost" in response.text
