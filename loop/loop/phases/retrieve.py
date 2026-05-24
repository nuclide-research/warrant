from __future__ import annotations
import dataclasses
import json
from pathlib import Path

from librarian.store import Index
from librarian.query import query_index, Result, SEMANTIC_POOL
from librarian.models import principle_to_dict


def retrieve(
    queries: list[str],
    index: Index,
    embedder,
    reranker,
    worktree_path: str,
    max_principles: int = 15,
) -> list[Result]:
    if not queries:
        return []

    seen: dict[str, Result] = {}
    for query in queries:
        results = query_index(index, query, embedder, reranker, k=SEMANTIC_POOL)
        for r in results:
            pid = r.principle.id
            if pid not in seen or r.score > seen[pid].score:
                seen[pid] = r

    merged = list(seen.values())
    combined_query = " ".join(queries)
    reranked_pairs = reranker.rerank(combined_query, [r.principle for r in merged])
    id_to_result = {r.principle.id: r for r in merged}
    ordered = []
    for p, new_score in reranked_pairs:
        r = id_to_result.get(p.id)
        if r is not None:
            ordered.append(dataclasses.replace(r, score=new_score))
    top = ordered[:max_principles]

    warrant_dir = Path(worktree_path) / ".warrant"
    warrant_dir.mkdir(parents=True, exist_ok=True)
    (warrant_dir / "principles.json").write_text(
        json.dumps([principle_to_dict(r.principle) for r in top], indent=2),
        encoding="utf-8",
    )

    return top
