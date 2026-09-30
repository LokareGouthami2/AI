# ML pipeline — section classifier

**Task:** label every text segment (a merged line/block) of a document as one of
13 classes: `TITLE, HEADING, SUBHEADING, PARAGRAPH, DEFINITION, EXAMPLE,
PROCEDURE, IMPORTANT_POINT, FORMULA, QUESTION, ANSWER, CONCLUSION, REFERENCE`.

The labels drive the section tree (headings open sections), the Preserve mode,
the LLM's structured input, the offline notes engine and RAG chunk boundaries.

## Features (`backend/ml/features.py`)

| Group | Features |
|---|---|
| Lexical | TF-IDF word 1–2-grams; TF-IDF char_wb 2–5-grams (catch `=`, `Σ`, `Q1.`, `[2]`) |
| Typography | font size ÷ document median, bold, italic, largest-font flag |
| Surface | token count (log), line count, caps/title-case ratio, digit ratio, math-symbol ratio, ends with `:`/`?`/`.`, starts with bullet/number/sub-number/`Q1`/`Answer:` |
| Cue patterns | definition cues ("is defined as", "refers to"), example cues, procedure cues ("Step 1", "First,"), important-point cues ("Note:", "Remember"), conclusion cues, reference pattern (year, `[n]`, "et al.") |
| Position/context | relative position, is-first, vertical page position, indent, gap before/after ÷ font size, previous/next segment's font ratio & bold, previous ends with `?` |

All of it is one scikit-learn `Pipeline` (`FeatureUnion` + classifier), so the
artefact is a single `joblib` file with no hidden preprocessing.

## Dataset

The build environment could not reach public corpora (Hugging Face, Wikipedia,
OpenStax), so the training data is **generated, then extracted with the
production pipeline**:

1. `ml/corpus.py` holds hand-written vocabularies for 12 subjects (terms with
   definitions, processes, formulas, real bibliographic references) and
   sentence frames for every class.
2. `ml/dataset.py` composes complete documents (title, sections, subsections,
   paragraphs, definitions, examples, procedures, formulas, questions,
   answers, conclusion, references) and renders each in a **random
   typographic style**: 4 font families, body 10–12 pt, heading size/bold
   variations, 3 numbering schemes, APA/IEEE references, A4/Letter. The mix is
   70 % PDF, 15 % DOCX, 15 % TXT.
3. Each rendered file goes through the **real** `extract()` → `preprocess()`
   pipeline. Segments are aligned back to their source blocks, which gives
   labels by construction (0.4 % of blocks are lost in alignment).

**Splits are by subject** so that no vocabulary leaks between splits:

| Split | Subjects | Documents | Segments |
|---|---|---|---|
| train | biology, physics, history, economics, computer science, psychology, business, environmental science | 320 | 14,042 |
| val | chemistry, geography | 80 | 3,573 |
| test | mathematics, literature | 80 | 3,442 |
| **gold** | 3 **hand-written** documents (ML chapter, photosynthesis notes, French Revolution notes), each as PDF + TXT | 6 | 140 |

The gold set was written independently of the generator's templates. It is
never used for training or model selection.

## Models compared (`python -m backend.ml.train`)

Selection is by **validation macro-F1**. Test and gold numbers are reported
for transparency only.

| Model | Val macro-F1 | Test macro-F1 | Gold macro-F1 | Train time |
|---|---|---|---|---|
| **TF-IDF + layout → Logistic Regression** (selected) | **0.9932** | 0.9969 | **0.9332** | 13.4 s |
| TF-IDF + layout → LinearSVC (calibrated) | 0.9930 | 0.9962 | 0.8970 | 18.1 s |
| Dense text embedding (LSA-256*) + layout → LR | 0.9917 | 0.9970 | 0.9332 | 12.6 s |

\* MiniLM sentence embeddings are used automatically when the model is cached
locally. It wasn't available in this environment, so the dense variant used
LSA (TF-IDF → TruncatedSVD).

All numbers are copied from `ml_models/metrics.json`, which the training script
writes. A unit test recomputes accuracy from the stored confusion matrices.

## Results of the selected model

| Set | n | Accuracy | Macro P | Macro R | Macro F1 |
|---|---|---|---|---|---|
| Synthetic test (held-out subjects) | 3,442 | 0.9948 | 0.9969 | 0.9968 | 0.9969 |
| **Hand-written gold** | 140 | **0.9286** | 0.9675 | 0.9181 | **0.9332** |

Gold per-class F1: TITLE 1.00 · HEADING 0.93 · SUBHEADING 0.83 · PARAGRAPH 0.91 ·
DEFINITION 0.67 · EXAMPLE 1.00 · PROCEDURE 1.00 · IMPORTANT_POINT 1.00 ·
FORMULA 1.00 · QUESTION 1.00 · ANSWER 1.00 · CONCLUSION 0.80 · REFERENCE 1.00.

Confusion matrices: `ml_models/confusion_test.png`, `ml_models/confusion_gold.png`.

### Honest reading of these numbers

* **The synthetic test score (0.997) is optimistic.** Held-out subjects share
  the generator's sentence frames with training. It shows the model learned
  the structure, not that it generalises to arbitrary documents.
* **The gold score (0.933 on 140 segments) is the better estimate**, but the
  set is small: one error moves macro-F1 by about 1–3 points.
* The remaining gold errors are explainable:
  - HEADING ↔ SUBHEADING for *unnumbered* headings in plain-text files, where
    no typography exists.
  - "To sum up, …" conclusions, which the frames never used.
  - "Term: definition" lines with no cue word.
  These were **not** fixed by tuning on the gold set, since that would turn
  it into a training set.

## Runtime (`ml/predict.py`)

* Predictions below 0.45 probability fall back to transparent layout rules
  (`rule_label`) and are shown as "rule" in the Analysis tab.
* If the artefact is missing, the whole document is labelled by rules. The
  app keeps working, just with lower quality.

## Reproduce

```bash
python -m backend.ml.train --docs 40 --regenerate   # ~70 s on 4 CPUs
python -m pytest backend/tests/test_ml.py
```
