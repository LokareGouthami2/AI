"""Font registry: registers bundled fonts with ReportLab and exposes metrics
(advance widths, per-glyph ink bounds) used by the layout engine."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont as FTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FALLBACK = "dejavu-sans-fallback"


@dataclass
class FontInfo:
    name: str
    cmap: set[int]
    upm: int
    # ink bounds per codepoint in em units: (yMin, yMax)
    bounds: dict[int, tuple[float, float]] = field(default_factory=dict)

    def has(self, ch: str) -> bool:
        return ord(ch) in self.cmap

    def ink_bounds(self, ch: str) -> tuple[float, float]:
        return self.bounds.get(ord(ch), (-0.25, 0.8))


def _load(name: str) -> FontInfo:
    path = FONT_DIR / f"{name}.ttf"
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    ft = FTFont(str(path))
    cmap = ft.getBestCmap()
    upm = ft["head"].unitsPerEm
    bounds: dict[int, tuple[float, float]] = {}
    if "glyf" in ft:
        glyf = ft["glyf"]
        for cp, gname in cmap.items():
            g = glyf[gname]
            if g.numberOfContours == 0:
                bounds[cp] = (0.0, 0.0)
                continue
            g.recalcBounds(glyf)
            bounds[cp] = (g.yMin / upm, g.yMax / upm)
    return FontInfo(name=name, cmap=set(cmap), upm=upm, bounds=bounds)


@functools.cache
def font(name: str) -> FontInfo:
    return _load(name)


def font_for(ch: str, preferred: str) -> str:
    """Name of the font that will draw ``ch`` (preferred, else fallback)."""
    if ch == " " or font(preferred).has(ch):
        return preferred
    return FALLBACK if font(FALLBACK).has(ch) else preferred


def advance(ch: str, font_name: str, size: float) -> float:
    return pdfmetrics.stringWidth(ch, font_name, size)
