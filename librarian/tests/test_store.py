import numpy as np
from librarian.models import Citation, Principle, Edge
from librarian.store import Index, save_index, load_index


def _index():
    p = Principle(id="111:c:s:1", statement="Do the thing.",
                  citation=Citation("B", "111", "C", "S"),
                  checkability_tier=1, evidence_chunk="evidence")
    return Index(principles=[p],
                 embeddings=np.ones((1, 4), dtype=np.float32),
                 edges=[Edge("111:c:s:1", "111:c:s:1", "refines")])


def test_save_then_load_round_trips(tmp_path):
    save_index(_index(), tmp_path)
    loaded = load_index(tmp_path)
    assert loaded.principles[0].statement == "Do the thing."
    assert loaded.embeddings.shape == (1, 4)
    assert loaded.edges[0].kind == "refines"
    # principles are written as inspectable per-principle JSON files
    assert (tmp_path / "principles").is_dir()
    assert len(list((tmp_path / "principles").glob("*.json"))) == 1


def test_order_is_preserved(tmp_path):
    p1 = Principle(id="111:c:s:1", statement="First.",
                   citation=Citation("B", "111", "C", "S"),
                   checkability_tier=1, evidence_chunk="e1")
    p2 = Principle(id="111:c:s:2", statement="Second.",
                   citation=Citation("B", "111", "C", "S"),
                   checkability_tier=2, evidence_chunk="e2")
    idx = Index(principles=[p1, p2],
                embeddings=np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32),
                edges=[])
    save_index(idx, tmp_path)
    loaded = load_index(tmp_path)
    assert loaded.principles[0].statement == "First."
    assert loaded.principles[1].statement == "Second."
    assert loaded.embeddings[0, 0] == 1.0
    assert loaded.embeddings[1, 1] == 1.0
