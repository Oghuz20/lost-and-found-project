"""Scripted demo scenario for Smart Lost & Found grading.

This script demonstrates the exact scenario used for grading:
1. Registers all items from data/lost as lost items
2. Registers all items from data/found as found items
3. Queries one lost item (the first one) for matches
4. Prints top-3 matches + VLM reasoning

Works both with the HTTP API (when running) and in offline/direct mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure imports work regardless of execution directory
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from ai import top_k
from ai.schemas import ItemDescription
from src.services.ai_service import describe_item, embed
from src.services.cache import get_embedding_cache

from dotenv import load_dotenv
load_dotenv()


def load_items_from_directory(directory: Path) -> List[Path]:
    """Load all PNG/JPG images from a directory."""
    if not directory.exists():
        print(f"!! Directory not found: {directory}", file=sys.stderr)
        return []

    images = []
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        images.extend(directory.glob(ext))
    return sorted(images)


def register_item_via_api(
    image_path: Path,
    item_type: str,
    user_text: str = "",
    api_base_url: str = "http://localhost:8000",
) -> Dict[str, Any]:
    """Register an item via the HTTP API (POST /items/lost or /items/found)."""
    endpoint = f"{api_base_url}/items/{item_type}"
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f, "image/png")}
        data = {"user_text": user_text}
        response = requests.post(endpoint, files=files, data=data, timeout=30)
        response.raise_for_status()
        return response.json()


def process_item_direct(
    image_path: Path,
    user_text: str = "",
    use_fake_providers: bool = False,
) -> Tuple[str, ItemDescription, List[float]]:
    """Process an item directly using Python service wrappers."""
    filename = image_path.name

    if use_fake_providers:
        from tests.conftest import FakeEmbedder, FakeVLM

        description = describe_item(str(image_path), user_text, vlm=FakeVLM())
        search_text = description.to_search_text()
        embedding = embed(search_text, embedder=FakeEmbedder())
    else:
        description = describe_item(str(image_path), user_text)
        search_text = description.to_search_text()
        embedding = embed(search_text)

    return filename, description, embedding


def run_demo_scenario(
    use_api: bool = False,
    api_base_url: str = "http://localhost:8000",
    use_fake_providers: bool = False,
) -> None:
    """Run the complete demo scenario."""
    here = Path(__file__).parent.parent
    lost_dir = here / "data" / "lost"
    found_dir = here / "data" / "found"

    print("Smart Lost & Found Demo")
    print("=" * 50)
    print(f"Mode: {'HTTP API' if use_api else 'Direct Service Calls'}")
    if use_api:
        print(f"API URL: {api_base_url}")
    print()

    # Clear embedding cache for clean demo run
    get_embedding_cache().clear()
    print("Cleared embedding cache for fresh run\n")

    # 1. Process Lost Items
    print("Processing LOST items...")
    lost_items = []
    lost_images = load_items_from_directory(lost_dir)

    if not lost_images:
        print("!! No lost items found in data/lost!", file=sys.stderr)
        return

    for img_path in lost_images:
        try:
            if use_api:
                data = register_item_via_api(
                    img_path, "lost", "", api_base_url
                )
                desc_obj = ItemDescription(**data["vlm_description"])
                lost_items.append((img_path.name, desc_obj, data["embedding"]))
            else:
                filename, desc_obj, embedding = process_item_direct(
                    img_path, "", use_fake_providers
                )
                lost_items.append((filename, desc_obj, embedding))

            print(
                f"  - {img_path.name}: {desc_obj.object_class} "
                f"(confidence: {desc_obj.confidence:.2f})"
            )
        except Exception as e:
            print(
                f"  !! Skipping {img_path.name} due to error: {e}",
                file=sys.stderr,
            )

    print(f"\nProcessed {len(lost_items)} lost items\n")

    # 2. Process Found Items
    print("Processing FOUND items...")
    found_items = []
    found_images = load_items_from_directory(found_dir)

    if not found_images:
        print("!! No found items found in data/found!", file=sys.stderr)
        return

    for img_path in found_images:
        try:
            if use_api:
                data = register_item_via_api(
                    img_path, "found", "", api_base_url
                )
                desc_obj = ItemDescription(**data["vlm_description"])
                found_items.append(
                    (img_path.name, desc_obj, data["embedding"])
                )
            else:
                filename, desc_obj, embedding = process_item_direct(
                    img_path, "", use_fake_providers
                )
                found_items.append((filename, desc_obj, embedding))

            print(
                f"  - {img_path.name}: {desc_obj.object_class} "
                f"(confidence: {desc_obj.confidence:.2f})"
            )
        except Exception as e:
            print(
                f"  !! Skipping {img_path.name} due to error: {e}",
                file=sys.stderr,
            )

    print(f"\nProcessed {len(found_items)} found items\n")

    if not lost_items or not found_items:
        print("!! Insufficient items for matching", file=sys.stderr)
        return

    # 3. Matching
    query_filename, query_desc, query_embedding = lost_items[0]
    print(f"Finding matches for LOST item: {query_filename!r}")
    print(f"  Query description: {query_desc.to_search_text()}\n")

    k = min(3, len(found_items))

    if use_api:
        # Search using API endpoint
        search_endpoint = f"{api_base_url}/matches/search"
        resp = requests.post(
            search_endpoint,
            json={"embedding": query_embedding, "k": k},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("matches", [])

        print(f"Top {len(results)} matches for LOST item '{query_filename}':")
        print(f"  Query: {query_desc.to_search_text()}\n")

        for i, match in enumerate(results, 1):
            print(f"  {i}. Item ID: {match.get('found_item_id')}")
            print(f"     Similarity score: {match.get('score', 0.0):+.3f}")
            print(f"     Reason: {match.get('reason', 'N/A')}\n")
    else:
        # Search direct in memory
        found_embeddings = [emb for (_, _, emb) in found_items]
        matches = top_k(query_embedding, found_embeddings, k=k)

        print(f"Top {k} matches for LOST item '{query_filename}':")
        print(f"  Query: {query_desc.to_search_text()}\n")

        for i, match in enumerate(matches, 1):
            found_idx = match.candidate_id
            if found_idx < len(found_items):
                fname, fdesc, _ = found_items[found_idx]
                print(f"  {i}. {fname}")
                print(f"     Description: {fdesc.to_search_text()}")
                print(f"     Similarity score: {match.score:+.3f}")
                print(f"     Object class: {fdesc.object_class}")
                print(
                    f"     Colors: {', '.join(fdesc.colors) if fdesc.colors else 'None'}"
                )
                print(f"     Confidence: {fdesc.confidence:.2f}\n")

    # Cache Stats
    cache_stats = get_embedding_cache().stats()
    print("Embedding Cache Statistics:")
    print(f"  Hits: {cache_stats['hits']}")
    print(f"  Misses: {cache_stats['misses']}")
    print(f"  Size: {cache_stats['size']} entries")
    total_calls = cache_stats["hits"] + cache_stats["misses"]
    if total_calls > 0:
        hit_rate = (cache_stats["hits"] / total_calls) * 100
        print(f"  Hit rate: {hit_rate:.1f}%")
    print("\nDemo completed successfully!")


def test_api_health(api_base_url: str = "http://localhost:8000") -> bool:
    """Check if the HTTP API server is responsive."""
    try:
        response = requests.get(f"{api_base_url}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run the Smart Lost & Found demo scenario"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Test against HTTP API instead of direct service calls",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL for HTTP API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in offline mode (uses fake providers, no network calls)",
    )

    args = parser.parse_args()
    use_fake_providers = args.offline

    if args.offline:
        print("Running in offline mode (using fake providers)\n")

    if args.api:
        if not test_api_health(args.api_url):
            print(
                f"!! HTTP API not available at {args.api_url}", file=sys.stderr
            )
            print("!! Falling back to direct service calls...\n")
            args.api = False

    try:
        run_demo_scenario(
            use_api=args.api,
            api_base_url=args.api_url,
            use_fake_providers=use_fake_providers,
        )
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"!! Demo failed with error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()