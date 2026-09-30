import pytest
from pydantic import ValidationError

from backend.editor import wdm
from backend.editor.diff import diff_documents


def sample() -> wdm.WDMDocument:
    return wdm.WDMDocument(
        title="ML",
        blocks=[
            wdm.heading(1, "Introduction"),
            wdm.para("Machine learning is ", wdm.text("great", "bold"), "."),
            wdm.Paragraph(),  # Enter pressed twice
            wdm.para("line a", wdm.HardBreakNode(), "line b"),
            wdm.numbered(["Supervised", "Unsupervised"]),
        ],
    )


def test_roundtrip_json():
    d = sample()
    again = wdm.parse(wdm.dump(d))
    assert wdm.content_hash(again) == wdm.content_hash(d)


def test_empty_paragraph_is_preserved_by_normalize():
    d = wdm.normalize(sample())
    assert wdm.count_empty_paragraphs(d) == 1
    assert wdm.count_hard_breaks(d) == 1


def test_normalize_merges_adjacent_runs_and_fixes_duplicate_ids():
    p1 = wdm.para("a", "b")
    p2 = wdm.para("c")
    p2.id = p1.id
    d = wdm.normalize(wdm.WDMDocument(blocks=[p1, p2]))
    assert len(d.blocks[0].content) == 1 and d.blocks[0].content[0].text == "ab"
    assert d.blocks[0].id != d.blocks[1].id


def test_marks_are_canonical_and_unknown_marks_rejected():
    t = wdm.TextNode(text="x", marks=["underline", "bold", "bold"])
    assert t.marks == ["bold", "underline"]
    with pytest.raises(ValidationError):
        wdm.TextNode(text="x", marks=["highlight"])


def test_newlines_inside_text_rejected():
    with pytest.raises(ValidationError):
        wdm.TextNode(text="a\nb")


def test_unknown_fields_and_block_types_rejected():
    with pytest.raises(ValidationError):
        wdm.parse({"blocks": [{"type": "image", "src": "x"}]})
    with pytest.raises(ValidationError):
        wdm.parse({"blocks": [{"type": "paragraph", "content": [], "style": "evil"}]})


def test_nesting_limit():
    inner = wdm.bullets(["x"])
    for _ in range(6):
        inner = wdm.BulletList(items=[wdm.ListItem(blocks=[inner])])
    with pytest.raises(ValidationError):
        wdm.WDMDocument(blocks=[inner])


def test_tokens_in_reading_order():
    assert wdm.document_tokens(sample()) == ["Introduction", "Machine", "learning", "is", "great.", "line", "a", "line", "b", "Supervised", "Unsupervised"]


def test_hash_changes_with_content_not_with_equivalent_runs():
    a = wdm.WDMDocument(blocks=[wdm.para("ab")])
    b = wdm.normalize(wdm.WDMDocument(blocks=[wdm.para("a", "b")]))
    b.blocks[0].id = a.blocks[0].id
    assert wdm.content_hash(a) == wdm.content_hash(b)
    c = wdm.WDMDocument(blocks=[wdm.para("abc")])
    c.blocks[0].id = a.blocks[0].id
    assert wdm.content_hash(a) != wdm.content_hash(c)


def test_diff_reports_changes():
    a = sample()
    b = a.model_copy(deep=True)
    b.blocks.pop(1)
    b.blocks.append(wdm.para("new paragraph"))
    d = diff_documents(a, b)
    assert d["removed"] >= 1 and d["added"] >= 1
