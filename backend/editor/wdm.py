"""WriteAI Document Model (WDM) — the canonical, structured editable document.

The editor (TipTap) and the renderer both speak this format. It is deliberately
small: every node the editor can create is something the layout engine can
draw, and nothing else is accepted.

    Document
      └─ blocks: heading | paragraph | bullet_list | ordered_list | blockquote
           paragraph/heading.content: text(marks, font_size) | hard_break
           list.items[].blocks: nested blocks (paragraphs, nested lists)
           blockquote.blocks: nested blocks

An empty paragraph (``content == []``) is meaningful — it is how pressing
Enter twice is stored, and it renders as exactly one blank line.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
MAX_TEXT_LEN = 20_000
MAX_BLOCKS = 5_000
MAX_DEPTH = 4

Mark = Literal["bold", "italic", "underline"]
FontSize = Literal["small", "normal", "large", "xlarge"]
Align = Literal["left", "center", "right", "justify"]


def new_block_id() -> str:
    return "b" + uuid.uuid4().hex[:10]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextNode(_Strict):
    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=MAX_TEXT_LEN)
    marks: list[Mark] = Field(default_factory=list)
    font_size: FontSize | None = None

    @field_validator("marks")
    @classmethod
    def _dedupe_marks(cls, v: list[str]) -> list[str]:
        # Canonical order so equal documents hash equally.
        order = ["bold", "italic", "underline"]
        return [m for m in order if m in set(v)]

    @field_validator("text")
    @classmethod
    def _no_control_chars(cls, v: str) -> str:
        # Newlines inside a text node are not allowed: line breaks are either a
        # new paragraph or an explicit hard_break node.
        if "\n" in v or "\r" in v:
            raise ValueError("text nodes must not contain newlines; use hard_break")
        return "".join(ch for ch in v if ch == "\t" or ord(ch) >= 32)


class HardBreakNode(_Strict):
    type: Literal["hard_break"] = "hard_break"


Inline = Annotated[Union[TextNode, HardBreakNode], Field(discriminator="type")]


class Heading(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    type: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=3)
    align: Align = "left"
    content: list[Inline] = Field(default_factory=list)


class Paragraph(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    type: Literal["paragraph"] = "paragraph"
    align: Align = "left"
    content: list[Inline] = Field(default_factory=list)


class ListItem(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    blocks: list["Block"] = Field(min_length=1)


class BulletList(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    type: Literal["bullet_list"] = "bullet_list"
    items: list[ListItem] = Field(min_length=1)


class OrderedList(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    type: Literal["ordered_list"] = "ordered_list"
    start: int = Field(default=1, ge=0, le=10_000)
    items: list[ListItem] = Field(min_length=1)


class Blockquote(_Strict):
    id: str = Field(default_factory=new_block_id, max_length=64)
    type: Literal["blockquote"] = "blockquote"
    blocks: list["Block"] = Field(min_length=1)


Block = Annotated[
    Union[Heading, Paragraph, BulletList, OrderedList, Blockquote], Field(discriminator="type")
]

ListItem.model_rebuild()
Blockquote.model_rebuild()


class WDMDocument(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    title: str = Field(default="Untitled", max_length=300)
    blocks: list[Block] = Field(default_factory=list)

    @model_validator(mode="after")
    def _limits(self) -> "WDMDocument":
        count = 0
        for _, depth in iter_blocks_with_depth(self.blocks):
            count += 1
            if depth > MAX_DEPTH:
                raise ValueError(f"nesting deeper than {MAX_DEPTH} levels is not supported")
        if count > MAX_BLOCKS:
            raise ValueError(f"document has more than {MAX_BLOCKS} blocks")
        return self


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------


def iter_blocks_with_depth(blocks: list, depth: int = 0) -> Iterator[tuple[object, int]]:
    for b in blocks:
        yield b, depth
        if isinstance(b, (BulletList, OrderedList)):
            for item in b.items:
                yield from iter_blocks_with_depth(item.blocks, depth + 1)
        elif isinstance(b, Blockquote):
            yield from iter_blocks_with_depth(b.blocks, depth + 1)


def iter_text_blocks(doc: WDMDocument) -> Iterator[Heading | Paragraph]:
    """Headings and paragraphs in reading order (lists/quotes flattened)."""
    for b, _ in iter_blocks_with_depth(doc.blocks):
        if isinstance(b, (Heading, Paragraph)):
            yield b


def block_plain_text(block: Heading | Paragraph) -> str:
    parts = []
    for node in block.content:
        parts.append(node.text if isinstance(node, TextNode) else "\n")
    return "".join(parts)


def document_tokens(doc: WDMDocument) -> list[str]:
    """Whitespace tokens in reading order — used by the quality checker."""
    tokens: list[str] = []
    for b in iter_text_blocks(doc):
        tokens.extend(block_plain_text(b).split())
    return tokens


def underlined_tokens(doc: WDMDocument) -> list[str]:
    """Tokens (in order) that carry the underline mark, split at run boundaries."""
    out: list[str] = []
    for b in iter_text_blocks(doc):
        for node in b.content:
            if isinstance(node, TextNode) and "underline" in node.marks:
                out.extend(node.text.split())
    return out


def count_empty_paragraphs(doc: WDMDocument) -> int:
    return sum(1 for b in iter_text_blocks(doc) if isinstance(b, Paragraph) and not b.content)


def count_hard_breaks(doc: WDMDocument) -> int:
    return sum(
        1 for b in iter_text_blocks(doc) for n in b.content if isinstance(n, HardBreakNode)
    )


# ---------------------------------------------------------------------------
# Normalisation & hashing
# ---------------------------------------------------------------------------


def _merge_adjacent_text(content: list) -> list:
    merged: list = []
    for node in content:
        if (
            merged
            and isinstance(node, TextNode)
            and isinstance(merged[-1], TextNode)
            and merged[-1].marks == node.marks
            and merged[-1].font_size == node.font_size
        ):
            merged[-1] = TextNode(
                text=merged[-1].text + node.text, marks=node.marks, font_size=node.font_size
            )
        else:
            merged.append(node)
    return merged


def normalize(doc: WDMDocument) -> WDMDocument:
    """Canonicalise without changing meaning.

    * adjacent text runs with identical formatting are merged
    * duplicate block ids are re-assigned (e.g. after a paste)
    * ``font_size == "normal"`` is dropped (it is the default)

    Empty paragraphs and hard breaks are *never* removed.
    """
    seen: set[str] = set()

    def fix_ids(obj) -> None:
        if hasattr(obj, "id"):
            if obj.id in seen or not obj.id:
                obj.id = new_block_id()
            seen.add(obj.id)

    def walk(blocks: list) -> None:
        for b in blocks:
            fix_ids(b)
            if isinstance(b, (Heading, Paragraph)):
                for n in b.content:
                    if isinstance(n, TextNode) and n.font_size == "normal":
                        n.font_size = None
                b.content = _merge_adjacent_text(b.content)
            elif isinstance(b, (BulletList, OrderedList)):
                for item in b.items:
                    fix_ids(item)
                    walk(item.blocks)
            elif isinstance(b, Blockquote):
                walk(b.blocks)

    doc = doc.model_copy(deep=True)
    walk(doc.blocks)
    return doc


def to_canonical_json(doc: WDMDocument) -> str:
    data = doc.model_dump(mode="json", exclude_none=True)
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(doc: WDMDocument) -> str:
    return hashlib.sha256(to_canonical_json(doc).encode("utf-8")).hexdigest()


def parse(data: dict) -> WDMDocument:
    return WDMDocument.model_validate(data)


def dump(doc: WDMDocument) -> dict:
    return doc.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Convenience constructors (used by converters and tests)
# ---------------------------------------------------------------------------


def text(t: str, *marks: str, font_size: str | None = None) -> TextNode:
    return TextNode(text=t, marks=list(marks), font_size=font_size)


def para(*parts: str | TextNode | HardBreakNode, align: str = "left") -> Paragraph:
    content = [TextNode(text=p) if isinstance(p, str) else p for p in parts if p != ""]
    return Paragraph(content=content, align=align)


def heading(level: int, t: str) -> Heading:
    return Heading(level=level, content=[TextNode(text=t)] if t else [])


def bullets(items: list[str]) -> BulletList:
    return BulletList(items=[ListItem(blocks=[para(i)]) for i in items])


def numbered(items: list[str], start: int = 1) -> OrderedList:
    return OrderedList(start=start, items=[ListItem(blocks=[para(i)]) for i in items])
