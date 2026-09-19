"""Command-line entry point for the Smart Lost & Found service.

Run as::

    python -m src.cli register-lost --image data/lost/wallet_brown.png --text "brown leather wallet"
    python -m src.cli register-found --image data/found/wallet_brown_2.png --text "found near the gym"
    python -m src.cli list --status lost
    python -m src.cli search-matches --id 1 -k 3
    python -m src.cli cost-report

Integration note
-----------------
`_register` and `_search_matches` currently call `ai.describe_item` /
`ai.embed` / `ai.top_k` directly so every command is usable end-to-end on
its own. Once `src/services/ai_service.py` (Person C's retry/timeout/
logging wrapper) and `src/services/pipeline.py` (Person B's orchestration)
are both confirmed stable, swap the direct `ai.*` calls below for those
instead — nothing else in this file should need to change.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

from dotenv import load_dotenv
from numpy import ndarray

from ai import describe_item, embed, top_k
from src.config import get_settings
from src.models import Item, ItemStatus
from src.storage.blob_store import BlobStore, BlobValidationError
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


async def _register(kind: ItemStatus, image_path: str, text: str) -> None:
    settings = get_settings()
    store = BlobStore(settings)

    try:
        with open(image_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"error: could not read {image_path!r}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        blob = store.save(data, original_filename=image_path)
    except BlobValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    desc = describe_item(str(blob.path), text)
    vec = embed(desc.to_search_text())

    pool = await get_pool(settings)
    await init_schema(pool, settings)
    repo = ItemRepository(pool)
    item = Item(
        status=kind,
        user_text=text,
        image_path=str(blob.path),
        vlm_description=desc.to_dict(),
        embedding=Item.pack_embedding(vec),
    )
    saved = await repo.save_item(item)
    print(f"registered {kind.value} item #{saved.id}: {desc.object_class} (confidence={desc.confidence:.2f})")


async def _search_matches(item_id: int, k: int) -> None:
    settings = get_settings()
    pool = await get_pool(settings)
    await init_schema(pool, settings)
    repo = ItemRepository(pool)

    query_item = await repo.get_item(item_id)
    if query_item is None:
        print(f"error: no item with id {item_id}", file=sys.stderr)
        raise SystemExit(1)

    query_vec = query_item.embedding_array()
    if query_vec is None:
        print(f"error: item {item_id} has no stored embedding", file=sys.stderr)
        raise SystemExit(1)

    opposite_status = ItemStatus.FOUND if query_item.status == ItemStatus.LOST else ItemStatus.LOST
    candidates = await repo.list_items(opposite_status)
    if not candidates:
        print(f"no {opposite_status.value} items to match against")
        return
    scored_candidates = [c for c in candidates if c.embedding_array() is not None]
    if not scored_candidates:
        print(f"no {opposite_status.value} items with embeddings to match against")
        return

    cand_vecs = [cast(ndarray, c.embedding_array()) for c in scored_candidates]
    matches = top_k(query_vec, cand_vecs, k=min(k, len(scored_candidates)))

    obj = query_item.vlm_description.get("object_class", "?")
    print(f"top matches for item #{item_id} ({obj}):")
    for m in matches:
        cand = scored_candidates[m.candidate_id]
        cand_obj = cand.vlm_description.get("object_class", "?")
        print(f"  -> #{cand.id:<4} {cand_obj:<20} score={m.score:+.3f}")


async def _list(status: str | None) -> None:
    settings = get_settings()
    pool = await get_pool(settings)
    await init_schema(pool, settings)
    repo = ItemRepository(pool)
    items = await repo.list_items(status)
    if not items:
        print("no items found")
        return
    for it in items:
        obj = it.vlm_description.get("object_class", "?")
        print(f"#{it.id:<4} {it.status.value:<8} {obj:<20} {it.created_at.isoformat()}")


async def _cost_report() -> None:
    """Generate and display the telemetry cost report."""
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
    else:  # pragma: no cover - argparse enforces `required=True` above
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()