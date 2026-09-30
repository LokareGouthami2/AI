"""Train, compare and evaluate section classifiers.

    python -m backend.ml.train                # generate data, train, evaluate, save
    python -m backend.ml.train --docs 20      # smaller/faster run

Models compared (selected by macro-F1 on the VALIDATION subjects):
  A. tfidf_logreg   : word+char TF-IDF + layout features → LogisticRegression
  B. tfidf_svm      : same features → LinearSVC (calibrated for probabilities)
  C. dense_logreg   : dense text embedding + layout features → LogisticRegression
                      (sentence-transformers MiniLM when available locally,
                       otherwise LSA = TF-IDF → TruncatedSVD(256))

The selected model is then evaluated ONCE on the held-out TEST subjects and on
the hand-written GOLD set. All numbers written to metrics.json are measured.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from backend.config import REPO_ROOT
from backend.ml import dataset
from backend.ml.features import LayoutFeaturizer, TextSelector
from backend.ml.gold import gold_samples
from backend.ml.labels import LABELS

log = logging.getLogger("train")
MODEL_DIR = REPO_ROOT / "ml_models"
DATA_DIR = REPO_ROOT / "datasets"


def _text_features() -> FeatureUnion:
    return FeatureUnion(
        [
            ("word", Pipeline([("sel", TextSelector()), ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, lowercase=True))])),
            ("char", Pipeline([("sel", TextSelector()), ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, max_features=40000, sublinear_tf=True))])),
            ("layout", Pipeline([("feat", LayoutFeaturizer()), ("scale", StandardScaler())])),
        ]
    )


class DenseTextEmbedder:
    """Sentence-transformers if the model is cached locally, else LSA."""

    def __init__(self, backend: str = "auto", model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.backend = backend
        self.model_name = model_name
        self.kind_: str | None = None

    def get_params(self, deep=True):
        return {"backend": self.backend, "model_name": self.model_name}

    def set_params(self, **p):
        for k, v in p.items():
            setattr(self, k, v)
        return self

    def fit(self, X, y=None):
        texts = [x["text"] for x in X]
        if self.backend in ("auto", "sentence-transformers"):
            try:
                from sentence_transformers import SentenceTransformer

                self._st = SentenceTransformer(self.model_name, local_files_only=True)
                self.kind_ = "minilm"
                return self
            except Exception as exc:
                if self.backend == "sentence-transformers":
                    raise
                log.warning("sentence-transformers model not available (%s); using LSA", type(exc).__name__)
        self._tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        m = self._tfidf.fit_transform(texts)
        self._svd = TruncatedSVD(n_components=min(256, m.shape[1] - 1), random_state=0).fit(m)
        self.kind_ = "lsa"
        return self

    def transform(self, X):
        texts = [x["text"] for x in X]
        if self.kind_ == "minilm":
            return self._st.encode(texts, batch_size=64, normalize_embeddings=True)
        z = self._svd.transform(self._tfidf.transform(texts))
        norms = np.linalg.norm(z, axis=1, keepdims=True)
        return z / np.maximum(norms, 1e-9)

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_st", None)  # never pickle the transformer weights
        return state


def build_models() -> dict[str, Pipeline]:
    return {
        "tfidf_logreg": Pipeline(
            [("features", _text_features()), ("clf", LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced"))]
        ),
        "tfidf_svm": Pipeline(
            [("features", _text_features()), ("clf", CalibratedClassifierCV(LinearSVC(C=0.5, class_weight="balanced"), cv=3))]
        ),
        "dense_logreg": Pipeline(
            [
                (
                    "features",
                    FeatureUnion(
                        [
                            ("dense", DenseTextEmbedder()),
                            ("layout", Pipeline([("feat", LayoutFeaturizer()), ("scale", StandardScaler())])),
                        ]
                    ),
                ),
                ("clf", LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced")),
            ]
        ),
    }


def evaluate(model, X, y) -> dict:
    pred = model.predict(X)
    p, r, f, _ = precision_recall_fscore_support(y, pred, labels=LABELS, average="macro", zero_division=0)
    pw, rw, fw, _ = precision_recall_fscore_support(y, pred, labels=LABELS, average="weighted", zero_division=0)
    return {
        "n": len(y),
        "accuracy": round(accuracy_score(y, pred), 4),
        "macro": {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)},
        "weighted": {"precision": round(pw, 4), "recall": round(rw, 4), "f1": round(fw, 4)},
        "per_class": {
            k: {m: round(v, 4) if isinstance(v, float) else v for m, v in d.items()}
            for k, d in classification_report(y, pred, labels=LABELS, output_dict=True, zero_division=0).items()
            if k in LABELS
        },
        "confusion_matrix": {"labels": LABELS, "matrix": confusion_matrix(y, pred, labels=LABELS).tolist()},
    }


def plot_confusion(cm: dict, title: str, path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        return
    m = np.array(cm["matrix"], dtype=float)
    norm = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(LABELS)), LABELS, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(range(len(LABELS)), LABELS, fontsize=8)
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            if m[i, j]:
                ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=7, color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=40, help="documents generated per subject")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--out", type=Path, default=MODEL_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    data_path = DATA_DIR / "generated" / f"segments_d{args.docs}_s{args.seed}.jsonl"
    t0 = time.time()
    if data_path.exists() and not args.regenerate:
        samples = dataset.load_jsonl(data_path)
    else:
        log.info("generating dataset (%s docs/subject)…", args.docs)
        samples = dataset.generate(args.docs, args.seed)
        dataset.save_jsonl(samples, data_path)
    log.info("dataset: %s segments in %.1fs", len(samples), time.time() - t0)

    splits = {k: [s for s in samples if dataset.split_of(s) == k] for k in ("train", "val", "test")}
    gold = gold_samples()
    for k, v in splits.items():
        log.info("  %-5s %5d segments, %3d docs", k, len(v), len({s['doc_id'] for s in v}))
    log.info("  gold  %5d segments (hand-written)", len(gold))

    Xtr, ytr = splits["train"], [s["label"] for s in splits["train"]]
    comparison = {}
    fitted = {}
    for name, model in build_models().items():
        t = time.time()
        model.fit(Xtr, ytr)
        fitted[name] = model
        comparison[name] = {
            "val": evaluate(model, splits["val"], [s["label"] for s in splits["val"]]),
            "train_seconds": round(time.time() - t, 1),
        }
        if name == "dense_logreg":
            comparison[name]["embedding"] = model.named_steps["features"].transformer_list[0][1].kind_
        log.info("%-13s val macro-F1=%.4f acc=%.4f (%.1fs)", name, comparison[name]["val"]["macro"]["f1"], comparison[name]["val"]["accuracy"], comparison[name]["train_seconds"])

    best = max(comparison, key=lambda n: comparison[n]["val"]["macro"]["f1"])
    log.info("selected: %s", best)
    model = fitted[best]
    test_metrics = evaluate(model, splits["test"], [s["label"] for s in splits["test"]])
    gold_metrics = evaluate(model, gold, [s["label"] for s in gold])
    # Also report every model on test/gold for transparency (selection used val only).
    for name, m in fitted.items():
        comparison[name]["test_macro_f1"] = evaluate(m, splits["test"], [s["label"] for s in splits["test"]])["macro"]["f1"]
        comparison[name]["gold_macro_f1"] = evaluate(m, gold, [s["label"] for s in gold])["macro"]["f1"]

    args.out.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    artefact = {"model": model, "name": best, "version": f"{best}-{version}", "labels": LABELS}
    joblib.dump(artefact, args.out / "section_classifier.joblib", compress=3)
    metrics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected_model": best,
        "model_version": artefact["version"],
        "dataset": {
            "docs_per_subject": args.docs,
            "seed": args.seed,
            "splits": {k: {"segments": len(v), "documents": len({s['doc_id'] for s in v}), "subjects": dataset.SPLITS[k]} for k, v in splits.items()},
            "gold_segments": len(gold),
            "label_counts_train": {lbl: sum(1 for s in splits["train"] if s["label"] == lbl) for lbl in LABELS},
        },
        "comparison": comparison,
        "test": test_metrics,
        "gold": gold_metrics,
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    plot_confusion(test_metrics["confusion_matrix"], f"{best} — held-out test subjects", args.out / "confusion_test.png")
    plot_confusion(gold_metrics["confusion_matrix"], f"{best} — hand-written gold set", args.out / "confusion_gold.png")
    for split in ("train", "val", "test"):
        (DATA_DIR / "splits" / f"{split}_docs.txt").write_text("\n".join(sorted({s["doc_id"] for s in splits[split]})) + "\n")
    log.info("TEST  macro-F1=%.4f acc=%.4f", test_metrics["macro"]["f1"], test_metrics["accuracy"])
    log.info("GOLD  macro-F1=%.4f acc=%.4f", gold_metrics["macro"]["f1"], gold_metrics["accuracy"])
    return metrics


if __name__ == "__main__":
    main()
