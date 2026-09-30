"""Runtime section classification with a deterministic low-confidence fallback."""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

import joblib

from backend.config import get_settings
from backend.ml.features import segment_samples
from backend.nlp.preprocess import Segment

log = logging.getLogger(__name__)


@dataclass
class Prediction:
    label: str
    confidence: float
    source: str  # "model" | "rule"


class SectionClassifier:
    def __init__(self, artefact: dict | None):
        self.artefact = artefact
        self.version = artefact["version"] if artefact else "rules-only"

    @property
    def loaded(self) -> bool:
        return self.artefact is not None

    def classify(self, segments: list[Segment]) -> list[Prediction]:
        samples = segment_samples(segments)
        if not samples:
            return []
        if not self.loaded:
            return [Prediction(rule_label(s), 0.0, "rule") for s in samples]
        model = self.artefact["model"]
        probs = model.predict_proba(samples)
        classes = list(model.classes_)
        min_conf = get_settings().classifier_min_confidence
        out = []
        for s, p in zip(samples, probs):
            i = int(p.argmax())
            if p[i] < min_conf:
                out.append(Prediction(rule_label(s), float(p[i]), "rule"))
            else:
                out.append(Prediction(classes[i], float(p[i]), "model"))
        return out


def rule_label(sample: dict) -> str:
    """Transparent layout rules used when the model is unsure or missing."""
    f = sample["layout"]
    text = sample["text"]
    if f["is_first"] and f["font_ratio"] >= 1.3:
        return "TITLE"
    if f["n_tokens_log"] < 2.5 and not f["ends_period"]:
        if f["starts_subnumber"] or (f["font_ratio"] > 1.05 and f["font_ratio"] < 1.3):
            return "SUBHEADING"
        if f["font_ratio"] >= 1.3 or f["is_bold"]:
            return "HEADING"
    if f["ends_question"] or f["starts_qprefix"]:
        return "QUESTION"
    if f["ref_pattern"]:
        return "REFERENCE"
    if f["math_ratio"] > 0.15 and len(text) < 120:
        return "FORMULA"
    if f["def_pattern"]:
        return "DEFINITION"
    return "PARAGRAPH"


@functools.lru_cache(maxsize=1)
def get_classifier() -> SectionClassifier:
    path = get_settings().classifier_path
    try:
        artefact = joblib.load(path)
        log.info("loaded section classifier %s", artefact["version"])
        return SectionClassifier(artefact)
    except FileNotFoundError:
        log.warning("classifier artefact %s not found; using rules only", path)
        return SectionClassifier(None)
