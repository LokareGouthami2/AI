"""Feature engineering for the section classifier.

A sample is a dict produced by :func:`segment_samples` — the segment text plus
typographic/positional features and a 1-segment context window. Transformers
here are plain scikit-learn estimators so the whole model is one picklable
Pipeline.
"""

from __future__ import annotations

import re
import statistics

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from backend.nlp.preprocess import Segment

_MATH = set("=+−-×*/÷^²³√∑Σ∫πθλμσΔ≤≥≈≠<>()[]{}|")
_BULLET = re.compile(r"^\s*(?:[•●▪◦\-–*])\s+")
_NUMBERED = re.compile(r"^\s*\(?(\d{1,3})[.)]\s+")
_SUBNUMBERED = re.compile(r"^\s*\d{1,3}\.\d{1,3}(\.\d{1,3})?\.?\s+")
_QPREFIX = re.compile(r"^\s*(q\s*\d+|question\s*\d*)\s*[.:)]", re.I)
_APREFIX = re.compile(r"^\s*(ans(wer)?|solution|sol)\s*[.:)\-]", re.I)
_REF = re.compile(r"(\[\d+\]|\(\d{4}\)|\b(19|20)\d{2}\b|et al\.|doi:|https?://|pp\.|vol\.)", re.I)
_DEF = re.compile(r"\b(is defined as|refers to|is called|is known as|means that|definition)\b", re.I)
_EX = re.compile(r"^\s*(e\.g\.|example|for example|for instance|consider|illustration)\b", re.I)
_PROC = re.compile(r"\b(step\s*\d+|first,|then,|next,|finally,|procedure|method:)", re.I)
_IMP = re.compile(r"^\s*(important|note|remember|key point|caution|warning|tip)\b", re.I)
_CONC = re.compile(r"^\s*(in conclusion|to conclude|in summary|to summari[sz]e|overall|thus,|therefore,|conclusion)\b", re.I)
_IMPERATIVE_Q = re.compile(r"^\s*(explain|describe|discuss|define|compare|what|why|how|which|state|list|calculate|derive|name)\b", re.I)

LAYOUT_FEATURE_NAMES = [
    "font_ratio",
    "is_bold",
    "is_italic",
    "caps_ratio",
    "title_case_ratio",
    "n_tokens_log",
    "line_count",
    "ends_colon",
    "ends_question",
    "ends_period",
    "starts_bullet",
    "starts_number",
    "starts_subnumber",
    "starts_qprefix",
    "starts_aprefix",
    "digit_ratio",
    "math_ratio",
    "ref_pattern",
    "def_pattern",
    "ex_pattern",
    "proc_pattern",
    "imp_pattern",
    "conc_pattern",
    "imperative_q",
    "rel_position",
    "is_first",
    "rel_y",
    "indent_ratio",
    "gap_before_ratio",
    "gap_after_ratio",
    "prev_font_ratio",
    "next_font_ratio",
    "prev_is_bold",
    "next_is_bold",
    "prev_ends_question",
    "is_largest_font",
    "is_txt",
]


def _ratio(pred, text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    return sum(1 for c in chars if pred(c)) / len(chars) if chars else 0.0


def segment_samples(segments: list[Segment]) -> list[dict]:
    """Convert preprocessed segments to classifier samples (text + features)."""
    if not segments:
        return []
    sizes = [s.font_size for s in segments]
    median = statistics.median(sizes) or 11.0
    max_size = max(sizes)
    n = len(segments)
    samples = []
    for i, s in enumerate(segments):
        text = s.text
        tokens = text.split()
        prev = segments[i - 1] if i > 0 else None
        nxt = segments[i + 1] if i + 1 < n else None
        words = [w for w in tokens if w[:1].isalpha()]
        f = {
            "font_ratio": s.font_size / median,
            "is_bold": float(s.is_bold),
            "is_italic": float(s.is_italic),
            "caps_ratio": _ratio(str.isupper, "".join(ch for ch in text if ch.isalpha())),
            "title_case_ratio": (sum(1 for w in words if w[0].isupper()) / len(words)) if words else 0.0,
            "n_tokens_log": float(np.log1p(len(tokens))),
            "line_count": float(min(s.line_count, 10)),
            "ends_colon": float(text.rstrip().endswith(":")),
            "ends_question": float(text.rstrip().endswith("?")),
            "ends_period": float(text.rstrip().endswith(".")),
            "starts_bullet": float(bool(_BULLET.match(text))),
            "starts_number": float(bool(_NUMBERED.match(text))),
            "starts_subnumber": float(bool(_SUBNUMBERED.match(text))),
            "starts_qprefix": float(bool(_QPREFIX.match(text))),
            "starts_aprefix": float(bool(_APREFIX.match(text))),
            "digit_ratio": _ratio(str.isdigit, text),
            "math_ratio": _ratio(lambda c: c in _MATH, text),
            "ref_pattern": float(len(_REF.findall(text)) >= 2),
            "def_pattern": float(bool(_DEF.search(text))),
            "ex_pattern": float(bool(_EX.match(text))),
            "proc_pattern": float(len(_PROC.findall(text)) >= 1),
            "imp_pattern": float(bool(_IMP.match(text))),
            "conc_pattern": float(bool(_CONC.match(text))),
            "imperative_q": float(bool(_IMPERATIVE_Q.match(text))),
            "rel_position": i / max(n - 1, 1),
            "is_first": float(i == 0),
            "rel_y": (s.bbox[1] / s.page_height) if s.page_height else 0.0,
            "indent_ratio": (s.indent / s.page_width) if s.page_width else 0.0,
            "gap_before_ratio": min(s.gap_before / max(s.font_size, 1.0), 5.0),
            "gap_after_ratio": min(s.gap_after / max(s.font_size, 1.0), 5.0),
            "prev_font_ratio": (prev.font_size / median) if prev else 0.0,
            "next_font_ratio": (nxt.font_size / median) if nxt else 0.0,
            "prev_is_bold": float(prev.is_bold) if prev else 0.0,
            "next_is_bold": float(nxt.is_bold) if nxt else 0.0,
            "prev_ends_question": float(prev.text.rstrip().endswith("?")) if prev else 0.0,
            "is_largest_font": float(s.font_size >= max_size and max_size > median * 1.05),
            "is_txt": float(s.source == "txt"),
        }
        samples.append({"text": text, "layout": f, "page": s.page})
    return samples


class TextSelector(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return [x["text"] for x in X]


class LayoutFeaturizer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return np.array([[x["layout"][k] for k in LAYOUT_FEATURE_NAMES] for x in X], dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.array(LAYOUT_FEATURE_NAMES)
