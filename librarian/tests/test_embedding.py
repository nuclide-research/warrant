import numpy as np
from librarian.embedding import Embedder


def test_embedder_returns_unit_vectors_one_row_per_text():
    emb = Embedder()
    vecs = emb.encode(["composition over inheritance", "use ems for spacing"])
    assert vecs.shape[0] == 2
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)  # normalized for cosine via dot


def test_embedder_empty_input_returns_zero_rows():
    emb = Embedder()
    vecs = emb.encode([])
    assert vecs.shape == (0, 384)
    assert vecs.dtype == np.float32
