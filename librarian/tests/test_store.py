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
