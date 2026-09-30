"""Document statistics, sentence segmentation, keyphrases and injection flags."""

from __future__ import annotations

import functools
import logging
import re
from collections import Counter

log = logging.getLogger(__name__)

_SENT_FALLBACK = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_EN_STOP = set(
    "the of and to a in is that it for as with was on are be by this an which or from at "
    "can not have has we they their its these used into also more than such other "
    "what why how who whom when where which does did do is was were".split()
)
_INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now (a|an|the) ",
    r"system prompt",
    r"reveal (your|the) (instructions|prompt|api key)",
    r"<\s*/?\s*(system|assistant|instructions)\s*>",
]


@functools.lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy

        nlp = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer", "tagger", "attribute_ruler"])
        nlp.max_length = 3_000_000
        return nlp
    except Exception as exc:  # model not installed → regex fallback
        log.warning("spaCy model unavailable (%s); using regex sentence splitter", exc)
        return None


def split_sentences(text: str) -> list[str]:
    nlp = _nlp()
    if nlp is None:
        return [s.strip() for s in _SENT_FALLBACK.split(text) if s.strip()]
    return [s.text.strip() for s in nlp(text).sents if s.text.strip()]


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'\-]*|\d+(?:\.\d+)?", text)


def detect_language(text: str) -> str:
    words = [w.lower() for w in tokenize_words(text[:20000])]
    if len(words) < 20:
        return "unknown"
    ratio = sum(1 for w in words if w in _EN_STOP) / len(words)
    return "en" if ratio > 0.15 else "unknown"


def keyphrases(text: str, top: int = 12) -> list[str]:
    try:
        import yake

        kw = yake.KeywordExtractor(lan="en", n=3, top=top * 3, dedupLim=0.7)
        out: list[str] = []
        for k, _ in kw.extract_keywords(text[:100_000]):
            low = k.lower()
            toks = low.split()
            if len(set(toks)) < len(toks):  # "learning unsupervised learning"
                continue
            if any(low in o.lower() or o.lower() in low for o in out):
                continue
            out.append(k)
        return out[:top]
    except Exception:  # pragma: no cover - yake optional
        counts = Counter(w.lower() for w in tokenize_words(text) if w.lower() not in _EN_STOP and len(w) > 3)
        return [w for w, _ in counts.most_common(top)]


def count_syllables(word: str) -> int:
    """Heuristic syllable count: vowel groups, minus a silent trailing 'e'."""
    w = word.lower().strip("'")
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


def readability(text: str) -> dict:
    """Flesch Reading Ease and Flesch-Kincaid grade (standard formulas)."""
    words = [w for w in tokenize_words(text) if not w[0].isdigit()]
    sentences = split_sentences(text)
    if not words or not sentences:
        return {}
    syllables = sum(count_syllables(w) for w in words)
    wps = len(words) / len(sentences)
    spw = syllables / len(words)
    return {
        "flesch_reading_ease": round(206.835 - 1.015 * wps - 84.6 * spw, 1),
        "flesch_kincaid_grade": round(0.39 * wps + 11.8 * spw - 15.59, 1),
    }


def injection_flags(text: str) -> list[str]:
    """Spans that look like instructions aimed at an AI model. These are flagged
    to the user; the document is always treated as data, never as instructions."""
    found = []
    for pat in _INJECTION_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            start = max(0, m.start() - 40)
            found.append(text[start : m.end() + 40].replace("\n", " "))
    return found[:10]


def document_stats(full_text: str) -> dict:
    sentences = split_sentences(full_text) if full_text.strip() else []
    words = tokenize_words(full_text)
    return {
        "characters": len(full_text),
        "words": len(words),
        "sentences": len(sentences),
        "avg_sentence_length": round(len(words) / len(sentences), 1) if sentences else 0.0,
        "reading_time_min": round(len(words) / 200, 1),
        "language": detect_language(full_text),
        "keyphrases": keyphrases(full_text) if words else [],
        "readability": readability(full_text) if len(words) > 30 else {},
        "injection_flags": injection_flags(full_text),
    }
