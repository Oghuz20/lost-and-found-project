"""Command-line entry point for the Smart Lost & Found service.

Run as::

    python -m src.cli register-lost --image data/lost/wallet_brown.png --text "brown leather wallet"
    python -m src.cli register-found --image data/found/wallet_brown_2.png --text "found near the gym"
    python -m src.cli list --status lost
    python -m src.cli search-matches --id 1 -k 3
    python -m src.cli cost-report
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv
from pydantic import ValidationError

from src.config import get_settings
from src.models import ItemStatus
from src.services.item_flow import (
    ItemFlowError,
    ItemNoEmbeddingError,
    ItemNotFoundError,
    find_top_matches,
    register_item_from_file,
)
from src.storage.blob_store import BlobValidationError
from src.storage.db import get_pool, init_schema
from src.storage.repository import ItemRepository

load_dotenv()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lost-and-found", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_lost = sub.add_parser("register-lost", help="Register a lost item.")
    p_lost.add_argument("--image", required=True, help="Path to a JPEG/PNG image.")
    p_lost.add_argument("--text", default="", help="Free-text description from the user.")

    p_found = sub.add_parser("register-found", help="Register a found item.")
    p_found.add_argument("--image", required=True, help="Path to a JPEG/PNG image.")
    p_found.add_argument("--text", default="", help="Free-text description from the user.")

    p_search = sub.add_parser("search-matches", help="Find top-k matches for an item.")
    p_search.add_argument("--id", type=int, required=True, dest="item_id", help="Item ID to search matches for.")
    p_search.add_argument("-k", type=int, default=3, help="Number of top matches to return.")

    p_list = sub.add_parser("list", help="List registered items.")
    p_list.add_argument(
        "--status",
        choices=[s.value for s in ItemStatus],
        default=None,
        help="Filter by status. Omit to list everything.",
    )

    sub.add_parser("cost-report", help="Display AI service cost and token usage summary")

    return parser


async def _get_repo() -> ItemRepository:
    settings = get_settings()
    pool = await get_pool(settings)
    await init_schema(pool, settings)
    return ItemRepository(pool)


async def _register(kind: ItemStatus, image_path: str, text: str) -> None:
    try:
        repo = await _get_repo()
        saved = await register_item_from_file(
            status=kind,
            image_path=image_path,
            user_text=text,
            repo=repo,
        )
    except ValidationError as exc:
        print(f"error: invalid input: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except BlobValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ItemFlowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    obj = saved.vlm_description.get("object_class", "?")
    conf = saved.vlm_description.get("confidence", 0.0)
    print(f"registered {kind.value} item #{saved.id}: {obj} (confidence={conf:.2f})")


async def _search_matches(item_id: int, k: int) -> None:
    repo = await _get_repo()
    try:
        query_item, matches = await find_top_matches(item_id=item_id, k=k, repo=repo)
    except ItemNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ItemNoEmbeddingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if not matches:
        opposite = ItemStatus.FOUND if query_item.status == ItemStatus.LOST else ItemStatus.LOST
        print(f"no {opposite.value} items with embeddings to match against")
        return

    obj = query_item.vlm_description.get("object_class", "?")
    print(f"top matches for item #{item_id} ({obj}):")
    for m in matches:
        print(
            f"  -> #{m['item_id']:<4} {m.get('object_class') or '?':<20} "
            f"score={m['score']:+.3f}"
        )


async def _list(status: str | None) -> None:
    repo = await _get_repo()
    items = await repo.list_items(status)
    if not items:
        print("no items found")
        return
    for it in items:
        obj = it.vlm_description.get("object_class", "?")
        print(f"#{it.id:<4} {it.status.value:<8} {obj:<20} {it.created_at.isoformat()}")


async def _cost_report() -> None:
    from src.telemetry.cost import get_cost_report

    report = get_cost_report(hours=24)
    print(report)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "register-lost":
        asyncio.run(_register(ItemStatus.LOST, args.image, args.text))
    elif args.command == "register-found":
        asyncio.run(_register(ItemStatus.FOUND, args.image, args.text))
    elif args.command == "search-matches":
        asyncio.run(_search_matches(args.item_id, args.k))
    elif args.command == "list":
        asyncio.run(_list(args.status))
    elif args.command == "cost-report":
        asyncio.run(_cost_report())
    else:  # pragma: no cover
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
