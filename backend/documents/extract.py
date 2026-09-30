"""Text extraction for PDF, DOCX and TXT.

PDF extraction keeps span-level typography (size, bold, italic, bbox) because
the section classifier uses it as features. Pages without a usable text layer
are routed to OCR.
"""

from __future__ import annotations

import io
import logging
import re

import pymupdf as fitz  # PyMuPDF
import numpy as np

from backend.documents import ocr
from backend.documents.types import ExtractedDocument, ExtractedPage, TextLine

log = logging.getLogger(__name__)

OCR_DPI = 300
MIN_TEXT_CHARS = 20


def _is_bold(font: str, flags: int) -> bool:
    return bool(flags & 16) or bool(re.search(r"bold|black|heavy|semibold", font, re.I))


def _is_italic(font: str, flags: int) -> bool:
    return bool(flags & 2) or bool(re.search(r"italic|oblique", font, re.I))


def _pdf_page_lines(page: fitz.Page, number: int) -> list[TextLine]:
    out: list[TextLine] = []
    data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(s["text"] for s in line["spans"]).strip()
            text = re.sub(r"\s+", " ", text)
            # Dominant span = the one covering most characters.
            dom = max(spans, key=lambda s: len(s["text"].strip()))
            chars = sum(len(s["text"].strip()) for s in spans)
            bold_chars = sum(
                len(s["text"].strip()) for s in spans if _is_bold(s.get("font", ""), s.get("flags", 0))
            )
            ital_chars = sum(
                len(s["text"].strip())
                for s in spans
                if _is_italic(s.get("font", ""), s.get("flags", 0))
            )
            out.append(
                TextLine(
                    text=text,
                    page=number,
                    bbox=tuple(round(v, 2) for v in line["bbox"]),
                    font_size=round(float(dom.get("size", 11.0)), 2),
                    is_bold=bold_chars > chars / 2,
                    is_italic=ital_chars > chars / 2,
                    font_name=dom.get("font", ""),
                    source="text_layer",
                )
            )
    out.sort(key=lambda ln: (round(ln.bbox[1] / 3), ln.bbox[0]))
    return out


def _ocr_page(page: fitz.Page, number: int) -> ExtractedPage:
    pix = page.get_pixmap(dpi=OCR_DPI, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    lines, mean_conf = ocr.ocr_image(img)
    scale = 72.0 / OCR_DPI  # pixels → PDF points
    text_lines = [
        TextLine(
            text=ln.text,
            page=number,
            bbox=tuple(round(v * scale, 2) for v in ln.bbox),
            # Cap height ≈ 0.7 × font size, so estimate size from line height.
            font_size=round(ln.height * scale / 0.72, 2),
            source="ocr",
            ocr_confidence=round(ln.confidence, 1),
        )
        for ln in lines
    ]
    return ExtractedPage(
        number=number,
        width=page.rect.width,
        height=page.rect.height,
        source="ocr",
        lines=text_lines,
        ocr_confidence=round(mean_conf, 1),
    )


def extract_pdf(data: bytes, allow_ocr: bool = True) -> ExtractedDocument:
    doc = ExtractedDocument(kind="pdf")
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for i, page in enumerate(pdf, start=1):
            lines = _pdf_page_lines(page, i)
            chars = sum(len(ln.text) for ln in lines)
            if chars < MIN_TEXT_CHARS and allow_ocr and ocr.tesseract_available():
                log.info("page %s has no text layer; running OCR", i)
                doc.pages.append(_ocr_page(page, i))
            else:
                doc.pages.append(
                    ExtractedPage(
                        number=i,
                        width=page.rect.width,
                        height=page.rect.height,
                        source="text_layer",
                        lines=lines,
                    )
                )
    return doc


_DOCX_HEADING = re.compile(r"^(heading|title|subtitle)\s*(\d*)", re.I)
# Nominal sizes so DOCX lines get comparable typography features.
_DOCX_SIZES = {"title": 26.0, "subtitle": 16.0, "1": 18.0, "2": 15.0, "3": 13.0}


def extract_docx(data: bytes) -> ExtractedDocument:
    import docx  # python-docx

    d = docx.Document(io.BytesIO(data))
    page = ExtractedPage(number=1, width=595.0, height=842.0, source="docx")
    y = 0.0

    def add(text: str, style: str | None, bold: bool, italic: bool, size: float | None):
        nonlocal y
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return
        m = _DOCX_HEADING.match(style or "")
        if size is None:
            if m:
                key = m.group(1).lower() if m.group(1).lower() != "heading" else (m.group(2) or "1")
                size = _DOCX_SIZES.get(key, 14.0)
            else:
                size = 11.0
        page.lines.append(
            TextLine(
                text=text,
                page=1,
                bbox=(72.0, y, 523.0, y + size * 1.2),
                font_size=size,
                is_bold=bold or bool(m),
                is_italic=italic,
                source="docx",
                style=style,
            )
        )
        y += size * 1.6

    for para in d.paragraphs:
        runs = [r for r in para.runs if r.text.strip()]
        chars = sum(len(r.text) for r in runs) or 1
        bold = sum(len(r.text) for r in runs if r.bold) > chars / 2
        italic = sum(len(r.text) for r in runs if r.italic) > chars / 2
        sizes = [r.font.size.pt for r in runs if r.font.size is not None]
        size = max(sizes) if sizes else None
        style = para.style.name if para.style is not None else None
        if style and style.lower().startswith("list"):
            add("• " + para.text, style, bold, italic, size)
        else:
            add(para.text, style, bold, italic, size)
    for table in d.tables:
        for row in table.rows:
            add(" | ".join(c.text.strip() for c in row.cells), "Table", False, False, None)
    doc = ExtractedDocument(kind="docx", pages=[page])
    return doc


def decode_text(data: bytes) -> str:
    from charset_normalizer import from_bytes

    best = from_bytes(data).best()
    text = str(best) if best is not None else data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def extract_txt(data: bytes) -> ExtractedDocument:
    text = decode_text(data)
    lines_per_page = 50
    raw_lines = text.split("\n")
    doc = ExtractedDocument(kind="txt")
    for p in range(0, max(len(raw_lines), 1), lines_per_page):
        number = p // lines_per_page + 1
        page = ExtractedPage(number=number, width=595.0, height=842.0, source="txt")
        for j, raw in enumerate(raw_lines[p : p + lines_per_page]):
            t = raw.rstrip()
            if not t.strip():
                # Keep blank lines as empty markers: they separate paragraphs.
                page.lines.append(TextLine(text="", page=number, bbox=(72, 72 + j * 14, 72, 72 + j * 14), source="txt"))
                continue
            page.lines.append(
                TextLine(
                    text=t.strip(),
                    page=number,
                    bbox=(72.0 + (len(t) - len(t.lstrip())) * 5, 72 + j * 14, 523.0, 84 + j * 14),
                    font_size=11.0,
                    source="txt",
                )
            )
        doc.pages.append(page)
    return doc


def extract(kind: str, data: bytes, allow_ocr: bool = True) -> ExtractedDocument:
    if kind == "pdf":
        return extract_pdf(data, allow_ocr=allow_ocr)
    if kind == "docx":
        return extract_docx(data)
    if kind == "txt":
        return extract_txt(data)
    raise ValueError(f"unsupported kind {kind}")
