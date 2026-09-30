"""Hybrid retrieval: dense (vector store) + lexical (BM25), fused with
Reciprocal Rank Fusion, followed by a relevance gate."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.nlp.stats import _EN_STOP
from backend.rag.embedder import Embedder
from backend.rag.store import VectorStore

RRF_K = 60


def bm25_tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _EN_STOP and len(t) > 1]


@dataclass
class Retrieved:
    id: str
    text: str
    page_start: int
    page_end: int
    section_path: str
    score: float
    dense: float
    bm25: float


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


def retrieve(
    question: str,
    document_id: str,
    chunks: list[dict],
    embedder: Embedder,
    store: VectorStore,
    top_k: int = 5,
    candidates: int = 20,
    min_dense: float = 0.15,
) -> list[Retrieved]:
    """``chunks``: dicts with id/text/page_start/page_end/section_path (from the DB)."""
    if not chunks or not question.strip():
        return []
    by_id = {c["id"]: c for c in chunks}
    qvec = embedder.embed([question])[0]
    dense = [(cid, s) for cid, s in store.query(document_id, qvec, candidates) if cid in by_id]
    dense_scores = dict(dense)

    corpus = [bm25_tokens(c["text"]) for c in chunks]
    q_tokens = bm25_tokens(question)
    bm25_scores: dict[str, float] = {}
    if q_tokens and any(corpus):
        bm = BM25Okapi(corpus)
        raw = bm.get_scores(q_tokens)
        bm25_scores = {c["id"]: float(s) for c, s in zip(chunks, raw)}
    bm_rank = [cid for cid, s in sorted(bm25_scores.items(), key=lambda t: -t[1]) if s > 0][:candidates]

    fused = rrf([[cid for cid, _ in dense], bm_rank])
    # Relevance gate: need lexical evidence OR a reasonably similar dense hit.
    best_dense = max(dense_scores.values(), default=0.0)
    if not bm_rank and best_dense < min_dense:
        return []
    out = []
    for cid, score in sorted(fused.items(), key=lambda t: -t[1])[:top_k]:
        c = by_id[cid]
        out.append(
            Retrieved(
                id=cid,
                text=c["text"],
                page_start=c["page_start"],
                page_end=c["page_end"],
                section_path=c.get("section_path", ""),
                score=round(score, 5),
                dense=round(dense_scores.get(cid, 0.0), 4),
                bm25=round(bm25_scores.get(cid, 0.0), 4),
            )
        )
    return out
