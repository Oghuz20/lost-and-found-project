"""Command-line entry point for Person A's storage and registration scope."""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv

from ai import describe_item, embed
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
    p_lost.add_argument(
        "--text", default="", help="Free-text description from the user."
    )

    p_found = sub.add_parser("register-found", help="Register a found item.")
    p_found.add_argument("--image", required=True, help="Path to a JPEG/PNG image.")
    p_found.add_argument(
        "--text", default="", help="Free-text description from the user."
    )

    p_list = sub.add_parser("list", help="List registered items.")
    p_list.add_argument(
        "--status",
        choices=[s.value for s in ItemStatus],
        default=None,
        help="Filter by status. Omit to list everything.",
    )

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
    print(
        f"registered {kind.value} item #{saved.id}: {desc.object_class} (confidence={desc.confidence:.2f})"
    )


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


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "register-lost":
        asyncio.run(_register(ItemStatus.LOST, args.image, args.text))
    elif args.command == "register-found":
        asyncio.run(_register(ItemStatus.FOUND, args.image, args.text))
    elif args.command == "list":
        asyncio.run(_list(args.status))
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
