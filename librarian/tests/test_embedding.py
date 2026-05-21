import numpy as np
from librarian.embedding import Embedder


def test_embedder_returns_unit_vectors_one_row_per_text():
    emb = Embedder()
    vecs = emb.encode(["composition over inheritance", "use ems for spacing"])
    assert vecs.shape[0] == 2
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)  # normalized for cosine via dot
