"""Deterministic structure builder: labelled segments → section tree.

The tree is the compact, page-annotated representation handed to the LLM and
the RAG chunker, and it is also what Preserve mode converts directly to WDM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Item:
    label: str
    text: str
    page: int


@dataclass
class Section:
    heading: str
    level: int  # 0 = document root, 1 = heading, 2 = subheading
    page: int
    items: list[Item] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

    @property
    def pages(self) -> set[int]:
        ps = {self.page} | {i.page for i in self.items}
        for c in self.children:
            ps |= c.pages
        return ps

    def to_dict(self) -> dict:
        return {
            "heading": self.heading,
            "level": self.level,
            "page": self.page,
            "items": [{"label": i.label, "text": i.text, "page": i.page} for i in self.items],
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class DocumentTree:
    title: str
    root: Section

    def walk(self):
        stack = [(self.root, [])]
        while stack:
            sec, path = stack.pop(0)
            p = path + ([sec.heading] if sec.heading and sec.level > 0 else [])
            yield sec, p
            stack[0:0] = [(c, p) for c in sec.children]

    def to_dict(self) -> dict:
        return {"title": self.title, "root": self.root.to_dict()}

    def to_outline_text(self, max_chars: int = 400_000) -> str:
        """Compact, page-tagged text rendering for LLM prompts."""
        lines: list[str] = [f"TITLE: {self.title}"]
        for sec, _ in self.walk():
            if sec.level > 0:
                lines.append(f"{'#' * sec.level} {sec.heading}  [p.{sec.page}]")
            for it in sec.items:
                lines.append(f"[{it.label} p.{it.page}] {it.text}")
        out = "\n".join(lines)
        return out[:max_chars]


def build_tree(texts: list[str], labels: list[str], pages: list[int], fallback_title: str) -> DocumentTree:
    title = ""
    root = Section(heading="", level=0, page=1)
    current_h1: Section | None = None
    current: Section = root
    for text, label, page in zip(texts, labels, pages):
        if label == "TITLE" and not title:
            title = text
            continue
        if label in ("HEADING", "TITLE"):
            current_h1 = Section(heading=text, level=1, page=page)
            root.children.append(current_h1)
            current = current_h1
        elif label == "SUBHEADING":
            sub = Section(heading=text, level=2, page=page)
            (current_h1 or root).children.append(sub)
            current = sub
        else:
            current.items.append(Item(label=label, text=text, page=page))
    return DocumentTree(title=title or fallback_title, root=root)
