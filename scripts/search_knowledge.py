import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge import KnowledgeBase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local agent knowledge base.")
    parser.add_argument("query", help="Search query to test")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env.local", override=True)
    load_dotenv(ROOT / ".env")

    kb = KnowledgeBase.from_env()
    print(f"chunks={len(kb.chunks)}")
    for hit in kb.search(args.query, limit=args.limit):
        print(f"\nscore={hit.score:.4f} source={hit.source} heading={hit.heading}")
        print(hit.text)


if __name__ == "__main__":
    main()
