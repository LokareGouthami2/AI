# Evaluation & testing

Every number here was produced by a script in this repository, and each has a
reproduce command. Nothing is hand-typed.

## Test suites

| Suite | Command | Count | Status |
|---|---|---|---|
| Backend unit + API + property + acceptance | `pytest` | 122 tests | ✅ pass |
| Frontend unit (converters, real TipTap editor, autosave) | `cd frontend && npm test` | 34 tests | ✅ pass |
| Browser end-to-end (Chromium) | `cd frontend && npx playwright test` | 13 tests | ✅ pass |
| Lint | `ruff check backend` · `npm run lint` | — | ✅ clean |

### Critical acceptance test (requirement §30)

Implemented twice:

* **`frontend/e2e/acceptance.spec.js` — real browser, real backend.**
  1. Upload the fixture PDF.
  2. Generate Smart Notes.
  3. Open the editor.
  4. Delete a whole paragraph (triple-click, Backspace ×2).
  5. Ctrl+End, then Enter twice.
  6. Type a new paragraph.
  7. Add an H2 heading with the toolbar.
  8. Replace a word and extend a sentence.
  9. Ctrl+Z (verify the edit is gone).
  10. Ctrl+Y (verify it's back).
  11. Save (wait for "✓ Saved").
  12. Update Preview (pinned to the saved revision).
  13. Generate Final PDF, then download it.
  14. Inspect the PDF with `backend/quality/pdf_inspect.py`. Checks: deleted
      paragraph absent; new paragraph present; heading present *and* larger
      than body text; modified and redone text present; blank line preserved
      (vertical gap ≥ 2 grid lines); **0 underline strokes**; PDF metadata
      `content_hash` equals the editor's saved hash; quality report passed.
* **`backend/tests/test_acceptance.py` — the same checks at API level**,
  plus proof that an *intermediate* saved state (the "undone" text) never
  reaches the PDF.

**Result: passes.** Getting there found three real bugs, all fixed with
regression tests:

1. Ctrl+Shift+Z with nothing to redo performed an **undo**.
2. Backspace after a list hid an empty line inside the list.
3. The quality checker expected a blank line for an empty list item, which
   renders as a bullet.

The checker blocked the PDF for bug 3, which shows the quality gate working
as intended.

### Property-based layout testing

Random documents × 6 styles × sizes × spacings. Invariants: no overflow, no
ink overlap, no orphan headings, token sequence identical to the document. A
**1,500-example run passes**; the regular suite runs 40 examples per test.

## ML classifier

See [ml-pipeline.md](ml-pipeline.md). Selected model: TF-IDF + layout →
Logistic Regression.

| Set | n | Accuracy | Macro F1 |
|---|---|---|---|
| Synthetic, held-out subjects | 3,442 | 0.9948 | 0.9969 |
| **Hand-written gold** | 140 | **0.9286** | **0.9332** |

Reproduce: `python -m backend.ml.train --docs 40 --regenerate`

## RAG

See [rag.md](rag.md). 24 questions over 3 gold documents; hashing embedder;
offline extractive answerer.

| Recall@1 | Recall@5 | MRR | Answer contains evidence | Unanswerable refused |
|---|---|---|---|---|
| 0.895 | 1.000 | 0.947 | 0.947 | 5 / 5 |

Reproduce: `python -m backend.rag.evaluate`

Sentence splitting uses spaCy's `senter` component (switched from the
dependency parser to save ~80 MB of memory). Retrieval scores were
unchanged; "answer contains evidence" rose from 0.737 to 0.947 because the
chunker's sentence boundaries improved.

## Handwriting quality gate

Every final render must pass `check_layout` (before rendering) **and**
`audit_pdf` (after rendering, reading the PDF back), otherwise no PDF is
produced. The audit found and fixed:

* a lost glyph from overlapping identical letters (spacing floor raised);
* merged words in the text layer (real space characters added);
* bold leaking into the next line (per-line graphics state).

All 18 combinations of 6 styles × 3 papers pass both checks
(`test_all_styles_pass_quality_and_pdf_audit`).

## Deployment smoke test

Both Docker images were built and run together (API behind nginx). Upload,
extract, analyze, generate (Exam mode), final render (quality and PDF audit
passed), download and Ask all worked through the proxy. See
[deployment.md](deployment.md).

## Not measured / limitations

* **No live LLM evaluation:** there was no API key in the build environment.
  The Claude path is unit-tested with scripted responses only.
* The gold set is small (140 segments), so treat its F1 as ±~3 points.
* OCR accuracy was checked on a rasterised fixture (mean Tesseract confidence
  ≈ 95), not on real phone-camera scans.
* The browser suite runs in Chromium only.
