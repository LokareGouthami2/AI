# Datasets

* `splits/` — document ids per split (written by `python -m backend.ml.train`).
  Splits are **by subject**: train (8 subjects), val (chemistry, geography),
  test (mathematics, literature).
* `generated/` (git-ignored) — cached segment JSONL produced by the generator.
  Reproduce with `python -m backend.ml.train --docs 40 --regenerate`.
* `annotations/guidelines.md` — label definitions used for the gold set.
* Gold documents live in code: `backend/ml/gold.py` (3 hand-written documents,
  rendered to PDF + TXT → 140 labelled segments).

## Sources & licences

All generator vocabularies, sentence frames and gold documents were written
for this project. The bibliographic references in `backend/ml/corpus.py` cite
real books and papers by author, title, publisher and year only; no text is
taken from them. No third-party document text is redistributed.
