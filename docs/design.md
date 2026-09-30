# WriteAI 2.0 — System Design

> **Understand. Edit. Learn. Create.**
>
> Status: **Implemented.** This is the original up-front design. The system as built,
> including deliberate deviations, is described in [architecture.md](architecture.md);
> measured results are in [evaluation.md](evaluation.md).

---

## Table of contents

1. [Complete architecture](#1-complete-architecture)
2. [Folder structure](#2-folder-structure)
3. [Technology choices and reasons](#3-technology-choices-and-reasons)
4. [Database schema](#4-database-schema)
5. [AI/ML pipeline](#5-aiml-pipeline)
6. [RAG pipeline](#6-rag-pipeline)
7. [Editable editor architecture](#7-editable-editor-architecture)
8. [Editor-to-PDF data flow](#8-editor-to-pdf-data-flow)
9. [API architecture](#9-api-architecture)
10. [ML dataset strategy](#10-ml-dataset-strategy)
11. [Development phases](#11-development-phases)
12. [Testing strategy](#12-testing-strategy)
13. [Major technical risks](#13-major-technical-risks)
14. [Security considerations](#14-security-considerations)

---

## 1. Complete architecture

### 1.1 Guiding principles

| Principle | Consequence |
|---|---|
| **The edited document is the only rendering source.** | Renderer reads a stored, revisioned *WriteAI Document Model* (WDM). It never sees raw AI output. |
| **Right tool per job.** | Deterministic code for extraction, layout, validation. Classical ML for section classification. LLM only for language generation. RAG for grounded Q&A. |
| **AI output is untrusted input.** | Every LLM response is schema-validated and converted by our code into WDM. The LLM can't emit formatting marks, so it can't introduce underline. |
| **Preview == final.** | Preview and final PDF share one layout pass and one display list; only the output backend differs. |
| **Reproducible.** | Handwriting "randomness" is seeded from `(content_hash, settings_hash)`, so the same input always gives byte-stable layout. |
| **User control.** | Nothing is rendered until the user opens the editor and asks for it. |

### 1.2 Logical architecture

```text
┌────────────────────────────── React (Vite, JS, plain CSS) ──────────────────────────────┐
│ Landing │ Dashboard │ Upload │ Analysis │ Editor (TipTap) │ Study │ Settings │ Preview   │
│                                   │                                                     │
│   services/api.js  ←→  editor/wdm/ (TipTap JSON ⇄ WDM converter, pure functions)         │
│   autosave (debounce 1.5 s, flush-on-demand)  ·  revision tracking  ·  TanStack Query    │
└───────────────────────────────────┬─────────────────────────────────────────────────────┘
                                    │ REST/JSON (no secrets in browser)
┌───────────────────────────────────▼─────────────────────────────────────────────────────┐
│ FastAPI  api/  (routers, request validation, error mapping, rate limit, size limits)     │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ services/  (orchestration: DocumentService, GenerationService, RenderService, ...)       │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┤
│documents/│  nlp/    │   ml/    │  llm/    │  rag/    │ editor/  │ layout/  │ quality/    │
│extract,  │ clean,   │ features,│ provider,│ chunk,   │ WDM      │ measure, │ geometry,   │
│OCR       │ segment, │ classify,│ prompts, │ embed,   │ schema,  │ wrap,    │ coverage,   │
│          │ keywords │ evaluate │ validate │ retrieve │ normalize│ paginate │ PDF audit   │
│          │          │          │          │          │ diff     │          │             │
│          │          │          │          │          │          │ handwriting/ → pdf/     │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴─────────────┤
│ database/  SQLAlchemy 2 + Alembic (SQLite dev / PostgreSQL prod)  ·  file store (uploads,│
│            renders)  ·  ChromaDB (vectors)  ·  ml_models/ (joblib artefacts + model card)│
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Layering rule:** `api → services → domain packages → database`. Domain packages
(`nlp`, `ml`, `layout`, …) never import FastAPI or each other's internals, so each is
unit-testable in isolation and explainable in an interview on its own.

### 1.3 End-to-end pipeline

```text
Upload ─► validate (magic bytes, size, pages) ─► store (uuid name, private dir)
  │
  ▼
Extract ─► PDF: PyMuPDF spans (text, font, size, bold, bbox, page)
           DOCX: python-docx paragraphs + style names
           TXT: charset detection, line model
           Scanned page (no text layer)? ─► OpenCV preprocess ─► Tesseract OCR (+ confidence)
  │
  ▼
NLP ─► line merge, de-hyphenation, header/footer removal, unicode normalisation,
       sentence split (spaCy), keyphrases, readability, language detection
  │
  ▼
ML ─► segment classifier (TF-IDF + layout features ─► Logistic Regression)
      ─► labelled segments {TITLE, HEADING, ..., REFERENCE} + confidence
  │
  ▼
Structure builder (deterministic) ─► section tree with page provenance
  │                                     │
  │                                     └──► RAG index (chunks + embeddings)
  ▼
LLM (mode = Preserve | Clean | Smart | Assignment | Exam | Simple)
      ─► JSON (schema-constrained) ─► Pydantic validation ─► repair/fallback
  │
  ▼
WDM converter ─► Structured Document (revision 1, version 1 "AI generated")
  │
  ▼
Editor (TipTap) ─► user edits ─► autosave PUT /content (revision n)
  │
  ▼
Preview/Render(expected_revision=n) ─► Layout engine ─► Display list
      ─► Quality checker ─► PDF backend (ReportLab) / PNG preview (PyMuPDF raster)
      ─► Post-render audit (extract text from PDF, compare to WDM)
  │
  ▼
Download (PDF whose metadata carries content_hash + revision)
```

### 1.4 Runtime topology

- **v1 (portfolio / local):** one FastAPI process + in-process job runner
  (`asyncio` task queue with a `jobs` table for status). SQLite, local file store,
  embedded ChromaDB. `docker compose up` starts backend + static frontend (nginx).
- **Scale-out path (documented, not built):** Postgres, Redis + RQ/Celery workers for
  OCR/LLM/render jobs, S3-compatible object store, pgvector or hosted vector DB. The
  `JobRunner`, `FileStore` and `VectorStore` interfaces are what make that a config
  change rather than a rewrite.

---

## 2. Folder structure

```text
writeai/                             (repository root)
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── playwright.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                   router
│       ├── styles/                   tokens.css, base.css (no Tailwind)
│       ├── components/               Button, Modal, Toast, SaveIndicator, FileDrop, ...
│       ├── pages/                    Landing, Dashboard, Upload, Analysis, Editor,
│       │                             Study, HandwritingSettings, Preview, Download
│       ├── editor/
│       │   ├── DocumentEditor.jsx    TipTap instance
│       │   ├── Toolbar.jsx
│       │   ├── extensions/           FontSize, PasteSanitizer, restricted schema
│       │   ├── wdm/                  toWdm.js, fromWdm.js, schema.js (pure, unit-tested)
│       │   ├── autosave.js           debounce + flush + revision/conflict handling
│       │   └── VersionHistory.jsx
│       ├── preview/                  PreviewPane, PageThumb, SettingsPanel
│       ├── study/                    Flashcards, Quiz, AskDocument
│       ├── services/                 api.js (fetch wrapper), documents.js, study.js
│       ├── utils/
│       └── __tests__/                Vitest unit tests
│   └── e2e/                          Playwright: keyboard, clipboard, acceptance test
│
├── backend/
│   ├── main.py                       app factory
│   ├── config.py                     pydantic-settings (env vars)
│   ├── api/                          routers: documents, content, study, render, jobs
│   ├── services/                     orchestration, transactions, job dispatch
│   ├── schemas/                      Pydantic request/response models
│   ├── models/                       SQLAlchemy ORM models
│   ├── database/                     session, migrations (alembic/), repositories
│   ├── documents/                    validation, storage, extractors (pdf, docx, txt), ocr
│   ├── nlp/                          cleaning, segmentation, header_footer, keywords, stats
│   ├── ml/                           features.py, train.py, predict.py, evaluate.py, labels.py
│   ├── llm/                          provider.py (Anthropic + Mock), prompts/, output_schemas.py,
│   │                                 validate.py, modes.py, map_reduce.py
│   ├── rag/                          chunker.py, embedder.py, vector_store.py, bm25.py,
│   │                                 retriever.py, answer.py
│   ├── editor/                       wdm.py (schema), normalize.py, from_llm.py, diff.py, hashing.py
│   ├── layout/                       metrics.py, linebreak.py, paginate.py, display_list.py
│   ├── handwriting/                  styles.py, jitter.py, ink.py, paper.py
│   ├── pdf/                          reportlab_backend.py, raster_preview.py, metadata.py
│   ├── quality/                      geometry.py, coverage.py, formatting.py, pdf_audit.py
│   ├── assets/fonts/                 OFL/Apache handwriting fonts + LICENSE files
│   └── tests/                        pytest: unit per package + api + acceptance
│
├── ml_models/                        section_classifier_v{n}.joblib, model_card.md, metrics.json
├── datasets/
│   ├── raw/                          (gitignored) source documents
│   ├── annotations/                  labelled segments (JSONL), guidelines.md
│   └── splits/                       train/val/test doc-id lists
├── docs/                             design.md (this file) + per-topic docs (Phase 17)
├── screenshots/
├── tests/                            cross-stack acceptance fixtures (sample PDFs)
├── docker/                           backend.Dockerfile, frontend.Dockerfile, nginx.conf
├── docker-compose.yml
├── .github/workflows/ci.yml
├── README.md
├── requirements.txt                  (+ requirements-dev.txt)
├── .env.example
└── .gitignore
```

---

## 3. Technology choices and reasons

| Area | Choice | Why (and what was rejected) |
|---|---|---|
| Backend | **Python 3.11 + FastAPI + Pydantic v2** | Async I/O for LLM calls, automatic OpenAPI docs, Pydantic is the same tool we use to validate LLM output. |
| ORM / DB | **SQLAlchemy 2 + Alembic; SQLite → PostgreSQL** | Zero-setup locally; JSON columns work on both. Migrations from day one. |
| PDF extraction | **PyMuPDF** | Gives span-level font size, flags (bold/italic), bbox — the layout features the classifier needs. `pdfplumber` is slower; `pypdf` loses font info. |
| DOCX | **python-docx** | Paragraph style names (`Heading 1`) double as weak labels for the dataset. |
| OCR | **Tesseract (pytesseract) + OpenCV preprocessing** | Offline, free, per-word confidence. Cloud OCR would need another key and send user documents to a third party. |
| NLP | **spaCy (`en_core_web_sm`)**, YAKE keyphrases, `textstat` | Fast, deterministic sentence segmentation and tokenisation; explainable. |
| ML | **scikit-learn**: TF-IDF + LogisticRegression (baseline), LinearSVC, **sentence-transformers** embeddings + LR | Classical ML is the right size for a 13-class, short-text problem; interpretable coefficients; fast CPU inference. |
| LLM | **Anthropic Claude via official SDK**, behind a `LLMProvider` interface; `MockProvider` for tests | Structured output through tool/JSON-schema use; provider interface keeps the rest of the system vendor-neutral. Default `claude-sonnet-5-5` for generation, `claude-haiku-4-5` for cheap tasks (flashcards, repair). Configurable via env. |
| Embeddings | **`sentence-transformers/all-MiniLM-L6-v2`** (local) | No API key needed, 384-d, fast on CPU. Same model reused for classifier comparison. |
| Vector store | **ChromaDB (embedded, persistent)** behind `VectorStore` | Metadata filtering by `document_id`/page, no server to run. FAISS lacks metadata filters; pgvector is the production swap. |
| Lexical retrieval | **rank_bm25** | Hybrid search fixes dense retrieval's weakness on exact terms/formula names. |
| Editor | **TipTap v2 (ProseMirror)** | Schema-enforced document tree, transactional undo/redo, robust clipboard & IME handling, JSON serialisation. Lexical/Slate are good but ProseMirror's schema lets us make the editor *unable* to create structures the renderer can't draw. A textarea is explicitly out. |
| Frontend | **React 18 + Vite + JavaScript + plain CSS (custom properties, CSS modules)**, React Router, TanStack Query | Per requirements; TanStack Query handles server cache/invalidation so previews never show stale data. |
| Layout | **Custom Python layout engine** using font metrics from ReportLab `pdfmetrics`/fontTools | We need handwriting-specific behaviour (baseline snapping to ruled lines, per-glyph jitter) that HTML→PDF engines can't provide deterministically. |
| PDF | **ReportLab** (vector output) + **PyMuPDF** (rasterise PDF → PNG for preview, and extract text for audits) | Preview is a raster of the *actual* PDF, so preview/final drift is impossible. |
| Handwriting | OFL/Apache licensed fonts (e.g. Caveat, Kalam, Patrick Hand, Indie Flower, Homemade Apple) + procedural variation | Legally redistributable; variation (baseline wobble, slant, size, spacing, ink pressure) makes it look hand-made while staying legible. |
| Testing | pytest, hypothesis (property tests), Vitest + Testing Library, **Playwright** (real Chromium) | jsdom can't faithfully run `contenteditable`; keyboard/clipboard behaviour must be tested in a real browser. |
| Deploy | Docker + docker compose; GitHub Actions CI | One command demo; image bundles Tesseract and fonts. |

---

## 4. Database schema

All ids are UUIDv4 strings. Timestamps are UTC. `JSON` = JSON column (SQLite JSON1 / Postgres JSONB).

```text
documents
  id              PK
  owner_id        nullable (v1 single-user; reserved for auth)
  title           text
  original_name   text           (display only, never used as a path)
  stored_path     text           (uuid filename in private upload dir)
  mime_type       text
  sha256          text           (dedupe + integrity)
  size_bytes      int
  page_count      int
  status          enum(uploaded, extracting, extracted, analyzing, analyzed,
                       generating, ready, failed)
  error           text nullable
  created_at, updated_at, deleted_at (soft delete, then purge job)

document_pages
  id PK, document_id FK, page_number int,
  text            text
  source          enum(text_layer, ocr, docx, txt)
  ocr_confidence  float nullable
  width, height   float

segments                          (one per extracted line/block; ML input & output)
  id PK, document_id FK, page_number int, order_index int
  text            text
  features        JSON           (font_size_ratio, is_bold, caps_ratio, bbox, indent, ...)
  predicted_label enum(TITLE, HEADING, SUBHEADING, PARAGRAPH, DEFINITION, EXAMPLE,
                       PROCEDURE, IMPORTANT_POINT, FORMULA, QUESTION, ANSWER,
                       CONCLUSION, REFERENCE)
  confidence      float
  model_version   text

analyses
  id PK, document_id FK (unique), stats JSON (words, sentences, readability, language,
  label distribution, keyphrases, ocr pages), created_at

generations                       (audit trail of every AI output)
  id PK, document_id FK
  mode            enum(preserve, clean, smart, assignment, exam, simple)
  provider, model text, prompt_version text
  input_tokens, output_tokens int
  output_json     JSON           (validated LLM payload, pre-WDM)
  status          enum(ok, repaired, fallback, failed)
  created_at

document_contents                 (HEAD — the single source of truth for rendering)
  document_id     PK/FK
  revision        int            (monotonic; optimistic concurrency token)
  content         JSON           (WDM)
  content_hash    text           (sha256 of canonical JSON)
  updated_at

document_versions                 (immutable snapshots)
  id PK, document_id FK
  version_number  int            (unique per document)
  revision        int            (head revision it snapshotted)
  content         JSON
  content_hash    text
  source          enum(ai_generated, manual_save, checkpoint, pre_restore, restored, pre_render)
  label           text nullable
  created_at
  UNIQUE(document_id, version_number)

chunks
  id PK, document_id FK, order_index int
  text, section_path text        ("Ch 2 > Supervised learning")
  page_start, page_end int
  token_count int
  embedding_model text           (vector itself lives in ChromaDB under the same id)

flashcard_sets / flashcards
  set: id, document_id, generation_id, created_at, updated_at
  card: id, set_id, order_index, question, answer,
        difficulty enum(easy, medium, hard), source_pages JSON, edited bool

quizzes / quiz_questions
  quiz: id, document_id, generation_id, created_at, updated_at
  question: id, quiz_id, order_index, question, options JSON[4], correct_index int(0-3),
            explanation, difficulty, source_pages JSON, edited bool

qa_logs
  id, document_id, question, answer, cited_chunk_ids JSON, grounded bool, latency_ms, created_at

render_settings
  document_id PK/FK, settings JSON (style, ink, paper, font_size, margins, line_spacing,
  page_size, page_numbers, seed_mode), updated_at

render_jobs
  id PK, document_id FK
  kind            enum(preview, final)
  revision        int, content_hash text, settings_hash text
  status          enum(queued, running, succeeded, failed, rejected_by_quality)
  output_path     text nullable  (PDF) ; preview_paths JSON
  quality_report  JSON
  created_at, finished_at

jobs                              (generic async job status for extract/analyze/generate)
  id PK, document_id FK, kind, status, progress float, error, created_at, finished_at
```

**Autosave vs versions.** Autosave overwrites `document_contents` (bumping `revision`)
— it does **not** create a version per save. Versions are created on: AI generation,
explicit "Save version", a checkpoint at most every 5 minutes of active editing,
before a restore, and for every final render (so every downloaded PDF maps to an
immutable snapshot). Restore copies a version into head as a new revision; nothing is
ever overwritten, so a restore is itself undoable.

---

## 5. AI/ML pipeline

### 5.1 Extraction & OCR (`documents/`)

- **PDF:** PyMuPDF `get_text("dict")` → spans → lines → blocks with font name, size,
  flags, bbox. A page is treated as scanned if it has < 20 extractable characters or
  images cover > 80 % of the area with no text.
- **OCR:** render page at 300 DPI → OpenCV grayscale, deskew (Hough / minAreaRect),
  adaptive threshold, denoise → Tesseract (`--psm 3`, word-level TSV with confidence).
  Low-confidence pages (< 60 mean) are flagged in the Analysis page.
- **DOCX:** paragraphs + runs (bold/italic) + style names; tables flattened to rows.
- **TXT:** `charset-normalizer` detection, blank-line paragraph model.
- Output: `ExtractedDocument{pages[], lines[] with features, provenance}`.

### 5.2 NLP preprocessing (`nlp/`)

1. Unicode NFKC normalisation, ligature and smart-quote folding, control-char strip.
2. **Header/footer removal:** lines repeating (fuzzy, digits masked) in the top/bottom
   band on ≥ 50 % of pages are dropped; page-number patterns removed.
3. **De-hyphenation** of line-end breaks when the joined word is in vocabulary.
4. **Line → block merge** using vertical gap, indent and font continuity.
5. Sentence segmentation (spaCy), tokenisation, stop-word flags.
6. Keyphrases (YAKE), readability (Flesch-Kincaid), language detection.
7. Feature extraction for the classifier (§5.3).

### 5.3 ML section classifier (`ml/`)

Input unit: one **segment** (a merged block/line). Features:

| Group | Features |
|---|---|
| Lexical | TF-IDF word 1–2-grams + char 2–5-grams (char n-grams catch `=`, `Σ`, `Q1.`, `Fig.`) |
| Layout | font size ÷ document median, bold, italic, all-caps ratio, indent, vertical gap before/after, relative page position, line count |
| Surface | length in tokens, ends with `:`/`?`/`.`, starts with number/bullet/`Q`, digit ratio, math-symbol ratio, contains "is defined as"/"refers to", year+author pattern |
| Context | predicted-or-layout features of previous & next segment (window of 1) |

Models (all in a single `sklearn.Pipeline` with `ColumnTransformer`):

1. **Baseline:** TF-IDF + layout → `LogisticRegression(class_weight="balanced")`.
2. **Comparison A:** same features → `LinearSVC` (+ `CalibratedClassifierCV` for confidences).
3. **Comparison B:** `all-MiniLM-L6-v2` embedding ⊕ layout features → LogisticRegression.

Selection: best **macro-F1 on the validation split**; final numbers reported once on
the held-out test split. Hyper-parameters via grouped CV (groups = source document).
Artefacts: `ml_models/section_classifier_vN.joblib`, `metrics.json` (accuracy, macro/
weighted P/R/F1, per-class report, confusion matrix PNG), `model_card.md`.
**Only measured values are ever written to docs or README** — they are generated by
`python -m backend.ml.evaluate` and copied from `metrics.json`, never typed by hand.

Runtime: segments below a confidence threshold (default 0.45) fall back to a
deterministic layout rule (e.g. largest font on page 1 → TITLE) and are marked
`low_confidence` in the Analysis UI.

### 5.4 Structure builder (deterministic)

Labelled segments → section tree (`TITLE` root, `HEADING`/`SUBHEADING` open sections,
other labels become typed content). Every node keeps `source_pages`. This tree feeds
both the LLM (as compact structured input) and the RAG chunker.

### 5.5 LLM document understanding (`llm/`)

- **Provider interface:** `generate_structured(system, messages, schema, max_tokens) → dict`.
  Implementations: `AnthropicProvider` (tool-use with JSON schema for structured
  output), `MockProvider` (deterministic fixtures for tests/offline demos).
- **Modes** each have a versioned prompt (`prompts/<mode>.v1.md`) and an output schema:

| Mode | LLM? | Output schema (simplified) |
|---|---|---|
| Preserve | **No** — deterministic tree → WDM | — |
| Clean Notes | Optional (light rewrite) | `sections[{heading, blocks[{type, text}]}]` |
| Smart Notes | Yes | `title, sections[{heading, level, blocks[{type: paragraph|bullets|numbered|definition|example|formula|key_point, text|items}]}]` |
| Assignment | Yes | `title, introduction, objectives[], main_sections[], examples[], conclusion, references[]` |
| Exam Revision | Yes | `definitions[{term, definition}], formulas[{name, expression, meaning}], key_concepts[], important_questions[]` |
| Simple Explanation | Yes | `sections[{heading, blocks}]` with reading-level constraint |
| Flashcards | Yes | `cards[{question, answer, difficulty, source_pages[]}]` |
| Quiz | Yes | `questions[{question, options[4], correct_index, explanation, difficulty, source_pages[]}]` |

- **Long documents:** map-reduce over sections (map: per-section notes with page refs;
  reduce: merge/deduplicate into final schema) to stay within context and cost budgets.
- **Validation chain:** JSON parse → Pydantic model (types, lengths, enums, 4 options,
  `correct_index ∈ [0,3]`, `source_pages ⊆ document pages`) → semantic checks (no empty
  sections, no duplicate questions) → **one repair attempt** (send validation errors
  back, cheaper model) → **fallback** to Preserve-mode output with a UI notice. The
  editor only ever receives a validated WDM; malformed AI output cannot reach it.
- **No formatting from the LLM.** Output schemas contain plain strings only — no
  markdown, no HTML, no marks. `editor/from_llm.py` strips any stray markdown
  (`**`, `__`, `<u>`) and maps block types to WDM nodes. Therefore **no underline or
  highlighting can be introduced by AI**; headings are distinguished only by block type.

---

## 6. RAG pipeline

```text
Section tree ─► structure-aware chunker ─► embed (MiniLM) ─► ChromaDB (+ BM25 index)
                                                                    │
Question ─► normalise ─► embed ─► dense top-20 ─┐                   │
                       └► BM25 top-20 ──────────┴► RRF fusion ─► top-k (5) chunks
                                                                    │
                          relevance gate (max cosine < τ ⇒ "not in document")
                                                                    │
                    LLM (answer ONLY from numbered context, cite chunk ids, JSON)
                                                                    │
                    citation validator (ids exist in retrieved set) ─► answer + pages
```

- **Chunking:** split on section boundaries first; within a section pack sentences to
  ~350 tokens with ~50-token overlap; never split a formula or list item. Each chunk
  stores `section_path`, `page_start/page_end`.
- **Hybrid retrieval:** dense + BM25 fused with Reciprocal Rank Fusion (k=60) — robust
  for exact terms (e.g. "ReLU", "Bayes theorem"). Optional cross-encoder rerank
  (`ms-marco-MiniLM-L-6-v2`) behind a flag.
- **Grounding rules:** context passed as `<chunk id="c3" pages="4-5">…</chunk>`; system
  prompt: answer only from chunks, otherwise return `{"answer": null, "reason":
  "not_found"}`. Output schema `{answer, citations[chunk_id], confidence}`; citations are
  validated against the retrieved set; pages are resolved server-side from chunk ids (the
  LLM never states page numbers itself). Answers with zero valid citations are
  downgraded to "I couldn't find this in the document."
- **Evaluation:** a hand-written QA set per sample document (question, gold pages,
  answerable yes/no) → retrieval Recall@5, MRR, citation accuracy, and refusal accuracy on
  unanswerable questions. Reported from measurements only.
- **Lifecycle:** index is built after analysis; deleted with the document.

---

## 7. Editable editor architecture

### 7.1 WriteAI Document Model (WDM) — canonical format

```json
{
  "schema_version": 1,
  "title": "Machine Learning",
  "blocks": [
    { "id": "b1", "type": "heading", "level": 1, "align": "left",
      "content": [ { "type": "text", "text": "Introduction" } ] },
    { "id": "b2", "type": "paragraph", "align": "left",
      "content": [ { "type": "text", "text": "Machine learning is " },
                   { "type": "text", "text": "a branch of AI", "marks": ["bold"] },
                   { "type": "hard_break" },
                   { "type": "text", "text": "It allows computers to learn from data." } ] },
    { "id": "b3", "type": "paragraph", "align": "left", "content": [] },
    { "id": "b4", "type": "ordered_list", "start": 1,
      "items": [ { "blocks": [ { "id": "b5", "type": "paragraph",
                                 "content": [ { "type": "text", "text": "Supervised Learning" } ] } ] } ] },
    { "id": "b6", "type": "blockquote", "blocks": [ ... ] }
  ]
}
```

- **Block types:** `heading(level 1–3)`, `paragraph`, `bullet_list`, `ordered_list`,
  `list_item` (contains blocks → nested lists), `blockquote`.
- **Inline:** `text` with `marks ⊆ {bold, italic, underline}` and optional
  `font_size ∈ {small, normal, large, xlarge}`; `hard_break` (Shift+Enter).
- **Block attrs:** `align ∈ {left, center, right, justify}`.
- **Empty paragraph** (`content: []`) is meaningful: it is how "Enter twice" is stored
  and it renders as one blank line. Normalisation never removes empty paragraphs.
- Same schema exists as a Pydantic model (`backend/editor/wdm.py`) and a JS validator
  (`frontend/src/editor/wdm/schema.js`), both generated/checked against one JSON Schema
  file so they cannot drift.

### 7.2 Editor = TipTap with a restricted schema

Extensions: `Document, Paragraph, Text, Heading{levels:[1,2,3]}, Bold, Italic,
Underline, BulletList, OrderedList, ListItem, Blockquote, HardBreak, History,
TextAlign{types:[heading,paragraph]}, TextStyle + FontSize (enum sizes), Dropcursor,
Gapcursor, Placeholder`. Disabled: code, strike, images, tables, links (not
renderable in v1). Because the ProseMirror schema is closed, pasting unsupported HTML is
coerced into supported nodes rather than corrupting the document.

Built-in ProseMirror behaviour covers typing, selection (incl. multi-line), cursor/arrow
navigation, Home/End, Backspace/Delete merges, Enter (split block → new paragraph),
Shift+Enter (hard break), Ctrl/Cmd+A/C/X/V, and transactional **Undo/Redo** (Ctrl/Cmd+Z,
Ctrl/Cmd+Y and Ctrl/Cmd+Shift+Z). Drag-to-move paragraphs via Dropcursor; plus
toolbar/keyboard "Move block up/down" (Alt+↑/↓) for reliable paragraph reordering.

**Toolbar:** Undo · Redo | **B** *I* U | H1 H2 H3 ¶Normal | • 1. ❝ | ⟸ ≡ ⟹ | size | Clear formatting | Save version.
Buttons reflect active state (`editor.isActive`) and are keyboard reachable.

### 7.3 Underline policy (explicit)

- Underline mark exists but is **off by default** and only applied by the toolbar button
  or Ctrl/Cmd+U on a user selection.
- Headings are styled by size/weight only (CSS + renderer), never underline.
- AI → WDM conversion cannot produce `underline` (§5.5).
- **Paste sanitizer** (`transformPastedHTML`): strips `<u>`, `text-decoration`,
  `<mark>`/background colours from external clipboard content, so pasting from a web
  page doesn't smuggle in underlines. Internal copy/paste (ProseMirror slice) keeps
  marks the user applied.
- Renderer draws an underline **only** for runs whose `marks` contain `underline`;
  the quality checker asserts that (§8.4).

### 7.4 Conversion & round-trip guarantee

`toWdm(tiptapJSON)` and `fromWdm(wdm)` are pure functions. Property-based test
(fast-check): for random valid WDM `w`, `toWdm(fromWdm(w)) deep-equals w`. Block ids are
preserved via a `blockId` node attribute (UniqueID extension) so diffs and version
comparisons are stable.

### 7.5 Autosave & concurrency (`autosave.js`)

```text
editor.on('update') ─► dirty=true, status "Unsaved changes"
      └─► debounce 1500 ms (max-wait 10 s) ─► PUT /content {content, base_revision}
             200 ─► revision=n+1, "✓ Saved"
             409 ─► conflict (another tab) ─► offer reload / overwrite (force)
             network error ─► exponential retry, keep local draft in IndexedDB
flush() ─► cancel debounce, save now, resolve when server has the latest revision
beforeunload ─► warn if dirty
```

Only one save is in flight at a time; edits during a save are queued into the next save.

### 7.6 Version history

Side panel lists versions (number, timestamp, source, label). Actions: preview
(read-only render), compare (block-level diff via `editor/diff.py`), restore (creates
`pre_restore` snapshot → writes version into head → editor reloads, history reset).

---

## 8. Editor-to-PDF data flow

### 8.1 The invariant

> Every preview and every final PDF is rendered from `document_contents` at a
> **revision the client explicitly names**, and that revision must be the current head.

```text
[User clicks "Update Preview" / "Generate Final PDF"]
      │
      ▼
autosave.flush()  ── guarantees server head == editor state, returns revision n
      │
      ▼
POST /preview | /render  { expected_revision: n, settings }
      │
      ├─ head.revision != n  ─► 409 STALE_REVISION (client flushes again and retries)
      ▼
load WDM @ n  ─► normalize (canonical JSON) ─► content_hash
      │
      ▼
Layout engine (settings) ─► DisplayList (pages → positioned glyph runs, rules, decorations)
      │
      ▼
Quality checker (pre-render) ─► errors? ─► 422 with report (no PDF produced)
      │
      ▼
PDF backend (ReportLab) ─► PDF bytes; metadata: writeai:content_hash, revision, settings_hash
      │
      ├─ preview: rasterise pages with PyMuPDF at 110 DPI ─► PNGs (cached by
      │           (content_hash, settings_hash); cache key includes the hash, so a new
      │           edit can never hit an old cache entry)
      ▼
Post-render audit: extract text from the PDF, compare to WDM token stream
      │
      ▼
final: snapshot version (source=pre_render), store render_job, enable download
```

### 8.2 Layout engine (`layout/`)

Deterministic; pure function `layout(wdm, settings, fonts) → DisplayList`.

1. **Page geometry:** page size (A4/Letter), margins (mm → pt), text box width/height,
   header/footer bands for page numbers.
2. **Line grid:** `line_height = font_size × line_spacing`. On *ruled* paper, rule lines
   are generated from the same grid and every text baseline snaps to a rule.
3. **Measure:** glyph advance widths from the font's metrics × per-style scale, plus the
   handwriting jitter budget (widths are computed **after** applying deterministic
   per-glyph variation so wrapping and drawing use identical numbers).
4. **Line breaking:** greedy first-fit on word boundaries (inline marks preserved as
   runs), words wider than the line are force-broken; `hard_break` forces a new line;
   alignment applied per line.
5. **Block spacing:** paragraph gap = 0.5 line; heading = scaled size (H1 1.6×, H2 1.35×,
   H3 1.15×), weight via stroke, gap before 1 line; **empty paragraph = exactly one
   line**; list indent + bullet/number glyph in the hanging margin; blockquote indent.
6. **Pagination:** place line by line; if the next line doesn't fit → new page.
   **Keep-with-next:** a heading must be followed by ≥ 2 lines of its content on the same
   page (no orphan headings). **Widow/orphan:** avoid a single paragraph line alone at
   top/bottom when the paragraph has ≥ 3 lines.
7. **Page numbers** placed in the footer band.

### 8.3 Handwriting engine (`handwriting/`)

Operates on the DisplayList, adding controlled imperfection from a seeded RNG
(`seed = hash(content_hash, settings_hash, block_id, line_index)`):

- per-line baseline drift (low-frequency), per-glyph vertical jitter, slant ±,
  size ±3 %, letter/word spacing variance, occasional glyph alternates where the font
  provides them;
- ink model: blue (#1A2E8C-ish) / black, per-word opacity & stroke-width variance to
  simulate pen pressure;
- styles = (font, slant, jitter amplitudes, spacing profile) presets: *Neat*, *Casual*,
  *Cursive*, *Rushed* (still legible);
- paper: blank, ruled (with margin line), grid; drawn as vector under the text.

All variation magnitudes are bounded so the quality checker's geometry and readability
checks can prove text stays inside its box and above minimum size.

### 8.4 Quality checker (`quality/`)

Runs twice — on the DisplayList (pre-render) and on the PDF (post-render):

| Check | Method | Severity |
|---|---|---|
| Overflow / clipping | every glyph bbox (incl. jitter) ⊂ printable area | error |
| Overlap | sweep-line over line bboxes per page; no intersections between lines/blocks | error |
| Empty pages | no page may contain zero glyphs (trailing empty paragraphs are trimmed at pagination, not rendered as a blank page) | error |
| Missing / extra content | normalised token sequence of WDM == token sequence in DisplayList == text extracted from PDF (PyMuPDF), diffed with `difflib` | error |
| Broken paragraphs | paragraph split across pages leaves ≥ 2 lines each side when possible; no heading as last line | warning |
| Unreadable text | effective font size ≥ 9 pt, jitter ≤ bounds, contrast ink vs paper ≥ 4.5:1 | error |
| Invalid formatting | WDM schema valid; list nesting ≤ 3; unknown marks rejected | error |
| **Underline audit** | set of underlined token ranges drawn == set of WDM runs with `underline` | error |
| Line breaks preserved | count of empty paragraphs & hard breaks in WDM == blank lines/forced breaks in layout | error |

Returns `QualityReport{passed, errors[], warnings[], metrics{pages, lines, fill_ratio}}`,
stored with the render job and shown in the UI.

---

## 9. API architecture

Base path `/api`. JSON everywhere except upload (multipart) and download (PDF stream).
Errors use one envelope: `{"error": {"code": "STALE_REVISION", "message": "...", "details": {}}}`.
Long operations return **202 + job** and are polled via `GET /api/jobs/{job_id}`.

| Method | Path | Purpose | Request → Response |
|---|---|---|---|
| POST | `/documents/upload` | Validate + store file | multipart `file` → `201 {document}` |
| GET | `/documents` | Dashboard list | → `[{document summary}]` |
| GET | `/documents/{id}` | Metadata + status | → `{document}` |
| POST | `/documents/{id}/extract` | Text/OCR extraction | → `202 {job}` |
| POST | `/documents/{id}/analyze` | NLP + ML classification + RAG index | → `202 {job}` |
| GET | `/documents/{id}/analysis` | Stats, labelled segments | → `{stats, segments[]}` |
| POST | `/documents/{id}/generate` | AI mode → WDM (creates version) | `{mode, options}` → `202 {job}` |
| GET | `/documents/{id}/content` | **Current head** | → `{revision, content_hash, content, updated_at}` |
| PUT | `/documents/{id}/content` | **Save edited WDM** | `{content, base_revision, force?}` → `200 {revision, content_hash, updated_at}` · `409 STALE_REVISION` · `422 INVALID_DOCUMENT` |
| GET | `/documents/{id}/versions` | Version list | → `[{version_number, source, label, created_at, content_hash}]` |
| POST | `/documents/{id}/versions` | Explicit "Save version" | `{label?}` → `201 {version}` |
| GET | `/documents/{id}/versions/{n}` | Version content | → `{version, content}` |
| POST | `/documents/{id}/versions/{n}/restore` | Restore | → `{revision, content}` |
| POST | `/documents/{id}/preview` | Render preview pages | `{expected_revision, settings, pages?}` → `{render_id, pages:[{n, url}], quality}` |
| POST | `/documents/{id}/validate` | Quality check only | `{expected_revision, settings}` → `{quality_report}` |
| POST | `/documents/{id}/render` | Final PDF | `{expected_revision, settings}` → `202 {job}` → `{render_id, quality_report}` |
| GET | `/documents/{id}/download` | Latest successful final PDF | `?render_id=` → `application/pdf` (`409` if head changed since render, unless `render_id` given explicitly) |
| POST | `/documents/{id}/ask` | RAG Q&A | `{question}` → `{answer, grounded, citations[{chunk_id, pages, excerpt}]}` |
| POST | `/documents/{id}/flashcards` | Generate set | `{count, difficulty?}` → `{set}` |
| PUT | `/documents/{id}/flashcards/{set_id}` | Save edited cards | `{cards[]}` → `{set}` |
| POST | `/documents/{id}/quiz` | Generate quiz | `{count, difficulty?}` → `{quiz}` |
| PUT | `/documents/{id}/quiz/{quiz_id}` | Save edited questions | `{questions[]}` → `{quiz}` |
| GET/PUT | `/documents/{id}/render-settings` | Handwriting settings | settings JSON |
| DELETE | `/documents/{id}` | Delete file, rows, vectors, renders | → `204` |
| GET | `/jobs/{job_id}` | Job status | → `{status, progress, result?, error?}` |
| GET | `/health` | Liveness + model/fonts loaded | → `{ok, versions}` |

The 14 required endpoints are all present; the extras (versions, jobs, settings, card/quiz
save) are what autosave, version history and editable study material need.

---

## 10. ML dataset strategy

**Unit of annotation:** a segment (block) with its text *and* layout features, so
labels are learned from the same representation used at inference.

1. **Sources (licence-clean only):** OpenStax textbooks (CC BY), Wikibooks (CC BY-SA),
   LibreTexts (CC BY-NC-SA, non-commercial use noted), MIT OCW lecture notes (CC BY-NC-SA),
   plus self-written sample notes and exam papers. Mix of born-digital PDFs, DOCX, and
   a few scanned pages (to exercise OCR features). Licence recorded per file in
   `datasets/SOURCES.md`; raw files gitignored, only annotations committed.
2. **Weak labelling to bootstrap:** PDF outline/bookmarks and DOCX heading styles →
   TITLE/HEADING/SUBHEADING; regexes ("Definition", "Example", "Q1.", "Answer:",
   "References", numbered steps, `=`-dense lines → FORMULA). Produces a noisy training
   pool, each label tagged `source=weak`.
3. **Manual gold labels:** a written guideline (`datasets/annotations/guidelines.md`)
   with a definition and boundary cases per class. Target ≥ 3,000 gold segments across
   ≥ 40 documents, stratified so every class has ≥ 100 examples (rare classes —
   CONCLUSION, REFERENCE, ANSWER — are oversampled at *document selection* time, not by
   duplication). A 10 % sample is re-labelled after a week to estimate self-consistency
   (honestly reported as intra-annotator agreement, Cohen's κ).
4. **Splits by document** (70/15/15) via `GroupShuffleSplit` — lines from the same book
   never appear in both train and test, preventing leakage of layout/style.
   Test set is **gold-only** and frozen (doc ids committed in `datasets/splits/`).
5. **Experiments:** (a) gold only, (b) gold + weak, (c) gold + weak + light augmentation
   (casing/numbering perturbation). Each reported separately.
6. **Metrics:** accuracy, macro & weighted precision/recall/F1, per-class report,
   normalised confusion matrix, plus calibration (reliability curve) for the chosen model.
   Error analysis notebook documents the top confusions (e.g. HEADING↔SUBHEADING,
   PARAGRAPH↔DEFINITION).
7. **Honesty rule:** README/evaluation.md numbers are rendered from `metrics.json`
   produced by the evaluation script; if the dataset is small, that is stated.

---

## 11. Development phases

Each phase ends with: summary, changed files, decisions, run commands, tests run (with
real output), and fixes for anything failing — no silent skips.

| # | Phase | Deliverable / exit criteria |
|---|---|---|
| 1 | Architecture & setup | Repo skeleton, FastAPI app factory + `/health`, Vite app shell, config via env, Docker compose, CI running lint + empty test suites green |
| 2 | Extraction & OCR | Upload validation, PDF/DOCX/TXT extractors, OCR path with preprocessing, `document_pages` persisted; fixtures incl. a scanned PDF |
| 3 | NLP preprocessing | Header/footer removal, de-hyphenation, block merge, sentence split, features, stats; unit tests per step |
| 4 | ML classifier & evaluation | Dataset tooling, weak labeller, training/eval scripts, 3 models compared, `metrics.json`, model card, `predict` service |
| 5 | LLM understanding | Provider interface + Anthropic + Mock, prompts v1, output schemas, validation/repair/fallback, WDM converter, map-reduce |
| 6 | RAG | Chunker, embeddings, Chroma + BM25, RRF, grounded answering, citation validation, retrieval eval |
| 7 | Flashcards & quizzes | Generation + validation + editable save endpoints |
| 8 | Editor | TipTap restricted schema, toolbar, paste sanitizer, WDM converters + round-trip property tests, Playwright keyboard/clipboard tests |
| 9 | Autosave & versions | Debounced save, revision/409 handling, flush, version table, restore, diff |
| 10 | Handwriting rendering | Fonts, styles, jitter, ink, paper, ReportLab backend, raster preview |
| 11 | Layout engine | Geometry, measuring, line breaking, pagination, keep-with-next, widow/orphan; golden tests |
| 12 | Quality checker | All §8.4 checks, pre- and post-render, report schema |
| 13 | FastAPI integration | All endpoints, jobs, error envelope, OpenAPI, API tests |
| 14 | React UI integration | All pages wired, study mode, settings, preview, download |
| 15 | Testing | Coverage gaps closed, **critical acceptance test (§12.4) automated and passing** |
| 16 | Deployment | Production Dockerfiles, compose, deployment guide (Render/Fly/VM), env hardening |
| 17 | Docs & portfolio | `docs/*.md` set, README, screenshots, demo script, interview questions |

> Phases 10 and 11 are tightly coupled; 11's line-breaking core is built first inside
> phase 10's work so the handwriting engine renders real layouts from the start.

---

## 12. Testing strategy

### 12.1 Backend (pytest)

- **Unit:** each package in isolation — extractors (fixture PDFs/DOCX/TXT, scanned page),
  NLP steps, feature extraction, WDM normalisation/hashing, LLM validators (malformed
  JSON, missing fields, 3 options, bad `correct_index`, injected markdown/underline),
  chunker boundaries, RRF, layout (golden DisplayList snapshots), quality checks
  (deliberately broken DisplayLists must fail).
- **Property-based (hypothesis):** random WDM → layout never overflows/overlaps; token
  coverage always exact; render is deterministic (same input ⇒ same bytes/hash).
- **ML:** model artefact loads, predicts on known examples, output labels ⊂ enum,
  evaluation script reproduces `metrics.json` on the frozen test split.
- **API:** httpx `TestClient` — upload limits and bad types, extract/analyze/generate
  with `MockProvider`, content GET/PUT, 409 on stale revision, 422 on invalid WDM,
  versions/restore, preview/render/validate/download, delete cleans files + vectors.
- **Rendering correctness:** edited content appears in PDF text; deleted content absent;
  added paragraphs appear; blank lines preserved (count via layout + y-gaps in PDF);
  headings rendered larger; **no underline drawn unless marked** (inspect PDF drawing ops
  via PyMuPDF `get_drawings()` for horizontal strokes under text).

### 12.2 Frontend

- **Vitest:** WDM converters, round-trip property tests (fast-check), autosave state
  machine with fake timers (debounce, flush, 409, retry), toolbar state.
- **Playwright (real Chromium):** Enter, Shift+Enter, Enter×2, Backspace/Delete merges,
  arrows/Home/End, select-all, copy/cut/paste (clipboard permissions granted), undo/redo
  via keys and buttons, heading/list/alignment toggles, underline only when clicked,
  pasting underlined HTML gets sanitised, large edits (replace all, paste 5 pages),
  move block up/down.

### 12.3 CI

GitHub Actions: `ruff` + `mypy` (backend), `eslint` + `prettier --check` (frontend),
pytest, vitest, Playwright (headless), acceptance test. LLM calls always use
`MockProvider` in CI; a separate manual workflow can run the live-LLM smoke test.

### 12.4 Critical acceptance test (automated, Playwright + backend verification)

1. Upload fixture PDF → 2. Generate Smart Notes (MockProvider fixture with known
paragraphs) → 3. open editor → 4. delete paragraph P2 entirely → 5. Enter twice →
6. type new paragraph N1 → 7. add heading H-new → 8. modify sentences S1, S2 →
9. Undo (assert S2 reverted in DOM) → 10. Redo (assert S2 re-applied) → 11. Save (wait
for "✓ Saved", assert GET /content equals editor WDM) → 12. Preview (assert page images
returned, render revision == saved revision) → 13. Generate final PDF → 14. verify on
the PDF with PyMuPDF: P2 text absent; N1 present; two blank-line gaps at the Enter×2
location (y-gap ≥ 2 × line height); S1/S2 modified text present; H-new present and
rendered at heading size; zero underline strokes; PDF metadata `content_hash` ==
head hash. **The editor is declared complete only when this test passes in CI.**

---

## 13. Major technical risks

| Risk | Impact | Mitigation |
|---|---|---|
| Preview/final or editor/PDF drift (stale content) | Core promise broken | Revision-pinned rendering, flush-before-render, hash in cache keys and PDF metadata, acceptance test |
| Lossy TipTap ⇄ WDM conversion | Edits silently lost | Closed schema identical to WDM, pure converters, property-based round-trip tests |
| `contenteditable` quirks (IME, mobile, paste) | Buggy editing | Mature ProseMirror core; Playwright tests in real browser; paste sanitizer |
| LLM malformed/hallucinated output | Broken editor, wrong notes | Schema-constrained output, Pydantic validation, repair once, deterministic fallback; RAG citation validation; Preserve mode needs no LLM |
| Prompt injection inside uploaded docs | Model follows document instructions | Documents are delimited data; no tool side effects; output schema-only; server derives pages; see §14 |
| Small / noisy classifier dataset | Weak, over-claimed metrics | Weak+gold strategy, document-level splits, frozen gold test set, report only measured numbers, confidence fallback |
| OCR quality on poor scans | Garbage in | Preprocessing, confidence flagging, user can edit everything anyway |
| Handwriting realism vs legibility | Looks fake or unreadable | Bounded jitter, style presets, readability checks |
| Layout edge cases (very long words, huge lists, formulas) | Overflow/clipping | Force-break, nesting limits, property tests, quality checker blocks bad renders |
| Font licensing | Legal | Only OFL/Apache fonts, licences shipped in repo |
| LLM cost/latency on long docs | Slow, expensive | Map-reduce, cheaper model for simple tasks, caching generations by (doc hash, mode, prompt version) |
| Concurrent edits in two tabs | Overwrites | Optimistic concurrency (`base_revision`, 409) |
| Misuse: passing off generated "handwritten" work as one's own | Academic dishonesty | Ethics section, optional visible "Generated with WriteAI" footer (off by default since v2.0.1, user choice), documented intended use (personal study notes) |

---

## 14. Security considerations

- **Upload validation:** extension allow-list (`.pdf .docx .txt`) **and** magic-byte
  sniffing (`%PDF-`; DOCX = ZIP containing `[Content_Types].xml` + `word/document.xml`;
  TXT must decode as text). Size limit (default 20 MB), page limit (default 300), DOCX
  zip-bomb guard (total uncompressed size and entry count caps), encrypted PDFs rejected.
- **Safe storage:** files saved under a random UUID name in a private directory outside
  any static route; original filename kept only as display metadata (sanitised);
  `tempfile` with restrictive permissions for OCR/raster work, cleaned in `finally`;
  scheduled purge of soft-deleted docs and orphaned temp/render files.
- **Parsing isolation:** extraction/OCR run with timeouts and in a worker process so a
  malicious/huge file can't hang the API; PyMuPDF/Tesseract versions pinned.
- **Secrets:** `ANTHROPIC_API_KEY` etc. only in backend env (pydantic-settings);
  `.env` gitignored, `.env.example` has placeholders; keys never logged, never returned
  by any endpoint, never in the frontend bundle (the browser only talks to our API).
- **Input validation:** Pydantic on every request; WDM size caps (blocks, text length,
  nesting depth); question length caps; enums for all settings; numeric ranges for margins
  and spacing.
- **Prompt-injection awareness:** document text passed inside explicit delimiters with a
  system instruction that it is untrusted data; the LLM has no side-effecting tools; all
  output validated against strict schemas; RAG answers must cite retrieved chunks; page
  numbers and document ids are resolved server-side; generation never alters settings or
  other documents. Suspicious instruction-like spans are flagged in the Analysis page.
- **Output safety:** LLM text is inserted as ProseMirror text nodes (never `innerHTML`),
  so no XSS through AI output or pasted content; strict CSP on the frontend.
- **Transport & API:** CORS restricted to the frontend origin; rate limiting on
  upload/generate/ask (slowapi); request body size limit; generic error messages (no stack
  traces) in production.
- **Data handling & privacy:** delete removes file, rows, vectors and renders; README
  states that document text is sent to the configured LLM provider for AI modes and that
  Preserve mode works fully offline.
- **Dependencies:** pinned versions, `pip-audit` / `npm audit` in CI, Dependabot.
- **Auth:** v1 is single-user/local; an optional static API token (`WRITEAI_API_TOKEN`)
  guards deployed demos. Multi-user auth (`owner_id` already in schema) is future work.

---

*Next step: on approval, start **Phase 1 — architecture and project setup**.*
