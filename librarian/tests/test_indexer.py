from pathlib import Path
import numpy as np
from librarian.indexer import build_index
from tests.fakes import FakeLLM, principles_json
import json

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEmbedder:
    def encode(self, texts):
        return np.ones((len(texts), 4), dtype=np.float32)


def test_build_index_extracts_embeds_and_links():
    # fixture book has 3 sections -> 3 principle-extraction calls, then 1 edge call
    llm = FakeLLM([
        principles_json([{"statement": "Principle A.", "checkability_tier": 1,
                          "evidence_chunk": "a"}]),
        principles_json([{"statement": "Principle B.", "checkability_tier": 2,
                          "evidence_chunk": "b"}]),
        principles_json([]),
        json.dumps([]),  # edge-extraction call
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    assert len(index.principles) == 2
    assert index.embeddings.shape == (2, 4)
    assert index.edges == []


def test_build_index_skips_malformed_sections(capsys):
    # section 2's response is malformed -> that section is skipped, build continues
    llm = FakeLLM([
        principles_json([{"statement": "Good A.", "checkability_tier": 1,
                          "evidence_chunk": "a"}]),
        "not json at all",
        principles_json([{"statement": "Good C.", "checkability_tier": 3,
                          "evidence_chunk": "c"}]),
        json.dumps([]),  # edge-extraction call
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    assert len(index.principles) == 2
    assert {p.statement for p in index.principles} == {"Good A.", "Good C."}
    assert "skipping" in capsys.readouterr().err


def test_build_index_empty_library(tmp_path):
    llm = FakeLLM([])  # no calls expected
    index = build_index(tmp_path, llm, FakeEmbedder())
    assert index.principles == []
    assert index.edges == []
    assert index.embeddings.shape[0] == 0


def test_build_index_survives_malformed_edge_response(capsys):
    # every section extracts fine; the edge call returns non-JSON -> the graph
    # is dropped but the index is still built, not aborted
    llm = FakeLLM([
        principles_json([{"statement": "P one.", "checkability_tier": 1,
                          "evidence_chunk": "a"}]),
        principles_json([{"statement": "P two.", "checkability_tier": 2,
                          "evidence_chunk": "b"}]),
        principles_json([]),
        "not valid json",  # edge-extraction call
    ])
    index = build_index(FIXTURES, llm, FakeEmbedder())
    assert len(index.principles) == 2
    assert index.edges == []
    assert "edge extraction failed" in capsys.readouterr().err
