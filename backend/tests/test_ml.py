import json

import pytest

from backend.config import REPO_ROOT
from backend.documents.extract import extract
from backend.ml.dataset import Generator, align, build_samples
from backend.ml.features import LAYOUT_FEATURE_NAMES, LayoutFeaturizer, segment_samples
from backend.ml.labels import LABELS
from backend.ml.predict import SectionClassifier, get_classifier, rule_label
from backend.nlp.preprocess import preprocess
from backend.tests.fixtures.sample_content import ML_CHAPTER


def test_model_artifact_loads():
    clf = get_classifier()
    assert clf.loaded, "run `python -m backend.ml.train` to create ml_models/section_classifier.joblib"
    assert set(clf.artefact["labels"]) == set(LABELS)


def test_classifies_fixture_pdf(pdf_bytes):
    segs = preprocess(extract("pdf", pdf_bytes))
    preds = get_classifier().classify(segs)
    assert len(preds) == len(segs)
    assert all(p.label in LABELS for p in preds)
    by_text = {s.text: p.label for s, p in zip(segs, preds)}
    assert by_text["Introduction to Machine Learning"] == "TITLE"
    assert by_text["2. Types of Machine Learning"] == "HEADING"
    assert by_text["2.1 Supervised Learning"] == "SUBHEADING"
    assert by_text["Q2. Why do we need a separate test set?"] == "QUESTION"
    # Overall agreement with the fixture's known labels (aligned by text).
    from backend.ml.dataset import DocSpec, Style

    spec = DocSpec("fx", "ml", Style("sans", 11, 22, 16, 13, True, True, "arabic", True, "apa", "pdf"), ML_CHAPTER)
    pred_by_seg = {id(s): p.label for s, p in zip(segs, preds)}
    aligned = align(spec, segs)
    assert len(aligned) >= len(ML_CHAPTER) - 2
    correct = sum(1 for seg, gold in aligned if pred_by_seg[id(seg)] == gold)
    assert correct / len(aligned) >= 0.85


def test_rules_only_fallback(pdf_bytes):
    segs = preprocess(extract("pdf", pdf_bytes))
    preds = SectionClassifier(None).classify(segs)
    assert preds[0].label == "TITLE" and all(p.source == "rule" for p in preds)


def test_features_shape(pdf_bytes):
    segs = preprocess(extract("pdf", pdf_bytes))
    samples = segment_samples(segs)
    X = LayoutFeaturizer().transform(samples)
    assert X.shape == (len(segs), len(LAYOUT_FEATURE_NAMES))
    assert samples[0]["layout"]["is_first"] == 1.0


def test_rule_label_basics():
    s = {"text": "What is entropy?", "layout": {k: 0.0 for k in LAYOUT_FEATURE_NAMES}}
    s["layout"].update(ends_question=1.0, n_tokens_log=1.6)
    assert rule_label(s) == "QUESTION"


def test_generator_is_deterministic_and_aligns():
    a = Generator(5).document("d1", "physics", "pdf")
    b = Generator(5).document("d1", "physics", "pdf")
    assert a.blocks == b.blocks
    samples = build_samples(a)
    assert len(samples) >= len(a.blocks) - 3  # alignment loses at most a couple of blocks
    assert {s["label"] for s in samples} <= set(LABELS)


def test_align_matches_sequentially():
    from backend.ml.dataset import DocSpec, Style
    from backend.nlp.preprocess import Segment

    spec = DocSpec("x", "physics", Style("sans", 11, 22, 16, 13, True, True, "none", True, "apa", "txt"), [("HEADING", "Intro"), ("PARAGRAPH", "Some text here that is long enough.")])
    segs = [Segment("Intro", 1, (0, 0, 1, 1), 11, False, False, 1, 0, 0, 0, "txt"), Segment("Some text here that is long enough.", 1, (0, 0, 1, 1), 11, False, False, 1, 0, 0, 0, "txt")]
    assert [lbl for _, lbl in align(spec, segs)] == ["HEADING", "PARAGRAPH"]


def test_reported_metrics_exist_and_are_measured():
    m = json.loads((REPO_ROOT / "ml_models" / "metrics.json").read_text())
    assert m["selected_model"] in m["comparison"]
    for split in ("test", "gold"):
        cm = m[split]["confusion_matrix"]["matrix"]
        n = sum(sum(r) for r in cm)
        assert n == m[split]["n"]
        acc = sum(cm[i][i] for i in range(len(cm))) / n
        assert acc == pytest.approx(m[split]["accuracy"], abs=1e-4)


def test_small_training_run(tmp_path):
    """End-to-end training smoke test on a tiny generated dataset."""
    from backend.ml.train import build_models, evaluate

    gen = Generator(1)
    samples = []
    for subj in ("physics", "history"):
        for i in range(3):
            samples.extend(build_samples(gen.document(f"{subj}-{i}", subj, "pdf")))
    model = build_models()["tfidf_logreg"]
    model.fit(samples, [s["label"] for s in samples])
    res = evaluate(model, samples, [s["label"] for s in samples])
    assert res["accuracy"] > 0.9  # training accuracy on tiny set
