# Ask Your Document — RAG

```text
section tree ─► chunker ─► embed ─► vector store (ChromaDB)    ┐
                               └─► chunk rows (SQL, for BM25)   │ built at analysis time
question ─► embed ─► dense top-20 ─┐                            │
         └► BM25 top-20 ───────────┴► Reciprocal Rank Fusion ─► top-5 ─► relevance gate
                                                                      │
      LLM (answer only from <chunk id=c1..c5>, JSON: answer|null, citations, confidence)
                                                                      │
      citation validation (ids ⊆ retrieved) ─► pages resolved server-side ─► UI
```

## Chunking (`rag/chunker.py`)

* Chunks never cross a section boundary. Within a section, sentences are
  packed to about 350 tokens with about 50 tokens of sentence overlap.
* Formulas, references, questions and answers are atomic units and never
  split.
* Each chunk is prefixed with its section heading ("2.2 Unsupervised
  Learning: …"), which helps both BM25 and embeddings. It stores
  `section_path` and `page_start`–`page_end`.

## Embeddings (`rag/embedder.py`)

* `all-MiniLM-L6-v2` (sentence-transformers) when it's cached locally. It's
  never downloaded at request time.
* Otherwise the **hashing embedder**: word 1–2-gram and char 3–5-gram feature
  hashing into 1024 dimensions, log-scaled and L2-normalised. It's lexical
  rather than semantic, but deterministic and dependency-free.

## Retrieval (`rag/retriever.py`)

* Dense cosine search (ChromaDB with `hnsw:space=cosine`, filtered by
  `document_id`) fused with BM25 (`rank_bm25`) through **Reciprocal Rank
  Fusion** (k = 60). RRF combines rankings without calibrating two different
  score scales.
* **Relevance gate:** no BM25 hit *and* best dense similarity below 0.15
  means nothing is retrieved, and the answer is "not in the document".

## Grounded answering

* The prompt contains only the retrieved chunks, under short aliases
  (`c1..c5`), plus the rule "answer only from these; otherwise
  `answer: null`".
* The server drops citations to ids that weren't retrieved, and drops the
  answer entirely if no valid citation remains.
* Page numbers come from the stored chunk rows, never from model text.

## Evaluation (`python -m backend.rag.evaluate`)

24 hand-written questions over the 3 gold documents: 19 answerable (each with
an evidence string that must appear in a retrieved chunk), 5 unanswerable.
Measured with the hashing embedder and the **offline extractive answerer**:

| Metric | Value |
|---|---|
| Retrieval Recall@1 | 0.895 |
| Retrieval Recall@5 | **1.000** |
| MRR | 0.947 |
| Answer contains the evidence (offline answerer) | 0.947 |
| Unanswerable questions correctly refused | **5 / 5** |
| Answerable questions wrongly refused | 0 |

Source: `ml_models/rag_metrics.json` (includes every question and answer).
With Claude as the answerer, answer quality should be higher; that path wasn't
measured here (no API key in the build environment).
