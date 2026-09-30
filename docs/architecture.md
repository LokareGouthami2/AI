# Architecture

WriteAI is a modular monolith: one FastAPI service, one React SPA, and a set of
domain packages that each own one job and can be tested (and explained) in
isolation. The full up-front design is in [design.md](design.md); this page
describes the system **as built**.

```text
React SPA (Vite)                                     FastAPI (backend/main.py)
┌────────────────────────────────────┐   REST/JSON   ┌────────────────────────────────────────────┐
│ pages/  Landing Dashboard Upload   │ ────────────► │ api/routes.py   error envelope, rate limit, │
│         Analysis Editor Study      │               │                 optional token, headers     │
│         Handwriting & Download     │               ├────────────────────────────────────────────┤
│ editor/ TipTap + closed schema     │               │ services/  documents content render study   │
│         WDM converters, autosave   │               │            jobs (thread pool, jobs table)   │
│ preview/ revision-pinned preview   │               ├──────┬──────┬─────┬─────┬─────┬──────┬──────┤
│ study/  flashcards quiz ask        │               │docu- │ nlp  │ ml  │ llm │ rag │layout│quali-│
└────────────────────────────────────┘               │ments │      │     │     │     │hand- │ ty   │
                                                     │      │      │     │     │     │writ. │      │
                                                     │      │      │     │     │     │pdf   │      │
                                                     ├──────┴──────┴─────┴─────┴─────┴──────┴──────┤
                                                     │ SQLAlchemy (SQLite/PostgreSQL) · file store  │
                                                     │ ChromaDB vectors · ml_models/*.joblib        │
                                                     └──────────────────────────────────────────────┘
```

## Package responsibilities

| Package | Responsibility | Key files |
|---|---|---|
| `documents/` | Upload validation (magic bytes, limits, zip-bomb guard), private storage, PDF/DOCX/TXT extraction, OCR | `validation.py`, `storage.py`, `extract.py`, `ocr.py` |
| `nlp/` | Unicode cleanup, header/footer removal, de-hyphenation, line→block merging, stats, readability, keyphrases, injection flags, section tree | `preprocess.py`, `stats.py`, `structure.py` |
| `ml/` | Section classifier: features, synthetic data generator, training/evaluation, runtime prediction with rule fallback | `features.py`, `dataset.py`, `train.py`, `predict.py` |
| `llm/` | Provider interface (Claude + offline extractive engine), prompts, output schemas, validation → repair → fallback | `provider.py`, `service.py`, `extractive.py` |
| `rag/` | Structure-aware chunking, embedders, vector store, BM25 + RRF retrieval, evaluation | `chunker.py`, `retriever.py`, `evaluate.py` |
| `editor/` | WriteAI Document Model (WDM), normalisation, hashing, AI→WDM conversion, diff | `wdm.py`, `from_llm.py`, `diff.py` |
| `layout/` | Deterministic page layout → display list | `engine.py`, `fonts.py`, `settings.py` |
| `handwriting/` | Style presets, seeded bounded variation, inks, paper colours | `styles.py` |
| `pdf/` | ReportLab vector PDF, raster preview, metadata | `render.py` |
| `quality/` | Pre-render layout checks and post-render PDF audit | `checker.py`, `pdf_inspect.py` |
| `services/` | Orchestration, transactions, background jobs | `documents.py`, `content.py`, `render.py`, `study.py` |

Dependency direction: `api → services → domain packages → database`. Domain
packages never import FastAPI.

## The one invariant

> Every preview and final PDF is rendered from the stored document **head** at
> a revision the client names. The client flushes autosave first; the server
> rejects a stale revision with `409 STALE_REVISION`.

Consequences:

* The original AI output is never rendered after the user edits. It is only
  the *initial* head (version 1).
* The PDF's metadata carries `writeai:content_hash` and `writeai:revision`, so
  any downloaded file can be traced to an exact document version.
* Preview images are rasterised from the *same* PDF bytes, so preview and final
  can't drift.
* `GET /download` without a render id refuses to serve a PDF whose content hash
  no longer matches the head (`409 STALE_RENDER`).

## Runtime topology

* **Local / portfolio:** one Uvicorn process with an in-process job runner, SQLite,
  local files and embedded ChromaDB. `docker compose up` runs the API and an
  nginx container that serves the SPA and proxies `/api`.
* **Scale-out path:** PostgreSQL (`WRITEAI_DATABASE_URL`), a real queue (RQ or
  Celery) behind `services/jobs.py`, S3-compatible storage behind
  `documents/storage.py`, and pgvector behind `rag/store.py`. These are
  interface swaps rather than rewrites.

## Differences from the original design

| Design | As built | Why |
|---|---|---|
| Alembic migrations | `Base.metadata.create_all` | Single-schema v1; Alembic is listed as future work |
| Separate `flashcards` / `quiz_questions` tables | JSON columns on `flashcard_sets` / `quizzes` | Sets are always edited and saved as a whole |
| TanStack Query | Small `useAsync` hook + explicit calls | Few server-state screens; fewer dependencies |
| MiniLM embeddings by default | Hashing embedder unless MiniLM is cached locally | Hugging Face is blocked in the build environment. MiniLM switches on automatically when available |
| Claude Sonnet as default model | `claude-opus-5-5` (configurable) | Current recommended default; effort is configurable |
