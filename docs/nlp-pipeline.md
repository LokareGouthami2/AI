# NLP pipeline

`backend/documents/extract.py` → `backend/nlp/preprocess.py` → `backend/nlp/stats.py` → `backend/nlp/structure.py`

## 1. Extraction (typography-preserving)

* **PDF (PyMuPDF):** spans → lines with bbox, dominant font, size, bold/italic
  (from font flags *and* font names such as "-Bold"). Lines are sorted in
  reading order.
* **Scanned pages:** a page with fewer than 20 extractable characters is
  rendered at 300 DPI. The OpenCV preprocessing is grayscale → deskew
  (min-area-rectangle angle, normalised so it doesn't depend on the OpenCV
  version) → median blur → adaptive threshold. The page then goes to
  Tesseract (`--psm 3`), which returns word boxes and confidences. Line height
  gives an estimated font size, so OCR'd lines still get typography features.
* **DOCX (python-docx):** each paragraph is a line; style names (`Heading 1`,
  `Title`) give nominal sizes; tables are flattened row by row.
* **TXT:** encoding detection (charset-normalizer); blank lines are kept
  because they separate paragraphs.

## 2. Preprocessing

| Step | What it does | Why |
|---|---|---|
| `normalise_text` | NFC (not NFKC), ligatures (ﬁ→fi), smart quotes, control chars, whitespace | NFKC would turn `x²` into `x2` and damage formulas |
| `remove_headers_footers` | Drops lines in the top/bottom 8 % band that repeat on ≥ 50 % of pages (digits masked), plus bare page numbers | Running headers pollute notes and retrieval |
| `merge_lines` | Joins wrapped lines into blocks; breaks on font change, bold change, list/question/answer/step/citation starts, and **gaps larger than the document's own leading + 0.3 em** | Adaptive threshold: paragraph spacing differs per document |
| `dehyphenate` | `classi-` + `fication` → `classification` when the next line starts lowercase | Repairs line-end hyphenation |

A generator-based test found that consecutive paragraphs separated only by
paragraph spacing were being merged. The adaptive-gap rule fixed it (block
loss in alignment went from about 5 % to 0.4 %).

## 3. Statistics (`stats.py`)

* Sentence segmentation: spaCy `en_core_web_sm` (parser-based), with a regex
  fallback if the model is missing.
* Words, sentences, reading time, language (stop-word ratio heuristic).
* Readability: Flesch Reading Ease and Flesch–Kincaid grade, computed with the
  standard formulas and a local syllable heuristic. `textstat` was removed
  because it downloads data at runtime.
* Keyphrases: YAKE, de-duplicated (drops phrases with repeated tokens or
  substring overlap).
* **Prompt-injection flags:** regexes for "ignore previous instructions",
  "system prompt" and similar. They're only *shown* to the user; document text
  is always treated as data.

## 4. Section tree (`structure.py`)

Labelled segments → a tree: TITLE, then HEADING sections, then SUBHEADING
sections, each holding items `(label, text, page)`. The tree is used by:

* Preserve mode (`editor/from_llm.tree_to_wdm`)
* the LLM prompt (`to_outline_text()`, with `[LABEL p.N]` tags for grounding)
* RAG chunking (chunks never cross a section)
* the offline notes/flashcard/quiz engine
