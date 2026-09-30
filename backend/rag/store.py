"""Vector store interface with a ChromaDB implementation and an in-memory one."""

from __future__ import annotations

import functools
import logging
import re

import numpy as np

from backend.config import get_settings

log = logging.getLogger(__name__)


class VectorStore:
    def add(self, document_id: str, ids: list[str], vectors: np.ndarray, metadatas: list[dict]) -> None:
        raise NotImplementedError

    def query(self, document_id: str, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        """Return (chunk_id, cosine_similarity) best-first."""
        raise NotImplementedError

    def delete_document(self, document_id: str) -> None:
        raise NotImplementedError


class InMemoryStore(VectorStore):
    def __init__(self):
        self._data: dict[str, tuple[list[str], np.ndarray]] = {}

    def add(self, document_id, ids, vectors, metadatas):
        old_ids, old = self._data.get(document_id, ([], np.zeros((0, vectors.shape[1]), dtype=np.float32)))
        self._data[document_id] = (old_ids + list(ids), np.vstack([old, vectors]))

    def query(self, document_id, vector, k):
        ids, m = self._data.get(document_id, ([], None))
        if not ids:
            return []
        sims = m @ vector
        order = np.argsort(-sims)[:k]
        return [(ids[i], float(sims[i])) for i in order]

    def delete_document(self, document_id):
        self._data.pop(document_id, None)


class ChromaStore(VectorStore):
    def __init__(self, path: str, embedder_name: str):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False))
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", embedder_name)[:50]
        # Embeddings are always supplied by us; Chroma never downloads a model.
        self.col = self.client.get_or_create_collection(name=f"chunks_{slug}", metadata={"hnsw:space": "cosine"}, embedding_function=None)

    def add(self, document_id, ids, vectors, metadatas):
        metas = [{**m, "document_id": document_id} for m in metadatas]
        self.col.upsert(ids=list(ids), embeddings=vectors.tolist(), metadatas=metas)

    def query(self, document_id, vector, k):
        n = self.col.count()
        if n == 0:
            return []
        res = self.col.query(query_embeddings=[vector.tolist()], n_results=min(k, n), where={"document_id": document_id})
        ids = res["ids"][0]
        dists = res["distances"][0]
        return [(i, 1.0 - float(d)) for i, d in zip(ids, dists)]

    def delete_document(self, document_id):
        self.col.delete(where={"document_id": document_id})


@functools.lru_cache(maxsize=1)
def get_store() -> VectorStore:
    from backend.rag.embedder import get_embedder

    s = get_settings()
    if s.env == "test":
        return InMemoryStore()
    try:
        s.ensure_dirs()
        return ChromaStore(str(s.vector_dir), get_embedder().name)
    except Exception as exc:  # pragma: no cover - chroma optional
        log.warning("ChromaDB unavailable (%s); using in-memory vector store", exc)
        return InMemoryStore()
