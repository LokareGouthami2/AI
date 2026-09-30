"""NLP preprocessing: turn raw extracted lines into clean, merged segments.

Steps (each a small pure function):
  1. normalise_text        – unicode cleanup (ligatures, quotes, control chars)
  2. remove_headers_footers – drop running headers/footers and page numbers
  3. merge_lines            – join wrapped lines into logical blocks (segments)
  4. dehyphenate            – repair words split across line ends
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass

from backend.documents.types import ExtractedDocument, TextLine

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_QUOTES = {"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"', " ": " ", "​": ""}
_PAGE_NUM = re.compile(r"^\s*(page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?\s*(of\s*\d+)?\s*$", re.I)
_BLOCK_START = re.compile(
    r"^\s*(?:[•●▪◦\-–*]\s+|\(?\d{1,3}[.)]\s+|\(?[a-z][.)]\s+|q\d+[.:)]|step\s*\d+|\[\d+\]|"
    r"answer\s*[:.]|definition\s*[:.]|example\s*[:.]|note\s*[:.]|important\s*[:.])",
    re.I,
)
# "Surname, A. B. (1999)" — a new bibliography entry (case-sensitive on purpose).
_CITATION_START = re.compile(r"^[A-Z][a-z]+,\s(?:[A-Z]\.\s?)+(?:,|&|\(|et al)")


def normalise_text(text: str) -> str:
    # NFC (not NFKC): NFKC would turn "x²" into "x2" and damage formulas.
    text = unicodedata.normalize("NFC", text)
    for k, v in {**_LIGATURES, **_QUOTES}.items():
        text = text.replace(k, v)
    text = "".join(ch for ch in text if ch in "\t\n" or unicodedata.category(ch)[0] != "C")
    return re.sub(r"[ \t]+", " ", text).strip()


def _mask(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def remove_headers_footers(doc: ExtractedDocument, band: float = 0.08) -> ExtractedDocument:
    """Drop lines that repeat in the top/bottom band on ≥50% of pages, and
    bare page numbers. Needs ≥3 pages for the repetition heuristic."""
    n_pages = len(doc.pages)
    repeated: set[str] = set()
    if n_pages >= 3:
        counts: Counter[str] = Counter()
        for p in doc.pages:
            seen = set()
            for ln in p.lines:
                if not ln.text or p.height <= 0:
                    continue
                y = ln.bbox[1] / p.height
                if y < band or y > 1 - band:
                    seen.add(_mask(ln.text))
            counts.update(seen)
        repeated = {t for t, c in counts.items() if c >= max(2, n_pages // 2)}

    for p in doc.pages:
        kept = []
        for ln in p.lines:
            in_band = p.height > 0 and (
                ln.bbox[1] / p.height < band or ln.bbox[1] / p.height > 1 - band
            )
            if ln.text and _PAGE_NUM.match(ln.text) and (in_band or ln.source in ("txt",)):
                continue
            if in_band and _mask(ln.text) in repeated:
                continue
            kept.append(ln)
        p.lines = kept
    return doc


def dehyphenate(prev: str, nxt: str) -> str:
    """Join two wrapped lines, repairing a hyphen split like 'classi-' + 'fication'."""
    if re.search(r"[A-Za-z]-$", prev) and nxt[:1].islower():
        return prev[:-1] + nxt
    return prev + " " + nxt


@dataclass
class Segment:
    text: str
    page: int
    bbox: tuple[float, float, float, float]
    font_size: float
    is_bold: bool
    is_italic: bool
    line_count: int
    gap_before: float
    gap_after: float
    indent: float
    source: str
    style: str | None = None
    ocr_confidence: float | None = None
    page_height: float = 842.0
    page_width: float = 595.0

    def to_dict(self) -> dict:
        return asdict(self)


def _same_block(prev: TextLine, cur: TextLine, prev_seg_lines: int) -> bool:
    if cur.source in ("docx",):
        return False  # DOCX paragraphs are already logical blocks
    if prev.page != cur.page or not prev.text or not cur.text:
        return False
    if abs(prev.font_size - cur.font_size) > 0.6 or prev.is_bold != cur.is_bold:
        return False
    if _BLOCK_START.match(cur.text) or _CITATION_START.match(cur.text):
        return False
    line_h = max(prev.bbox[3] - prev.bbox[1], prev.font_size * 1.1, 1.0)
    gap = cur.bbox[1] - prev.bbox[3]
    if gap > 0.9 * line_h or gap < -line_h:
        return False
    # A short previous line ending a sentence usually ends a paragraph.
    prev_width = prev.bbox[2] - prev.bbox[0]
    if prev.source != "txt" and prev_width > 0 and re.search(r"[.:!?]$", prev.text):
        cur_width = cur.bbox[2] - cur.bbox[0]
        if prev_width < 0.7 * max(cur_width, prev_width) and prev_seg_lines >= 1:
            return False
    return True


def merge_lines(doc: ExtractedDocument) -> list[Segment]:
    segments: list[Segment] = []
    page_dims = {p.number: (p.width or 595.0, p.height or 842.0) for p in doc.pages}
    lines = [ln for ln in doc.lines]
    cur: list[TextLine] = []

    def flush(next_line: TextLine | None) -> None:
        if not cur:
            return
        text = cur[0].text
        for ln in cur[1:]:
            text = dehyphenate(text, ln.text)
        text = normalise_text(text)
        if not text:
            cur.clear()
            return
        x0 = min(ln.bbox[0] for ln in cur)
        y0 = min(ln.bbox[1] for ln in cur)
        x1 = max(ln.bbox[2] for ln in cur)
        y1 = max(ln.bbox[3] for ln in cur)
        gap_before = 0.0
        if segments and segments[-1].page == cur[0].page:
            gap_before = max(0.0, y0 - segments[-1].bbox[3])
        confs = [ln.ocr_confidence for ln in cur if ln.ocr_confidence is not None]
        w, h = page_dims.get(cur[0].page, (595.0, 842.0))
        segments.append(
            Segment(
                text=text,
                page=cur[0].page,
                bbox=(x0, y0, x1, y1),
                font_size=statistics.median(ln.font_size for ln in cur),
                is_bold=cur[0].is_bold,
                is_italic=cur[0].is_italic,
                line_count=len(cur),
                gap_before=round(gap_before, 2),
                gap_after=0.0,
                indent=round(x0, 2),
                source=cur[0].source,
                style=cur[0].style,
                ocr_confidence=round(sum(confs) / len(confs), 1) if confs else None,
                page_height=h,
                page_width=w,
            )
        )
        cur.clear()

    for ln in lines:
        if not ln.text.strip():
            flush(ln)
            continue
        if cur and not _same_block(cur[-1], ln, len(cur)):
            flush(ln)
        cur.append(ln)
    flush(None)

    for i in range(len(segments) - 1):
        a, b = segments[i], segments[i + 1]
        if a.page == b.page:
            a.gap_after = round(max(0.0, b.bbox[1] - a.bbox[3]), 2)
    return segments


def preprocess(doc: ExtractedDocument) -> list[Segment]:
    for p in doc.pages:
        for ln in p.lines:
            ln.text = normalise_text(ln.text)
    remove_headers_footers(doc)
    return merge_lines(doc)
