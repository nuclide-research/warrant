from pathlib import Path
import json
import numpy as np
from librarian.indexer import build_index
from librarian.store import save_index, load_index
from librarian.query import query_index
from tests.fakes import FakeLLM, principles_json

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    """Deterministic: 'section one' principles get vector [1,0], others [0,1]."""
    def encode(self, texts):
        rows = [[1.0, 0.0] if "one" in t.lower() else [0.0, 1.0] for t in texts]
        return np.array(rows or [[0.0, 0.0]], dtype=np.float32)


class FakeReranker:
    def rerank(self, query, candidates):
        return [(p, 1.0) for p in candidates]


def test_index_save_load_query_round_trip(tmp_path):
    llm = FakeLLM([
        # response order follows iter_sections: Introduction, Section One,
        # Section Two, then the single edge-extraction pass over all principles
        principles_json([{"statement": "Section one principle.",
                          "checkability_tier": 1, "evidence_chunk": "one"}]),
        principles_json([{"statement": "Section two principle.",
                          "checkability_tier": 2, "evidence_chunk": "two"}]),
        principles_json([]),
        json.dumps([{"src": "9999999999999:the-first-chapter:introduction:1",
                     "dst": "9999999999999:the-first-chapter:section-one:1",
                     "kind": "shares_topic"}]),
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    save_index(index, tmp_path / "idx")
    reloaded = load_index(tmp_path / "idx")

    results = query_index(reloaded, "section one", FakeEmbedder(), FakeReranker(), k=1)
    assert len(results) == 1
    assert "one" in results[0].principle.statement.lower()
    assert results[0].citation.isbn == "9999999999999"
    # the principle graph survived the save/load round trip
    assert results[0].neighbors == [(reloaded.principles[1].id, "shares_topic")]
