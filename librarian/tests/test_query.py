import numpy as np
from librarian.models import Citation, Principle, Edge
from librarian.store import Index
from librarian.query import query_index


def _p(pid, statement):
    return Principle(id=pid, statement=statement,
                     citation=Citation("B", "111", "C", pid),
                     checkability_tier=3, evidence_chunk="e")


class FakeEmbedder:
    # query "layout" embeds parallel to row 0, orthogonal to row 1
    def encode(self, texts):
        return np.array([[1.0, 0.0]], dtype=np.float32)


class FakeReranker:
    def rerank(self, query, candidates):
        # identity rerank: keep semantic order, attach a score
        return [(p, 1.0) for p in candidates]


def test_query_returns_top_k_with_citations_and_graph_neighbors():
    index = Index(
        principles=[_p("p1", "layout principle"), _p("p2", "unrelated principle")],
        embeddings=np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        edges=[Edge("p1", "p2", "contradicts")],
    )
    results = query_index(index, "layout", FakeEmbedder(), FakeReranker(), k=1)
    assert len(results) == 1
    r = results[0]
    assert r.principle.id == "p1"
    assert r.citation.section == "p1"
    assert r.neighbors == [("p2", "contradicts")]
