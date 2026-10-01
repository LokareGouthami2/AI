"""Quality checker: validates a layout (pre-render) and a PDF (post-render).

Every check returns concrete evidence (page, counts, missing tokens) so the UI
can show the user exactly what is wrong. Errors block the final render;
warnings are informational.
"""

from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass, field

import pymupdf as fitz  # PyMuPDF

from backend.editor.wdm import (
    TextNode,
    WDMDocument,
    count_blank_lines,
    count_hard_breaks,
    document_tokens,
    iter_text_blocks,
)
from backend.handwriting.styles import INKS, PAPER_BG
from backend.layout import fonts
from backend.layout.engine import MIN_READABLE_PT, DisplayList, glyphs_collide
from backend.quality.pdf_inspect import trace_chars

TOL = 0.75  # points


@dataclass
class Issue:
    code: str
    message: str
    page: int | None = None
    details: dict = field(default_factory=dict)


@dataclass
class QualityReport:
    passed: bool
    errors: list[Issue]
    warnings: list[Issue]
    metrics: dict
    checks: list[str]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": [asdict(e) for e in self.errors],
            "warnings": [asdict(w) for w in self.warnings],
            "metrics": self.metrics,
            "checks": self.checks,
        }


def _luminance(rgb: tuple[float, float, float]) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _underlined_chars(doc: WDMDocument) -> str:
    return "".join(
        ch
        for b in iter_text_blocks(doc)
        for n in b.content
        if isinstance(n, TextNode) and "underline" in n.marks
        for ch in n.text
        if not ch.isspace()
    )


def _token_diff(expected: list[str], actual: list[str]) -> dict:
    sm = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
    missing, extra = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            missing.extend(expected[i1:i2])
        if tag in ("insert", "replace"):
            extra.extend(actual[j1:j2])
    return {"missing": missing[:50], "extra": extra[:50], "ratio": round(sm.ratio(), 4)}


def check_layout(doc: WDMDocument, dl: DisplayList) -> QualityReport:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    checks: list[str] = []
    x0, y0, x1, y1 = dl.box

    # 1. Overflow / clipping — every glyph's ink inside the text box.
    checks.append("overflow")
    for p in dl.pages:
        bad = 0
        for g in p.glyphs:
            lo, hi = fonts.font(g.font).ink_bounds(g.ch)
            if g.x < x0 - TOL - (g.size * 3 if g.marker else 0) or g.x + g.advance > x1 + TOL or g.y + hi * g.size > y1 + TOL or g.y + lo * g.size < y0 - TOL:
                bad += 1
        if bad:
            errors.append(Issue("OVERFLOW", f"{bad} glyph(s) fall outside the printable area", p.number, {"glyphs": bad}))

    # 2. Overlap — consecutive lines' ink must not intersect.
    checks.append("overlap")
    for p in dl.pages:
        by_line: dict[int, list] = {}
        for g in p.glyphs:
            by_line.setdefault(g.line_id, []).append(g)
        text_lines = sorted((ln for ln in p.lines if ln.kind != "blank"), key=lambda ln: -ln.baseline)
        for a, b in zip(text_lines, text_lines[1:]):
            if glyphs_collide(by_line.get(a.id, []), by_line.get(b.id, [])):
                errors.append(Issue("OVERLAP", f"ink of line '{a.text[:30]}' touches the line below", p.number))

    # 3. Empty pages.
    checks.append("empty_pages")
    for p in dl.pages:
        if not any(not g.marker for g in p.glyphs):
            errors.append(Issue("EMPTY_PAGE", "page contains no text", p.number))

    # 4. Missing / extra content — exact token sequence.
    checks.append("content_coverage")
    expected = document_tokens(doc)
    actual = dl.stats["tokens"]
    if expected != actual:
        errors.append(Issue("CONTENT_MISMATCH", "rendered text differs from the edited document", None, _token_diff(expected, actual)))

    # 5. Line breaks preserved.
    checks.append("line_breaks")
    exp_blank = count_blank_lines(doc) - dl.stats["trimmed_trailing_blank"]
    if dl.stats["blank_lines"] != exp_blank:
        errors.append(Issue("BLANK_LINES", f"expected {exp_blank} blank line(s), rendered {dl.stats['blank_lines']}"))
    if dl.stats["hard_breaks"] != count_hard_breaks(doc):
        errors.append(Issue("HARD_BREAKS", f"expected {count_hard_breaks(doc)} line break(s), rendered {dl.stats['hard_breaks']}"))
    if dl.stats["trimmed_trailing_blank"]:
        warnings.append(Issue("TRAILING_BLANK", f"{dl.stats['trimmed_trailing_blank']} blank line(s) at the very end were not rendered"))

    # 6. Broken paragraphs / orphan headings.
    checks.append("orphans_widows")
    for p, nxt in zip(dl.pages, dl.pages[1:]):
        content = [ln for ln in p.lines if ln.kind != "blank"]
        if content and content[-1].kind == "heading":
            nxt_first = next((ln for ln in nxt.lines if ln.kind != "blank"), None)
            bid = content[-1].block_id
            started_earlier = any(ln.block_id == bid for q in dl.pages[: p.number - 1] for ln in q.lines)
            # Already at the top of the page: heading + following lines exceed a page.
            at_top = content[0].block_id == bid
            if (nxt_first is not None and nxt_first.block_id == bid) or started_earlier or at_top:
                # A heading longer than a page has to continue on the next one.
                warnings.append(Issue("HEADING_SPLIT", f"heading '{content[-1].text[:40]}' is too long for one page", p.number))
            else:
                errors.append(Issue("ORPHAN_HEADING", f"heading '{content[-1].text[:40]}' is the last line on the page", p.number))
    for prev, p in zip(dl.pages, dl.pages[1:]):
        first = next((ln for ln in p.lines if ln.kind != "blank"), None)
        last_prev = next((ln for ln in reversed(prev.lines) if ln.kind != "blank"), None)
        if first and last_prev and first.block_id == last_prev.block_id:
            n_next = sum(1 for ln in p.lines if ln.block_id == first.block_id)
            if n_next == 1 and sum(1 for ln in prev.lines if ln.block_id == first.block_id) >= 2:
                warnings.append(Issue("WIDOW", "a paragraph's last line is alone at the top of the page", p.number))

    # 7. Readability.
    checks.append("readability")
    min_size = dl.stats["min_font_size"]
    if min_size < MIN_READABLE_PT:
        errors.append(Issue("TEXT_TOO_SMALL", f"smallest text is {min_size:.1f}pt (minimum {MIN_READABLE_PT}pt)"))
    ink = INKS[dl.settings.ink]
    lightest = tuple(ink[i] * 0.84 + PAPER_BG[i] * 0.16 for i in range(3))
    cr = contrast_ratio(lightest, PAPER_BG)
    if cr < 4.5:
        errors.append(Issue("LOW_CONTRAST", f"ink contrast {cr:.2f}:1 is below 4.5:1"))

    # 8. Underline audit — only where the user applied it.
    checks.append("underline")
    exp_ul = _underlined_chars(doc)
    got_ul = dl.stats["underlined_chars"]
    ul_decos = [d for p in dl.pages for d in p.decorations if d.kind == "underline"]
    if exp_ul != got_ul:
        errors.append(Issue("UNDERLINE_MISMATCH", "underlined text differs from the editor's underline marks", None, {"expected": exp_ul[:80], "rendered": got_ul[:80]}))
    if not exp_ul and ul_decos:
        errors.append(Issue("UNWANTED_UNDERLINE", f"{len(ul_decos)} underline(s) drawn but none requested"))
    for p in dl.pages:
        for d in p.decorations:
            if d.kind != "underline":
                continue
            under = [g for g in p.glyphs if g.line_id == d.line_id and not g.marker and g.x >= d.x1 - 0.01 and g.x + g.advance <= d.x2 + 0.01]
            if any(not g.underline for g in under):
                errors.append(Issue("UNWANTED_UNDERLINE", "underline drawn under text that is not marked underline", p.number))
    # Heading rules are a separate, opt-in render setting: only under heading
    # lines, and only when the user switched "underline headings" on.
    rules = [(p, d) for p in dl.pages for d in p.decorations if d.kind == "heading_rule"]
    heading_lines = {(p.number, ln.id) for p in dl.pages for ln in p.lines if ln.kind == "heading"}
    if rules and not dl.settings.underline_headings:
        errors.append(Issue("UNWANTED_UNDERLINE", f"{len(rules)} heading rule(s) drawn but heading underlines are off"))
    if any((p.number, d.line_id) not in heading_lines for p, d in rules):
        errors.append(Issue("UNWANTED_UNDERLINE", "heading rule drawn under a line that is not a heading"))

    metrics = {
        "pages": len(dl.pages),
        "lines": dl.stats["lines"],
        "blank_lines": dl.stats["blank_lines"],
        "hard_breaks": dl.stats["hard_breaks"],
        "tokens": len(actual),
        "underline_segments": len(ul_decos),
        "heading_rules": len(rules),
        "min_font_size": round(min_size, 2),
        "contrast_ratio": round(cr, 2),
        "fill_ratio": round(sum(len(p.lines) for p in dl.pages) / max(1, len(dl.pages) * dl.slots_per_page), 3),
    }
    return QualityReport(not errors, errors, warnings, metrics, checks)


def _pdf_tokens(pdf: bytes, dl: DisplayList, check_strokes: bool = True) -> tuple[list[str], int, int]:
    """Words drawn inside the text box (markers excluded), in drawing order;
    ink-coloured horizontal strokes (underlines); page count."""
    x0, y0, x1, y1 = dl.box
    chars: list[str] = []
    ul_strokes = 0
    ink = INKS[dl.settings.ink]
    with fitz.open(stream=pdf, filetype="pdf") as d:
        n_pages = d.page_count
        for page, pout in zip(d, dl.pages):
            H = page.rect.height
            clip = fitz.Rect(x0 - 40, H - y1 - 4, x1 + 4, H - y0 + 4)
            markers = [fitz.Rect(mx0, H - my1, mx1, H - my0) for mx0, my0, mx1, my1 in pout.markers]
            for ch, x, y, _ in trace_chars(page):
                p = fitz.Point(x, y)
                if not clip.contains(p) or any(m.contains(p) for m in markers):
                    continue
                chars.append(ch)
            chars.append(" ")
            if not check_strokes:
                continue
            for dr in page.get_drawings():
                col = dr.get("color")
                if not col or max(abs(col[i] - ink[i]) for i in range(3)) > 0.02:
                    continue
                for item in dr["items"]:
                    if item[0] == "l":
                        p1, p2 = item[1], item[2]
                        if abs(p1.y - p2.y) < 3 and abs(p2.x - p1.x) > 1:
                            ul_strokes += 1
    return "".join(chars).split(), ul_strokes, n_pages


def audit_pdf(doc: WDMDocument, dl: DisplayList, pdf: bytes, expected_meta: dict, check_strokes: bool = True) -> QualityReport:
    """Post-render: read the PDF back and compare with the edited document.
    ``check_strokes=False`` for scanned output (strokes are pixels there; the
    underline audit runs on the vector PDF before scanning)."""
    from backend.pdf.render import pdf_metadata

    errors: list[Issue] = []
    warnings: list[Issue] = []
    tokens, ul_strokes, n_pages = _pdf_tokens(pdf, dl, check_strokes)
    expected = document_tokens(doc)
    diff = _token_diff(expected, tokens)
    if expected != tokens:
        # Text extraction of handwriting is approximate (glyph overlap can merge
        # or split words), so tolerate a tiny mismatch but never lost content.
        if diff["ratio"] < 0.995 or len(diff["missing"]) > max(2, len(expected) // 200):
            errors.append(Issue("PDF_CONTENT_MISMATCH", "text read back from the PDF differs from the document", None, diff))
        else:
            warnings.append(Issue("PDF_TEXT_EXTRACTION", "minor differences reading text back from handwriting glyphs", None, diff))
    ul_expected = sum(1 for p in dl.pages for d in p.decorations if d.kind == "underline")
    if check_strokes and ul_strokes != ul_expected:
        errors.append(Issue("PDF_UNDERLINE_MISMATCH", f"PDF contains {ul_strokes} underline stroke(s); expected {ul_expected}"))
    if n_pages != len(dl.pages):
        errors.append(Issue("PDF_PAGE_COUNT", f"PDF has {n_pages} pages; layout has {len(dl.pages)}"))
    meta = pdf_metadata(pdf)
    for k, v in expected_meta.items():
        if str(meta.get(k)) != str(v):
            errors.append(Issue("PDF_METADATA", f"PDF metadata {k}={meta.get(k)!r}, expected {v!r}"))
    return QualityReport(
        not errors,
        errors,
        warnings,
        {"pdf_tokens": len(tokens), "expected_tokens": len(expected), "text_similarity": diff["ratio"], "underline_strokes": ul_strokes, "pdf_pages": n_pages},
        ["pdf_text", "pdf_underline", "pdf_pages", "pdf_metadata"],
    )
