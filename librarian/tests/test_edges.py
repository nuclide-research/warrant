import json
import numpy as np
from librarian.models import Citation, Principle, Edge
from librarian.edges import extract_edges, _candidate_pairs
from tests.fakes import FakeLLM

_EMB2 = np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32)


def _p(pid, statement):
    return Principle(id=pid, statement=statement,
                     citation=Citation("B", "111", "C", "S"),
                     checkability_tier=3, evidence_chunk="e")


def test_extract_edges_parses_relations_and_drops_unknown_ids():
    principles = [_p("p1", "Prefer composition."), _p("p2", "Always use inheritance.")]
    llm = FakeLLM([json.dumps([
        {"src": "p1", "dst": "p2", "kind": "contradicts"},
        {"src": "p1", "dst": "ghost", "kind": "refines"},  # ghost id -> dropped
    ])])
    edges = extract_edges(principles, _EMB2, llm)
    assert len(edges) == 1
    assert edges[0].src == "p1" and edges[0].dst == "p2"
    assert edges[0].kind == "contradicts"


def test_extract_edges_drops_self_loops():
    principles = [_p("p1", "A."), _p("p2", "B.")]
    llm = FakeLLM([json.dumps([{"src": "p1", "dst": "p1", "kind": "refines"}])])
    assert extract_edges(principles, _EMB2, llm) == []


def test_extract_edges_drops_unknown_kind():
    principles = [_p("p1", "A."), _p("p2", "B.")]
    llm = FakeLLM([json.dumps([{"src": "p1", "dst": "p2", "kind": "enhances"}])])
    assert extract_edges(principles, _EMB2, llm) == []


def test_candidate_pairs_are_nearest_neighbors():
    # principles 0 and 1 are near-identical; 2 is orthogonal
    emb = np.array([[1.0, 0.0], [0.99, 0.01], [0.0, 1.0]], dtype=np.float32)
    pairs = _candidate_pairs(emb, n_neighbors=1)
    assert (0, 1) in pairs


def test_extract_edges_batches_large_candidate_sets():
    # more candidate pairs than one batch holds -> more than one LLM call
    principles = [_p(f"p{i}", f"Principle number {i}.") for i in range(60)]
    rng = np.random.RandomState(0)
    emb = rng.rand(60, 8).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    llm = FakeLLM(["[]"] * 25)
    extract_edges(principles, emb, llm)
    assert len(llm.prompts) > 1
