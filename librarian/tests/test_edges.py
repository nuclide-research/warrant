from librarian.models import Citation, Principle
from librarian.edges import extract_edges
from tests.fakes import FakeLLM
import json


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
    edges = extract_edges(principles, llm)
    assert len(edges) == 1
    assert edges[0].src == "p1" and edges[0].dst == "p2"
    assert edges[0].kind == "contradicts"


def test_extract_edges_drops_self_loops():
    principles = [_p("p1", "A."), _p("p2", "B.")]
    llm = FakeLLM([json.dumps([{"src": "p1", "dst": "p1", "kind": "refines"}])])
    assert extract_edges(principles, llm) == []


def test_extract_edges_drops_unknown_kind():
    principles = [_p("p1", "A."), _p("p2", "B.")]
    llm = FakeLLM([json.dumps([{"src": "p1", "dst": "p2", "kind": "enhances"}])])
    assert extract_edges(principles, llm) == []
