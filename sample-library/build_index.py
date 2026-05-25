#!/usr/bin/env python3
"""Build sample-library/index from principles.json.

Run once during development from the repo root:
    python sample-library/build_index.py

Output (sample-library/index/) is committed to git. Users never run this.
"""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).parent


def main() -> None:
    raw: list[dict] = json.loads((HERE / "principles.json").read_text(encoding="utf-8"))

    # Pop related_ids before building Principle objects (not a model field)
    related: dict[str, list[dict]] = {p["id"]: p.pop("related_ids", []) for p in raw}

    from librarian.models import Principle, Citation, Edge
    from librarian.store import Index, save_index
    from librarian.embedding import Embedder

    principles = [
        Principle(
            id=p["id"],
            statement=p["statement"],
            citation=Citation(**p["citation"]),
            checkability_tier=p["checkability_tier"],
            evidence_chunk=p["evidence_chunk"],
        )
        for p in raw
    ]

    print(f"Embedding {len(principles)} principles...")
    embedder = Embedder()
    embeddings = embedder.encode([p.statement for p in principles])

    # Build edges from related_ids with their specified kinds
    id_set = {p.id for p in principles}
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for p in principles:
        for entry in related.get(p.id, []):
            dst_id = entry["id"]
            kind = entry["kind"]
            if dst_id not in id_set or dst_id == p.id:
                continue
            key = (min(p.id, dst_id), max(p.id, dst_id))
            if key in seen:
                continue
            seen.add(key)
            edges.append(Edge(src=p.id, dst=dst_id, kind=kind))

    index = Index(principles=principles, embeddings=embeddings, edges=edges)
    out_dir = HERE / "index"
    save_index(index, out_dir)
    print(f"Saved {len(principles)} principles, {len(edges)} edges → {out_dir}")


if __name__ == "__main__":
    main()
