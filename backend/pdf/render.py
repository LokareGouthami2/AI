"""Draw a DisplayList to PDF with ReportLab (vector output).

Paper, ink and page furniture are drawn here; *positions* all come from the
layout engine, so preview and final PDF are the same drawing.
"""

from __future__ import annotations

import io
import math

import pymupdf as fitz  # PyMuPDF
from reportlab.pdfgen import canvas

from backend.handwriting.styles import GRID_COLOR, INKS, MARGIN_COLOR, PAPER_BG, RULE_COLOR, STYLES
from backend.layout import fonts
from backend.layout.engine import MM, DisplayList

WATERMARK = "Generated with WriteAI"


def _mix(ink: tuple[float, float, float], shade: float) -> tuple[float, float, float]:
    return tuple(ink[i] * shade + PAPER_BG[i] * (1 - shade) for i in range(3))  # type: ignore[return-value]


def _draw_paper(c: canvas.Canvas, dl: DisplayList) -> None:
    s = dl.settings
    x0, y0, x1, y1 = dl.box
    c.setFillColorRGB(*PAPER_BG)
    c.rect(0, 0, dl.width, dl.height, stroke=0, fill=1)
    if s.paper == "ruled":
        c.setStrokeColorRGB(*RULE_COLOR)
        c.setLineWidth(0.5)
        for k in range(dl.slots_per_page):
            y = y1 - (k + 1) * dl.line_height
            c.line(0, y, dl.width, y)
        c.setStrokeColorRGB(*MARGIN_COLOR)
        c.setLineWidth(0.7)
        mx = x0 - 3 * MM
        c.line(mx, 0, mx, dl.height)
    elif s.paper == "grid":
        c.setStrokeColorRGB(*GRID_COLOR)
        c.setLineWidth(0.35)
        step = dl.line_height / 2
        y = y1
        while y > 0:
            c.line(0, y, dl.width, y)
            y -= step
        x = x0
        while x > 0:
            x -= step
        while x < dl.width:
            c.line(x, 0, x, dl.height)
            x += step


def render_pdf(dl: DisplayList, meta: dict | None = None) -> bytes:
    meta = meta or {}
    s = dl.settings
    ink = INKS[s.ink]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(dl.width, dl.height), pageCompression=1, invariant=1)
    c.setTitle(meta.get("title", "WriteAI document"))
    c.setAuthor("WriteAI 2.0")
    c.setCreator("WriteAI 2.0 handwriting engine")
    c.setSubject("Computer-generated handwriting-style document")
    c.setKeywords(";".join(f"writeai:{k}={v}" for k, v in sorted(meta.items()) if k != "title"))
    style = STYLES[s.style]

    for page in dl.pages:
        _draw_paper(c, dl)
        # Glyphs: one text object per line; per-glyph text matrix gives
        # jitter (translation) and slant (shear) without rotating the baseline.
        by_line: dict[int, list] = {}
        for g in page.glyphs:
            by_line.setdefault(g.line_id, []).append(g)
        for glyphs in by_line.values():
            c.saveState()  # text render mode is graphics state: isolate each line
            t = c.beginText()
            prev = None
            for g in glyphs:
                if g.word_start and prev is not None:
                    # Real space character between words: keeps the PDF's text
                    # layer (copy/paste, search, audit) word-accurate.
                    t.setTextRenderMode(3)  # invisible
                    t.setFont(prev.font, prev.size)
                    t.setTextTransform(1, 0, 0, 1, prev.x + prev.advance, prev.y)
                    t.textOut(" ")
                prev = g
                col = _mix(ink, g.shade)
                t.setFillColorRGB(*col)
                if g.fake_bold:
                    t.setStrokeColorRGB(*col)
                    t.setTextRenderMode(2)
                    c.setLineWidth(max(0.25, g.size * 0.035))
                else:
                    t.setTextRenderMode(0)
                t.setFont(g.font, g.size)
                t.setTextTransform(1, 0, math.tan(math.radians(g.skew)), 1, g.x, g.y)
                t.textOut(g.ch)
            c.drawText(t)
            c.restoreState()
        c.setStrokeColorRGB(*ink)
        c.setLineCap(1)
        for d in page.decorations:
            c.setLineWidth(d.width)
            if d.kind == "quote_bar":
                c.setStrokeColorRGB(*_mix(ink, 0.45))
            else:
                c.setStrokeColorRGB(*ink)
            c.line(d.x1, d.y1, d.x2, d.y2)
        x0, y0, x1, y1 = dl.box
        if s.page_numbers:
            label = f"– {page.number} –"
            size = max(10.0, s.font_size * 0.75)
            c.setFillColorRGB(*_mix(ink, 0.8))
            fname = style.font
            w = sum(fonts.advance(ch, fonts.font_for(ch, fname), size) for ch in label)
            t = c.beginText((dl.width - w) / 2, y0 / 2)
            for ch in label:
                t.setFont(fonts.font_for(ch, fname), size)
                t.textOut(ch)
            c.drawText(t)
        if s.watermark:
            c.setFillColorRGB(0.6, 0.6, 0.6)
            c.setFont("Helvetica", 6.5)
            c.drawRightString(dl.width - 10 * MM, 6 * MM, WATERMARK)
        c.showPage()
    c.save()
    return buf.getvalue()


def pdf_metadata(pdf: bytes) -> dict:
    with fitz.open(stream=pdf, filetype="pdf") as d:
        kw = d.metadata.get("keywords") or ""
    out = {}
    for part in kw.split(";"):
        if part.startswith("writeai:") and "=" in part:
            k, v = part[len("writeai:"):].split("=", 1)
            out[k] = v
    return out


def rasterize(pdf: bytes, dpi: int = 110, pages: list[int] | None = None) -> list[bytes]:
    """PNG bytes for each page (preview = picture of the actual PDF)."""
    out = []
    with fitz.open(stream=pdf, filetype="pdf") as d:
        for i, page in enumerate(d, start=1):
            if pages and i not in pages:
                continue
            out.append(page.get_pixmap(dpi=dpi, alpha=False).tobytes("png"))
    return out
