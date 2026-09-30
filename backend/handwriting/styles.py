"""Handwriting style presets and seeded variation.

A style = a font (+ optional bold cut) and a variation profile. The variation
is *controlled imperfection*: every amplitude is bounded, so the quality
checker can prove text stays inside its line box and above a readable size.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class StyleProfile:
    name: str
    label: str
    font: str
    bold_font: str | None
    size_scale: float  # visual size normalisation between fonts
    slant_deg: float  # base slant (positive = right-leaning)
    slant_var: float  # ± per word
    baseline_var: float  # per-glyph vertical jitter, fraction of font size
    drift: float  # per-line baseline drift amplitude, fraction of font size
    size_var: float  # per-glyph size variation (fraction)
    spacing_var: float  # per-glyph extra advance, fraction of font size
    word_space: float  # word-space multiplier


STYLES: dict[str, StyleProfile] = {
    "neat": StyleProfile("neat", "Neat (Kalam)", "kalam-400", "kalam-700", 1.0, 2.0, 1.0, 0.018, 0.02, 0.025, 0.012, 1.0),
    "casual": StyleProfile("casual", "Casual (Patrick Hand)", "patrick-hand-400", None, 1.08, 0.0, 1.5, 0.025, 0.03, 0.035, 0.015, 1.05),
    "cursive": StyleProfile("cursive", "Cursive (Homemade Apple)", "homemade-apple-400", None, 0.78, 0.0, 1.0, 0.012, 0.02, 0.02, 0.006, 1.0),
    "playful": StyleProfile("playful", "Playful (Indie Flower)", "indie-flower-400", None, 1.05, 0.0, 2.0, 0.03, 0.03, 0.04, 0.015, 1.05),
    "quick": StyleProfile("quick", "Quick notes (Caveat)", "caveat-400", "caveat-700", 1.2, 0.0, 1.5, 0.022, 0.03, 0.03, 0.01, 1.1),
    "light": StyleProfile("light", "Light (Shadows Into Light)", "shadows-into-light-400", None, 1.1, 0.0, 1.5, 0.025, 0.03, 0.035, 0.012, 1.05),
}

INKS = {
    "blue": (0.09, 0.17, 0.55),
    "black": (0.11, 0.11, 0.13),
}
PAPER_BG = (1.0, 1.0, 0.985)
RULE_COLOR = (0.62, 0.76, 0.90)
MARGIN_COLOR = (0.90, 0.45, 0.45)
GRID_COLOR = (0.80, 0.86, 0.92)


def seeded_rng(*parts: object) -> random.Random:
    """Deterministic RNG from arbitrary parts (content, settings seed, ids)."""
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def bounded_gauss(rng: random.Random, sigma: float, limit: float = 2.0) -> float:
    """Gaussian noise clipped to ±limit·sigma (keeps variation provably bounded)."""
    if sigma <= 0:
        return 0.0
    return max(-limit * sigma, min(limit * sigma, rng.gauss(0.0, sigma)))
