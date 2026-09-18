import argparse
import sys

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Lost & Found CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Person A commands placeholder
    parser_lost = subparsers.add_parser("register-lost", help="Register a lost item")
    parser_lost.add_argument("--image", required=True)
    parser_lost.add_argument("--text", required=True)

    parser_found = subparsers.add_parser("register-found", help="Register a found item")
    parser_found.add_argument("--image", required=True)
    parser_found.add_argument("--text", required=True)

    parser_list = subparsers.add_parser("list", help="List registered items")
    parser_list.add_argument("--status", default="lost")

    # Person B commands placeholder
    parser_search = subparsers.add_parser("search-matches", help="Search matches for an item")
    parser_search.add_argument("--id", required=True, type=int)

    # Person C commands placeholder
    subparsers.add_parser("cost-report", help="Show AI token usage and cost report")

    args = parser.parse_args()

    # Dispatch logic will be filled in as team members PR their parts
    print(f"Command received: {args.command}")
    sys.exit(0)

if __name__ == "__main__":
    main()