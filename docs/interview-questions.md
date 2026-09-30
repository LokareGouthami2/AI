# Interview questions (with answers grounded in this codebase)

## System design

**Q: Why isn't this just "LLM + handwriting font"?**
The LLM is one stage out of seven. Around it:
- extraction and OCR produce typography features;
- NLP cleans and segments;
- a trained classifier builds structure;
- a closed-schema editor gives the user control;
- a deterministic layout engine paginates;
- a quality checker proves the PDF matches the edited text.
The LLM's output is schema-validated, converted by our code, and replaced by a
deterministic engine if it fails.

**Q: How do you guarantee the PDF reflects the latest edits?**
Rendering is pinned to a revision:
- the client flushes autosave and sends `expected_revision`;
- the server returns 409 if the head has moved;
- the PDF metadata carries the content hash;
- preview caches are keyed by that hash;
- the post-render audit reads the text back out of the PDF and compares it
  token by token.
The browser acceptance test checks all of this end to end.

**Q: Why TipTap/ProseMirror instead of a textarea or Slate?**
The schema is enforced, so the editor literally can't create a node the
renderer can't draw. You also get transactional undo/redo and robust
clipboard and IME handling. I restricted StarterKit to exactly the WriteAI
Document Model and proved the equivalence with property tests against a real
editor instance.

**Q: What's the WriteAI Document Model and why have one?**
It's a small, versioned JSON schema (blocks + inline runs + marks) shared by
Pydantic (backend) and pure JS converters (frontend). It decouples the editor
library from storage and rendering, can be validated server-side, and has a
canonical form for hashing.

## ML

**Q: Why logistic regression and not a transformer?**
- 13 classes on short segments, where layout features carry much of the
  signal.
- It's interpretable, CPU-fast and small (a 1.5 MB artefact).
- A dense-embedding variant was compared and didn't beat it on validation.

**Q: How did you get training data?**
Public corpora were unreachable in the build environment. I wrote subject
vocabularies and sentence frames, generated documents with randomised
typography, and — importantly — pushed them through the *production*
extraction pipeline, so the features match inference.

**Q: Isn't 0.997 F1 suspicious?**
Yes, and the docs say so. Held-out subjects still share the generator's
frames. The meaningful number is **0.933 macro-F1 on a hand-written gold
set** that never influenced training or model selection. I didn't tune on
its errors, which would have leaked it.

**Q: How do you avoid leakage?**
- Splits are by subject (grouped), not by segment.
- Model selection uses validation only.
- The gold set is separate and frozen.
- Metrics are written by the script, and a test recomputes accuracy from the
  stored confusion matrix.

## LLM & RAG

**Q: How do you stop the LLM breaking the editor?**
- Structured outputs against Pydantic schemas;
- semantic validation (4 distinct options, a valid answer index, pages
  within range);
- one repair attempt, then the offline fallback;
- plain-string schemas plus a sanitising converter, so no marks and no HTML.

**Q: What's your prompt-injection strategy?**
- Delimit the document and declare it untrusted data;
- give the model no tools;
- constrain output to a schema;
- resolve citations and pages server-side;
- flag suspicious spans in the UI.

**Q: Why hybrid retrieval with RRF?**
BM25 nails exact terms (formula names, jargon); embeddings handle paraphrase.
RRF fuses the two rankings without calibrating different score scales.

**Q: How do you prevent hallucinated answers?**
- A relevance gate before generation;
- "answer only from these chunks or return null";
- citation ids validated against the retrieved set, with ungrounded answers
  dropped;
- pages taken from chunk rows, never from model text.
Measured: 5/5 unanswerable questions refused, 0 answerable questions refused.

## Rendering

**Q: How is the handwriting deterministic yet varied?**
The RNG is seeded from `(seed, style, block id, text)`. The same input gives
byte-identical PDFs (tested), and editing one paragraph leaves the others
unchanged (tested).

**Q: How do you make sure lines don't collide?**
Variation is clipped at 2σ, and the worst-case displacement is added to each
line's ink extent. After placing a line, its glyph ink boxes are compared with
those of the line above; on a collision the line moves down a slot or to the
next page. Hypothesis ran 1,500 random documents with zero overlaps.

**Q: Tell me about a bug your tests caught.**
Ctrl+Shift+Z performed an **undo** when there was nothing to redo.
ProseMirror retries unhandled Shift shortcuts without Shift, and redo returns
false when history is empty. A Playwright test caught it; the fix binds the
redo shortcuts to always consume the key.

## Trade-offs & next steps

- Alembic migrations;
- a real job queue;
- MiniLM or a cross-encoder reranker when network access allows;
- a live-LLM evaluation set;
- more real scanned documents for OCR;
- multi-user auth (`owner_id` already exists in the schema);
- Firefox/WebKit e2e runs.
