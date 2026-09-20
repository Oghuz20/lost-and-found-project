"""Tests for CLI subcommands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cli import _list, _register, _search_matches, main
from src.models import Item, ItemStatus


@pytest.fixture
def mock_saved_item():
    item = MagicMock(spec=Item)
    item.id = 1
    item.vlm_description = {"object_class": "wallet", "confidence": 0.9}
    return item


@pytest.mark.asyncio
async def test_cli_register_lost(mock_saved_item):
    with (
        patch("src.cli.register_item_from_file", new_callable=AsyncMock) as mock_reg,
        patch("src.cli._get_repo", new_callable=AsyncMock),
    ):
        mock_reg.return_value = mock_saved_item
        await _register(ItemStatus.LOST, "data/lost/wallet_brown.png", "brown wallet")
        mock_reg.assert_called_once()


@pytest.mark.asyncio
async def test_cli_search_matches():
    query = MagicMock()
    query.status = ItemStatus.LOST
    query.vlm_description = {"object_class": "wallet"}
    matches = [{"item_id": 2, "object_class": "wallet", "score": 0.916}]

    with (
        patch("src.cli._get_repo", new_callable=AsyncMock),
        patch("src.cli.find_top_matches", new_callable=AsyncMock) as mock_find,
    ):
        mock_find.return_value = (query, matches)
        await _search_matches(item_id=1, k=3)
        mock_find.assert_called_once()


@pytest.mark.asyncio
async def test_cli_list_items():
    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.status = ItemStatus.LOST
    mock_item.vlm_description = {"object_class": "wallet"}
    mock_item.created_at.isoformat.return_value = "2026-09-18T10:00:00Z"

    with (
        patch("src.cli._get_repo", new_callable=AsyncMock) as mock_get_repo,
    ):
        mock_repo = AsyncMock()
        mock_repo.list_items = AsyncMock(return_value=[mock_item])
        mock_get_repo.return_value = mock_repo

        await _list(status="lost")
        mock_repo.list_items.assert_called_once_with("lost")


def test_cli_main_argparse():
    test_args = ["cli.py", "list", "--status", "lost"]

    def _close_coro(coro):
        if hasattr(coro, "close"):
            coro.close()

    with (
        patch("sys.argv", test_args),
        patch("src.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        patch("src.cli._list", new_callable=AsyncMock),
    ):
        main()
        mock_run.assert_called_once()
