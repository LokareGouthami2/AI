"""Text embedders behind one interface.

* ``SentenceTransformerEmbedder`` – all-MiniLM-L6-v2 (384-d), loaded from the
  local Hugging Face cache only (never downloads at request time).
* ``HashingEmbedder`` – deterministic, dependency-light fallback: word 1-2-gram
  and char 3-5-gram feature hashing → 1024-d L2-normalised vectors. Lexical
  rather than semantic, but stable, fast, and needs no model download.
"""

from __future__ import annotations

import functools
import logging

import numpy as np

from backend.config import get_settings

log = logging.getLogger(__name__)


class Embedder:
    name: str = "base"
    dim: int = 0

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class HashingEmbedder(Embedder):
    name = "hashing-v1"
    dim = 1024

    def __init__(self):
        from sklearn.feature_extraction.text import HashingVectorizer

        self._word = HashingVectorizer(n_features=self.dim, ngram_range=(1, 2), alternate_sign=False, norm=None, lowercase=True, stop_words="english")
        self._char = HashingVectorizer(n_features=self.dim, analyzer="char_wb", ngram_range=(3, 5), alternate_sign=False, norm=None)

    def embed(self, texts: list[str]) -> np.ndarray:
        w = self._word.transform(texts).toarray()
        c = self._char.transform(texts).toarray()
        v = np.log1p(w) * 2.0 + np.log1p(c) * 0.5
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return (v / np.maximum(n, 1e-9)).astype(np.float32)


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, local_files_only=True)
        self.name = model_name.split("/")[-1]
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True).astype(np.float32)


@functools.lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend in ("auto", "sentence-transformers"):
        try:
            emb = SentenceTransformerEmbedder(s.embedding_model)
            log.info("embedder: %s", emb.name)
            return emb
        except Exception as exc:
            if s.embedding_backend == "sentence-transformers":
                raise
            log.warning("sentence-transformers unavailable (%s); using hashing embedder", type(exc).__name__)
    return HashingEmbedder()
