"""Block-level diff between two WDM documents (used by version history)."""

from __future__ import annotations

import difflib

from backend.editor.wdm import (
    BulletList,
    Heading,
    OrderedList,
    Paragraph,
    WDMDocument,
    block_plain_text,
    iter_blocks_with_depth,
)


def _lines(doc: WDMDocument) -> list[str]:
    out: list[str] = []
    for b, depth in iter_blocks_with_depth(doc.blocks):
        pad = "  " * depth
        if isinstance(b, Heading):
            out.append(f"{pad}{'#' * b.level} {block_plain_text(b)}")
        elif isinstance(b, Paragraph):
            out.append(f"{pad}{block_plain_text(b)}")
        elif isinstance(b, (BulletList, OrderedList)):
            out.append(f"{pad}[{b.type}]")
        else:
            out.append(f"{pad}[{b.type}]")
    return out


def diff_documents(old: WDMDocument, new: WDMDocument) -> dict:
    a, b = _lines(old), _lines(new)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        ops.append({"op": tag, "old": a[i1:i2], "new": b[j1:j2]})
    return {
        "changes": ops,
        "added": sum(len(o["new"]) for o in ops if o["op"] in ("insert", "replace")),
        "removed": sum(len(o["old"]) for o in ops if o["op"] in ("delete", "replace")),
    }
