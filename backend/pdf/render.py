"""Draw a DisplayList to PDF with ReportLab (vector output).

Paper, ink and page furniture are drawn here; *positions* all come from the
layout engine, so preview and final PDF are the same drawing.
"""

from __future__ import annotations

import io
import math

import pymupdf as fitz  # PyMuPDF
from reportlab.pdfgen import canvas

from backend.handwriting.styles import (
    GRID_COLOR,
    INKS,
    MARGIN_COLOR,
    PAPER_BG,
    RULE_COLOR,
    SHEET_LINE_COLOR,
    STYLES,
    bounded_gauss,
    seeded_rng,
)
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
    elif s.paper == "assignment":
        # Loose assignment sheet: no ruling, a header line across the top and
        # a margin line down the left.
        c.setStrokeColorRGB(*SHEET_LINE_COLOR)
        c.setLineWidth(0.55)
        top = dl.header.rule_y if dl.header and dl.header.rule_y is not None else dl.height - 15 * MM
        c.line(0, top, dl.width, top)
        mx = x0 - 3 * MM
        c.line(mx, 0, mx, top)


def _hand_text(c: canvas.Canvas, dl: DisplayList, text: str, x: float, y: float, size: float, shade: float, invisible: bool, key: object, align_right: bool = False) -> None:
    """A short handwritten string outside the text box (header, page number),
    with the same kind of bounded per-letter jitter as body text."""
    s = dl.settings
    style = STYLES[s.style]
    ink = INKS[s.ink]
    rng = seeded_rng("furniture", s.seed, s.style, key, text)
    chars = [(ch, fonts.font_for(ch, style.font)) for ch in text]
    if align_right:
        x -= sum(fonts.advance(ch, fn, size) for ch, fn in chars)
    c.saveState()
    t = c.beginText()
    t.setTextRenderMode(3 if invisible else 0)
    t.setFillColorRGB(*_mix(ink, shade))
    k = math.tan(math.radians(style.slant_deg))
    v = s.variation
    for ch, fn in chars:
        t.setFont(fn, size)
        if invisible:
            t.setTextTransform(1, 0, 0, 1, x, y)
        else:
            r = math.radians(bounded_gauss(rng, 1.0 * v))
            cr, sr = math.cos(r), math.sin(r)
            dy = bounded_gauss(rng, style.baseline_var * v * size)
            t.setTextTransform(cr, sr, cr * k - sr, sr * k + cr, x, y + dy)
        t.textOut(ch)
        x += fonts.advance(ch, fn, size)
    c.drawText(t)
    c.restoreState()


def _hand_rule(c: canvas.Canvas, x1: float, y1: float, x2: float, y2: float, rng) -> None:
    """A pen line drawn by hand: slightly bowed and uneven, not ruler-straight."""
    p = c.beginPath()
    p.moveTo(x1, y1)
    dx, dy = x2 - x1, y2 - y1
    amp = min(1.4, 0.012 * abs(dx) + 0.3)
    p.curveTo(x1 + dx / 3, y1 + dy / 3 + rng.uniform(-amp, amp), x1 + 2 * dx / 3, y1 + 2 * dy / 3 + rng.uniform(-amp, amp), x2, y2 + rng.uniform(-0.4, 0.4))
    c.drawPath(p, stroke=1, fill=0)


def render_pdf(dl: DisplayList, meta: dict | None = None, text_layer_only: bool = False) -> bytes:
    """Vector PDF of the display list.

    ``text_layer_only`` draws nothing visible: every glyph in invisible render
    mode, without rotation, and no paper/decorations. It is laid over the
    raster pages of a "scanned" PDF so the document stays searchable and
    auditable."""
    meta = meta or {}
    s = dl.settings
    ink = INKS[s.ink]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(dl.width, dl.height), pageCompression=1, invariant=1)
    c.setTitle(meta.get("title", "WriteAI document"))
    c.setAuthor("WriteAI 2.0")
    c.setCreator("WriteAI 2.0 handwriting engine")
    c.setSubject("Handwritten notes")
    c.setKeywords(";".join(f"writeai:{k}={v}" for k, v in sorted(meta.items()) if k != "title"))
    style = STYLES[s.style]

    for page in dl.pages:
        if not text_layer_only:
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
            started = False
            for g in glyphs:
                if not g.marker and not started:
                    started = True
                    if not g.cont:
                        # Invisible space at the start of every line: readers
                        # (and the audit) see a word boundary between lines.
                        t.setTextRenderMode(3)
                        t.setFont(g.font, g.size)
                        t.setTextTransform(1, 0, 0, 1, g.x - g.size * 0.3, g.y)
                        t.textOut(" ")
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
                stroke = max(0.25, g.size * 0.035) if g.fake_bold else g.weight
                if text_layer_only:
                    t.setTextRenderMode(3)
                    t.setFont(g.font, g.size)
                    t.setTextTransform(1, 0, 0, 1, g.x, g.y)
                    t.textOut(g.ch)
                    continue
                if stroke > 0.05:
                    # Fill + thin stroke: bold without a bold cut, or a word
                    # pressed harder with the pen. ("w" is legal inside BT/ET.)
                    t.setStrokeColorRGB(*col)
                    t.setTextRenderMode(2)
                    t._code.append(f"{stroke:.3f} w")
                else:
                    t.setTextRenderMode(0)
                t.setFont(g.font, g.size)
                # Text matrix = rotation (hand movement) x shear (slant).
                r, k = math.radians(g.rot), math.tan(math.radians(g.skew))
                cr, sr = math.cos(r), math.sin(r)
                t.setTextTransform(cr, sr, cr * k - sr, sr * k + cr, g.x, g.y)
                t.textOut(g.ch)
            c.drawText(t)
            c.restoreState()
        band = dl.header
        if band is not None:
            for i, (text, hx, hy) in enumerate(band.lines):
                _hand_text(c, dl, text, hx, hy, band.size, 0.95, text_layer_only, ("header", i, page.number))
            if band.page_number_y is not None:
                _hand_text(c, dl, str(page.number), dl.box[2], band.page_number_y, band.size, 0.95, text_layer_only, ("pageno", page.number), align_right=True)
        if text_layer_only:
            c.showPage()
            continue
        c.setStrokeColorRGB(*ink)
        c.setLineCap(1)
        for d in page.decorations:
            c.setLineWidth(d.width)
            if d.kind == "quote_bar":
                c.setStrokeColorRGB(*_mix(ink, 0.45))
            else:
                c.setStrokeColorRGB(*ink)
            if d.kind == "heading_rule":
                _hand_rule(c, d.x1, d.y1, d.x2, d.y2, seeded_rng("rule", s.seed, page.number, d.line_id))
            else:
                c.line(d.x1, d.y1, d.x2, d.y2)
        x0, y0, x1, y1 = dl.box
        if s.page_numbers and s.page_number_position == "bottom":
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
