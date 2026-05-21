import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Embedder:
    """Local sentence-transformers embedder. Returns L2-normalized vectors so
    cosine similarity is a plain dot product."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._model.get_embedding_dimension()),
                            dtype=np.float32)
        return self._model.encode(texts, normalize_embeddings=True,
                                  convert_to_numpy=True).astype(np.float32)
