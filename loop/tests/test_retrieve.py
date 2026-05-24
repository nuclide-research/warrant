import json
from pathlib import Path
from loop.phases.retrieve import retrieve
from tests.fakes import FakeReranker, FakeEmbedder, make_fixture_index


def test_retrieve_returns_results(tmp_path):
    index = make_fixture_index(2)
    results = retrieve(
        queries=["query one"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    assert len(results) > 0


def test_retrieve_writes_principles_json(tmp_path):
    index = make_fixture_index(2)
    retrieve(
        queries=["query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    principles_file = tmp_path / ".warrant" / "principles.json"
    assert principles_file.exists()
    data = json.loads(principles_file.read_text())
    assert isinstance(data, list)
    assert len(data) > 0


def test_retrieve_deduplicates(tmp_path):
    index = make_fixture_index(2)
    # Two identical queries — result set should not double
    results = retrieve(
        queries=["same query", "same query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
    )
    ids = [r.principle.id for r in results]
    assert len(ids) == len(set(ids))


def test_retrieve_respects_max_principles(tmp_path):
    index = make_fixture_index(10)
    results = retrieve(
        queries=["query"],
        index=index,
        embedder=FakeEmbedder(),
        reranker=FakeReranker(),
        worktree_path=str(tmp_path),
        max_principles=3,
    )
    assert len(results) <= 3
