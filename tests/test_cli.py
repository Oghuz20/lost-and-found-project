"""Tests for CLI subcommands."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ai.vlm import ItemDescription
from src.cli import _list, _register, _search_matches, main
from src.models import ItemStatus


@pytest.fixture
def mock_vlm_desc():
    return ItemDescription(
        object_class="wallet",
        colors=["brown"],
        brand=None,
        distinguishing_marks=["leather"],
        location_hints=[],
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_cli_register_lost(mock_vlm_desc):
    mock_saved_item = MagicMock()
    mock_saved_item.id = 1

    with (
        patch("src.cli.describe_item", return_value=mock_vlm_desc),
        patch("src.cli.embed_text", return_value=[0.1] * 1536, create=True),
        patch("src.cli.embed", return_value=[0.1] * 1536, create=True),
        patch("src.cli.get_pool", new_callable=AsyncMock),
        patch("src.cli.init_schema", new_callable=AsyncMock),
        patch("src.cli.ItemRepository") as mock_repo_cls,
    ):
        mock_repo = AsyncMock()
        mock_repo.save_item = AsyncMock(return_value=mock_saved_item)
        mock_repo.add_item = AsyncMock(return_value=1)
        mock_repo_cls.return_value = mock_repo

        await _register(ItemStatus.LOST, "data/lost/wallet_brown.png", "brown wallet")
        assert mock_repo.save_item.called or mock_repo.add_item.called


@pytest.mark.asyncio
async def test_cli_search_matches():
    mock_candidate = MagicMock()
    mock_candidate.item_id = 2
    mock_candidate.score = 0.916
    mock_candidate.status = ItemStatus.FOUND
    mock_candidate.user_text = "found near gym"
    mock_candidate.vlm_description = {"object_class": "wallet"}

    mock_target_item = MagicMock()
    mock_target_item.id = 1
    mock_target_item.vlm_description = {"object_class": "wallet"}
    mock_target_item.embedding = [0.1] * 1536

    with (
        patch("src.cli.get_pool", new_callable=AsyncMock),
        patch("src.cli.init_schema", new_callable=AsyncMock),
        patch("src.cli.ItemRepository") as mock_repo_cls,
    ):
        mock_repo = AsyncMock()
        mock_repo.get_item = AsyncMock(return_value=mock_target_item)
        mock_repo.find_matches = AsyncMock(return_value=[mock_candidate])
        mock_repo_cls.return_value = mock_repo

        await _search_matches(item_id=1, k=3)
        assert mock_repo.get_item.called


@pytest.mark.asyncio
async def test_cli_list_items():
    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.status = ItemStatus.LOST
    mock_item.vlm_description = {"object_class": "wallet"}
    mock_item.created_at.isoformat.return_value = "2026-09-18T10:00:00Z"

    with (
        patch("src.cli.get_pool", new_callable=AsyncMock),
        patch("src.cli.init_schema", new_callable=AsyncMock),
        patch("src.cli.ItemRepository") as mock_repo_cls,
    ):
        mock_repo = AsyncMock()
        mock_repo.list_items = AsyncMock(return_value=[mock_item])
        mock_repo_cls.return_value = mock_repo

        await _list(status="lost")
        mock_repo.list_items.assert_called_once()


def test_cli_main_argparse():
    test_args = ["cli.py", "list", "--status", "lost"]

    def _close_coro(coro):
        if hasattr(coro, "close"):
            coro.close()

    with (
        patch("sys.argv", test_args),
        patch("src.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        patch("src.cli._list", new_callable=AsyncMock) as mock_list_fn,
    ):
        main()
        mock_run.assert_called_once()