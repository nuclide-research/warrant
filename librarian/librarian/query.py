from dataclasses import dataclass

import numpy as np

from .models import Citation, Principle
from .store import Index

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
SEMANTIC_POOL = 20  # candidates fed to the reranker


@dataclass
class Result:
    principle: Principle
    citation: Citation
    score: float
    neighbors: list[tuple[str, str]]  # (neighbor principle id, edge kind)


class Reranker:
    """Cross-encoder reranker over (query, principle statement) pairs."""

    def __init__(self, model_name: str = RERANK_MODEL):
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[Principle]) -> list[tuple[Principle, float]]:
        if not candidates:
            return []
        scores = self._model.predict([(query, p.statement) for p in candidates])
        ranked = sorted(zip(candidates, scores), key=lambda t: t[1], reverse=True)
        return [(p, float(s)) for p, s in ranked]


def _neighbors(index: Index, pid: str) -> list[tuple[str, str]]:
    out = []
    for e in index.edges:
        if e.src == pid:
            out.append((e.dst, e.kind))
        elif e.dst == pid:
            out.append((e.src, e.kind))
    return out


def query_index(index: Index, query_text: str, embedder, reranker, k: int = 5) -> list[Result]:
    """Retrieve the top-k principles for a query: semantic pool, cross-encoder
    rerank, graph-neighbor enrichment. `k` should be <= SEMANTIC_POOL (20);
    results are silently capped at SEMANTIC_POOL otherwise."""
    if not index.principles:
        return []
    if index.embeddings.shape[0] != len(index.principles):
        raise ValueError("index is corrupt: embeddings/principles length mismatch")
    qv = embedder.encode([query_text])[0]
    sims = index.embeddings @ qv  # rows are normalized -> dot == cosine
    pool_idx = np.argsort(sims)[::-1][:SEMANTIC_POOL]
    pool = [index.principles[i] for i in pool_idx]
    ranked = reranker.rerank(query_text, pool)[:k]
    return [
        Result(principle=p, citation=p.citation, score=score,
               neighbors=_neighbors(index, p.id))
        for p, score in ranked
    ]
