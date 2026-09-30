"""Layout engine, handwriting renderer and quality checker."""

import pymupdf
import pytest
from hypothesis import HealthCheck, given
from hypothesis import settings as hsettings
from hypothesis import strategies as st

from backend.editor import wdm
from backend.handwriting.styles import STYLES
from backend.layout.engine import layout
from backend.layout.settings import RenderSettings
from backend.pdf.render import pdf_metadata, render_pdf
from backend.quality.checker import audit_pdf, check_layout
from backend.tests.fixtures.sample_content import ML_CHAPTER


def long_doc(repeat=3) -> wdm.WDMDocument:
    blocks = [wdm.heading(1, "Machine Learning")]
    for lbl, t in ML_CHAPTER * repeat:
        blocks.append(wdm.heading(2, t) if lbl == "HEADING" else wdm.para(t))
    return wdm.WDMDocument(title="x", blocks=blocks)


def test_deterministic():
    d = long_doc(1)
    a = layout(d, RenderSettings(), "h")
    b = layout(d, RenderSettings(), "h")
    assert [(g.ch, round(g.x, 4), round(g.y, 4)) for p in a.pages for g in p.glyphs] == [(g.ch, round(g.x, 4), round(g.y, 4)) for p in b.pages for g in p.glyphs]
    assert render_pdf(a, {"content_hash": "h"}) == render_pdf(b, {"content_hash": "h"})


def test_seed_changes_handwriting_not_content():
    d = long_doc(1)
    a = layout(d, RenderSettings(seed=1))
    b = layout(d, RenderSettings(seed=2))
    assert a.stats["tokens"] == b.stats["tokens"]
    assert [g.y for g in a.pages[0].glyphs] != [g.y for g in b.pages[0].glyphs]


def test_editing_one_paragraph_keeps_other_handwriting_stable():
    d = long_doc(1)
    a = layout(d, RenderSettings())
    d2 = d.model_copy(deep=True)
    d2.blocks[5] = wdm.para("A completely different paragraph.")
    d2.blocks[5].id = d.blocks[5].id
    b = layout(d2, RenderSettings())
    first_a = [(g.ch, g.y - a.pages[0].lines[0].baseline) for g in a.pages[0].glyphs if g.line_id == 0]
    first_b = [(g.ch, g.y - b.pages[0].lines[0].baseline) for g in b.pages[0].glyphs if g.line_id == 0]
    assert first_a == first_b


def test_blank_lines_and_hard_breaks_preserved():
    d = wdm.WDMDocument(blocks=[wdm.para("one"), wdm.Paragraph(), wdm.Paragraph(), wdm.para("two", wdm.HardBreakNode(), "three"), wdm.para("four")])
    dl = layout(d, RenderSettings(paragraph_spacing=0))
    lines = dl.pages[0].lines
    assert [ln.kind for ln in lines] == ["text", "blank", "blank", "text", "text", "text"]
    assert [ln.text for ln in lines if ln.kind == "text"] == ["one", "two", "three", "four"]
    # consecutive slots: blank lines occupy exactly one grid line each
    assert [ln.slot for ln in lines] == [0, 1, 2, 3, 4, 5]


def test_trailing_blank_lines_do_not_create_pages():
    d = wdm.WDMDocument(blocks=[wdm.para("x")] + [wdm.Paragraph() for _ in range(200)])
    dl = layout(d, RenderSettings())
    assert len(dl.pages) == 1 and dl.stats["trimmed_trailing_blank"] == 200
    assert check_layout(d, dl).passed


def test_pagination_and_orphan_headings():
    d = long_doc(4)
    dl = layout(d, RenderSettings())
    assert len(dl.pages) > 3
    r = check_layout(d, dl)
    assert r.passed, r.to_dict()["errors"]
    for p in dl.pages[:-1]:
        content = [ln for ln in p.lines if ln.kind != "blank"]
        assert content[-1].kind != "heading"


def test_underline_only_where_marked():
    d = wdm.WDMDocument(blocks=[wdm.heading(1, "Heading"), wdm.para("plain ", wdm.text("marked words", "underline"), " plain again")])
    dl = layout(d, RenderSettings())
    ul = [x for p in dl.pages for x in p.decorations if x.kind == "underline"]
    assert len(ul) == 1
    underlined = [g.ch for g in dl.pages[0].glyphs if g.underline]
    assert "".join(underlined) == "markedwords"
    # Headings and AI-style content get no underline at all.
    d2 = wdm.WDMDocument(blocks=[wdm.heading(1, "Heading"), wdm.heading(2, "Sub"), wdm.para("Definition: text.")])
    dl2 = layout(d2, RenderSettings())
    assert not [x for p in dl2.pages for x in p.decorations if x.kind == "underline"]


def test_lists_have_markers_and_indent():
    d = wdm.WDMDocument(blocks=[wdm.numbered(["Supervised", "Unsupervised", "Reinforcement"]), wdm.bullets(["a"])])
    dl = layout(d, RenderSettings())
    markers = "".join(g.ch for g in dl.pages[0].glyphs if g.marker)
    assert markers == "1.2.3.•"
    text_x = min(g.x for g in dl.pages[0].glyphs if not g.marker)
    assert text_x > dl.box[0] + 10  # indented


@pytest.mark.parametrize("align", ["center", "right"])
def test_alignment(align):
    d = wdm.WDMDocument(blocks=[wdm.para("short line", align=align)])
    dl = layout(d, RenderSettings())
    ln = dl.pages[0].lines[0]
    mid = (dl.box[0] + dl.box[2]) / 2
    if align == "center":
        assert abs((ln.x0 + ln.x1) / 2 - mid) < 2
    else:
        assert abs(ln.x1 - dl.box[2]) < 2


def test_long_word_is_force_broken_without_overflow():
    d = wdm.WDMDocument(blocks=[wdm.para("x" * 400)])
    dl = layout(d, RenderSettings())
    assert len(dl.pages[0].lines) > 1
    r = check_layout(d, dl)
    assert not [e for e in r.errors if e.code == "OVERFLOW"]


@pytest.mark.parametrize("style", list(STYLES))
@pytest.mark.parametrize("paper", ["ruled", "blank", "grid"])
def test_all_styles_pass_quality_and_pdf_audit(style, paper):
    d = long_doc(1)
    s = RenderSettings(style=style, paper=paper, ink="black" if paper == "grid" else "blue")
    dl = layout(d, s, "hash")
    r = check_layout(d, dl)
    assert r.passed, r.to_dict()["errors"]
    pdf = render_pdf(dl, {"content_hash": "hash"})
    a = audit_pdf(d, dl, pdf, {"content_hash": "hash"})
    assert a.passed, a.to_dict()["errors"]


def test_pdf_metadata_and_page_numbers():
    d = long_doc(2)
    dl = layout(d, RenderSettings())
    pdf = render_pdf(dl, {"content_hash": "abc", "revision": 7})
    assert pdf_metadata(pdf) == {"content_hash": "abc", "revision": "7"}
    with pymupdf.open(stream=pdf) as doc:
        assert doc.page_count == len(dl.pages)
        assert "– 2 –" in doc[1].get_text()


# ------------------------------------------------------------ quality checker


def test_checker_detects_corruption():
    d = long_doc(1)
    dl = layout(d, RenderSettings())
    dl.pages[0].glyphs[0].x = -50  # pushed off the page
    dl.stats["tokens"] = dl.stats["tokens"][:-3]  # content lost
    dl.stats["blank_lines"] += 1
    codes = {e.code for e in check_layout(d, dl).errors}
    assert {"OVERFLOW", "CONTENT_MISMATCH", "BLANK_LINES"} <= codes


def test_checker_detects_unwanted_underline():
    from backend.layout.engine import Decoration

    d = long_doc(1)
    dl = layout(d, RenderSettings())
    g = dl.pages[0].glyphs[5]
    dl.pages[0].decorations.append(Decoration("underline", g.x, g.y - 2, g.x + 20, g.y - 2, 1.0, g.line_id))
    codes = {e.code for e in check_layout(d, dl).errors}
    assert "UNWANTED_UNDERLINE" in codes


def test_checker_detects_overlap_and_empty_page():
    d = long_doc(1)
    dl = layout(d, RenderSettings())
    lines = dl.pages[0].lines
    a, b = lines[2], lines[3]
    for g in dl.pages[0].glyphs:
        if g.line_id == b.id:
            g.y = a.baseline  # stack two lines on top of each other
    from backend.layout.engine import PageOut

    dl.pages.append(PageOut(len(dl.pages) + 1))
    codes = {e.code for e in check_layout(d, dl).errors}
    assert {"OVERLAP", "EMPTY_PAGE"} <= codes


def test_pdf_audit_detects_wrong_document():
    d = long_doc(1)
    dl = layout(d, RenderSettings())
    pdf = render_pdf(dl, {"content_hash": "h"})
    other = wdm.WDMDocument(blocks=[wdm.para("Something else entirely")])
    a = audit_pdf(other, dl, pdf, {"content_hash": "different"})
    codes = {e.code for e in a.errors}
    assert {"PDF_CONTENT_MISMATCH", "PDF_METADATA"} <= codes


# --------------------------------------------------------- property-based

words = st.text(alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), max_codepoint=0x24F), min_size=1, max_size=18)


@st.composite
def random_docs(draw):
    blocks = []
    for _ in range(draw(st.integers(1, 25))):
        kind = draw(st.sampled_from(["p", "p", "p", "h", "empty", "list", "quote", "break"]))
        if kind == "p":
            n = draw(st.integers(1, 60))
            ws = draw(st.lists(words, min_size=n, max_size=n))
            marks = draw(st.sampled_from([[], ["bold"], ["italic"], ["underline"], ["bold", "underline"]]))
            blocks.append(wdm.Paragraph(content=[wdm.TextNode(text=" ".join(ws), marks=marks)], align=draw(st.sampled_from(["left", "center", "right", "justify"]))))
        elif kind == "h":
            blocks.append(wdm.heading(draw(st.integers(1, 3)), " ".join(draw(st.lists(words, min_size=1, max_size=8)))))
        elif kind == "empty":
            blocks.append(wdm.Paragraph())
        elif kind == "list":
            blocks.append(wdm.bullets([" ".join(draw(st.lists(words, min_size=1, max_size=20))) for _ in range(draw(st.integers(1, 4)))]))
        elif kind == "quote":
            blocks.append(wdm.Blockquote(blocks=[wdm.para(" ".join(draw(st.lists(words, min_size=1, max_size=30))))]))
        else:
            blocks.append(wdm.para(draw(words), wdm.HardBreakNode(), draw(words)))
    # Deterministic ids: handwriting variation is seeded by block id, so
    # random uuids would make Hypothesis replays non-reproducible.
    for i, (b, _) in enumerate(wdm.iter_blocks_with_depth(blocks)):
        b.id = f"blk{i}"
        for j, item in enumerate(getattr(b, "items", [])):
            item.id = f"blk{i}-item{j}"
    return wdm.WDMDocument(blocks=blocks)


@hsettings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(doc=random_docs(), style=st.sampled_from(list(STYLES)), size=st.sampled_from([12.0, 16.0, 22.0]), spacing=st.sampled_from([1.3, 1.6, 2.0]))
def test_property_layout_never_overflows_overlaps_or_loses_content(doc, style, size, spacing):
    dl = layout(doc, RenderSettings(style=style, font_size=size, line_spacing=spacing))
    report = check_layout(doc, dl)
    blocking = [e for e in report.errors if e.code != "EMPTY_PAGE"]
    assert not blocking, report.to_dict()["errors"]
    assert dl.stats["tokens"] == wdm.document_tokens(doc)


def test_regression_collision_near_page_bottom_moves_line_to_next_page():
    """Found by the property test: tall accented glyphs colliding with the line
    above at the bottom of a page must push the line to the next page."""
    tall = "ƸËȦŉĺŵ2ſXĜšÈzbÌWĘÄ řȄì bŵĻǶīƋÉ ǺǼǾȀȂ ŉſŉſ ÅÊÎÔÛ"
    for style in STYLES:
        for spacing in (1.3, 1.6):
            blocks = [wdm.para(tall) for _ in range(120)]
            d = wdm.WDMDocument(blocks=blocks)
            dl = layout(d, RenderSettings(style=style, line_spacing=spacing, paragraph_spacing=0))
            r = check_layout(d, dl)
            assert not [e for e in r.errors if e.code in ("OVERLAP", "OVERFLOW")], (style, spacing, r.to_dict()["errors"][:2])
