"""Convert validated AI outputs (and the Preserve-mode tree) into WDM.

This is the only path from AI output into the editor. It emits plain text
nodes only: no marks (so no underline / highlighting), headings are
distinguished purely by block type.
"""

from __future__ import annotations

import re

from backend.editor.wdm import (
    Block,
    HardBreakNode,
    Heading,
    Paragraph,
    TextNode,
    WDMDocument,
    bullets,
    heading,
    normalize,
    numbered,
)
from backend.llm.schemas import AssignmentOutput, ExamOutput, NoteBlock, NoteSection, NotesOutput
from backend.nlp.structure import DocumentTree

_MD = [
    (re.compile(r"</?[a-zA-Z][^>]{0,40}>"), ""),  # any HTML tag incl. <u>, <mark>
    (re.compile(r"\*\*([^*\s][^*]*?)\*\*"), r"\1"),
    (re.compile(r"__([^_\s][^_]*?)__"), r"\1"),
    (re.compile(r"(?<![\w*])\*([A-Za-z0-9][^*]*?[A-Za-z0-9.]|[A-Za-z0-9])\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])_([A-Za-z0-9][^_]*?[A-Za-z0-9.]|[A-Za-z0-9])_(?![\w_])"), r"\1"),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"^\s{0,3}#{1,6}\s+"), ""),
    (re.compile(r"^\s*[-*+]\s+"), ""),
]


def clean_text(text: str) -> str:
    """Strip markdown/HTML formatting an LLM might emit anyway; collapse whitespace."""
    t = text or ""
    for pat, rep in _MD:
        t = pat.sub(rep, t)
    t = t.replace("\r", "")
    return re.sub(r"[ \t]+", " ", t).strip()


def _para_from_text(text: str) -> Paragraph | None:
    """Paragraph; internal newlines become hard breaks (never lost)."""
    lines = [clean_text(line) for line in (text or "").split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None
    content: list = []
    for i, ln in enumerate(lines):
        if i:
            content.append(HardBreakNode())
        content.append(TextNode(text=ln))
    return Paragraph(content=content)


def _note_block(b: NoteBlock) -> list[Block]:
    if b.type in ("bullets", "numbered"):
        items = [clean_text(i) for i in b.items if clean_text(i)]
        if not items:
            p = _para_from_text(b.text)
            return [p] if p else []
        return [bullets(items) if b.type == "bullets" else numbered(items)]
    text = clean_text(b.text)
    if b.type == "definition":
        term = clean_text(b.term)
        if term and text:
            return [Paragraph(content=[TextNode(text=f"{term}: {text}")])]
    elif b.type == "example" and text and not re.match(r"^(example|e\.g\.)", text, re.I):
        text = f"Example: {text}"
    elif b.type == "key_point" and text and not re.match(r"^(important|note|key point|remember)", text, re.I):
        text = f"Key point: {text}"
    elif b.type == "formula" and text:
        return [Paragraph(content=[TextNode(text=text)], align="center")]
    p = _para_from_text(text)
    return [p] if p else []


def _sections_to_blocks(sections: list[NoteSection], base_level: int = 2) -> list[Block]:
    out: list[Block] = []
    for sec in sections:
        h = clean_text(sec.heading)
        if h:
            out.append(heading(min(base_level + sec.level - 1, 3), h))
        for b in sec.blocks:
            out.extend(_note_block(b))
    return out


def notes_to_wdm(o: NotesOutput) -> WDMDocument:
    title = clean_text(o.title) or "Notes"
    blocks: list[Block] = [heading(1, title)] + _sections_to_blocks(o.sections)
    return normalize(WDMDocument(title=title, blocks=blocks))


def assignment_to_wdm(o: AssignmentOutput) -> WDMDocument:
    title = clean_text(o.title) or "Assignment"
    b: list[Block] = [heading(1, title), heading(2, "Introduction")]
    b += [p for p in [_para_from_text(o.introduction)] if p]
    objectives = [clean_text(x) for x in o.objectives if clean_text(x)]
    if objectives:
        b += [heading(2, "Objectives"), numbered(objectives)]
    b += _sections_to_blocks(o.main_sections)
    examples = [clean_text(x) for x in o.examples if clean_text(x)]
    if examples:
        b.append(heading(2, "Examples"))
        b += [Paragraph(content=[TextNode(text=e)]) for e in examples]
    if clean_text(o.conclusion):
        b += [heading(2, "Conclusion"), _para_from_text(o.conclusion)]
    refs = [clean_text(x) for x in o.references if clean_text(x)]
    if refs:
        b += [heading(2, "References")] + [Paragraph(content=[TextNode(text=r)]) for r in refs]
    return normalize(WDMDocument(title=title, blocks=[x for x in b if x is not None]))


def exam_to_wdm(o: ExamOutput) -> WDMDocument:
    title = clean_text(o.title) or "Exam Revision"
    b: list[Block] = [heading(1, title)]
    defs = [(clean_text(d.term), clean_text(d.definition)) for d in o.definitions]
    defs = [(t, d) for t, d in defs if t and d]
    if defs:
        b.append(heading(2, "Key Definitions"))
        b += [Paragraph(content=[TextNode(text=f"{t}: {d}")]) for t, d in defs]
    forms = [f for f in o.formulas if clean_text(f.expression)]
    if forms:
        b.append(heading(2, "Formulas"))
        for f in forms:
            b.append(Paragraph(content=[TextNode(text=clean_text(f.expression))], align="center"))
            if clean_text(f.meaning):
                b.append(Paragraph(content=[TextNode(text=clean_text(f.meaning))]))
    concepts = [clean_text(c) for c in o.key_concepts if clean_text(c)]
    if concepts:
        b += [heading(2, "Key Concepts"), bullets(concepts)]
    qs = [clean_text(q) for q in o.important_questions if clean_text(q)]
    if qs:
        b += [heading(2, "Important Questions"), numbered(qs)]
    return normalize(WDMDocument(title=title, blocks=b))


_BULLET_PREFIX = re.compile(r"^\s*[•●▪◦\-–*]\s+")


def tree_to_wdm(tree: DocumentTree) -> WDMDocument:
    """PRESERVE mode: deterministic, no LLM. Keeps source text and order."""
    b: list[Block] = [heading(1, tree.title)]
    pending_bullets: list[str] = []

    def flush():
        if pending_bullets:
            b.append(bullets(list(pending_bullets)))
            pending_bullets.clear()

    for sec, _ in tree.walk():
        if sec.level > 0:
            flush()
            b.append(heading(2 if sec.level == 1 else 3, sec.heading))
        for it in sec.items:
            if _BULLET_PREFIX.match(it.text):
                pending_bullets.append(_BULLET_PREFIX.sub("", it.text))
                continue
            flush()
            p = Paragraph(content=[TextNode(text=it.text)], align="center" if it.label == "FORMULA" else "left")
            b.append(p)
    flush()
    return normalize(WDMDocument(title=tree.title, blocks=b))


def is_heading(b) -> bool:
    return isinstance(b, Heading)
