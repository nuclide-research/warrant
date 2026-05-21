import argparse
import json
import sys

from .embedding import Embedder
from .indexer import build_index
from .llm import AnthropicLLM
from .query import Reranker, query_index
from .store import load_index, save_index


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librarian",
                                     description="Warrant's retrieval engine.")
    sub = parser.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("index", help="build the index from a book library")
    pi.add_argument("library", help="path to the colophon-library directory")
    pi.add_argument("--out", default="./librarian-index", help="output index dir")

    pq = sub.add_parser("query", help="retrieve principles for a query")
    pq.add_argument("text", help="the query text")
    pq.add_argument("--index", default="./librarian-index", help="index dir")
    pq.add_argument("-k", type=int, default=5, help="how many principles to return")
    return parser


def _cmd_index(args) -> int:
    index = build_index(args.library, AnthropicLLM(), Embedder())
    save_index(index, args.out)
    print(f"indexed {len(index.principles)} principles, "
          f"{len(index.edges)} edges -> {args.out}", file=sys.stderr)
    return 0


def _cmd_query(args) -> int:
    index = load_index(args.index)
    results = query_index(index, args.text, Embedder(), Reranker(), k=args.k)
    print(json.dumps([
        {"statement": r.principle.statement,
         "tier": r.principle.checkability_tier,
         "citation": {"book": r.citation.book, "chapter": r.citation.chapter,
                      "section": r.citation.section},
         "score": round(r.score, 4),
         "neighbors": r.neighbors}
        for r in results
    ], indent=2))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return {"index": _cmd_index, "query": _cmd_query}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
