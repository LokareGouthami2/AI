"""Structure-aware chunking.

Chunks never cross a section boundary. Within a section, sentences are packed
up to ~TARGET tokens with ~OVERLAP tokens of sentence overlap. Formulas and
list items are never split (they are single units).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.nlp.stats import split_sentences
from backend.nlp.structure import DocumentTree

TARGET_TOKENS = 350
OVERLAP_TOKENS = 50


@dataclass
class ChunkSpec:
    order_index: int
    text: str
    section_path: str
    page_start: int
    page_end: int
    token_count: int


def _units(tree: DocumentTree):
    """Yield (section_path, text, page) sentence-level units in reading order."""
    for sec, path in tree.walk():
        section_path = " > ".join(path)
        heading_prefix = f"{path[-1]}: " if path else ""
        for it in sec.items:
            if it.label in ("FORMULA", "REFERENCE", "QUESTION", "ANSWER"):
                yield section_path, it.text, it.page, heading_prefix
            else:
                for s in split_sentences(it.text):
                    yield section_path, s, it.page, heading_prefix


def chunk_tree(tree: DocumentTree, target: int = TARGET_TOKENS, overlap: int = OVERLAP_TOKENS) -> list[ChunkSpec]:
    chunks: list[ChunkSpec] = []
    cur: list[tuple[str, int]] = []
    cur_path = None
    cur_prefix = ""

    def ntok(t: str) -> int:
        return len(t.split())

    def emit():
        if not cur:
            return
        body = " ".join(t for t, _ in cur)
        text = (cur_prefix + body) if cur_prefix and not body.startswith(cur_prefix.rstrip(": ")) else body
        pages = [p for _, p in cur]
        chunks.append(ChunkSpec(len(chunks), text, cur_path or "", min(pages), max(pages), ntok(text)))

    for path, sent, page, prefix in _units(tree):
        if path != cur_path:
            emit()
            cur, cur_path, cur_prefix = [], path, prefix
        if cur and sum(ntok(t) for t, _ in cur) + ntok(sent) > target:
            emit()
            # sentence overlap: carry trailing sentences up to `overlap` tokens
            carry, total = [], 0
            for t, p in reversed(cur):
                if total + ntok(t) > overlap:
                    break
                carry.insert(0, (t, p))
                total += ntok(t)
            cur = carry
        cur.append((sent, page))
    emit()
    return chunks
