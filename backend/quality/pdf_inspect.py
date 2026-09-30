"""Inspect a rendered PDF (used by acceptance tests and for debugging).

    python -m backend.quality.pdf_inspect file.pdf   → JSON summary
"""

from __future__ import annotations

import json
import sys

import pymupdf

from backend.handwriting.styles import INKS


def trace_chars(page) -> list[tuple[str, float, float, float]]:
    """(char, x, y, size) for every drawn character in content-stream order
    (the order WriteAI draws: line by line, word by word). Unlike layout-based
    extraction this is robust to rotated/jittered handwriting glyphs."""
    out = []
    for span in page.get_texttrace():
        # Fill+stroke text is traced once per pass: keep fill (0) and invisible (3).
        if span.get("type") not in (0, 3):
            continue
        for c in span["chars"]:
            ch = chr(c[0]) if c[0] > 0 else ""
            out.append((ch, c[2][0], c[2][1], span["size"]))
    return out


def page_lines(page, clip=None) -> list[dict]:
    """Group traced characters into text lines (a new line starts when the
    baseline jumps by more than half a font size)."""
    lines: list[dict] = []
    cur = None
    for ch, x, y, size in trace_chars(page):
        if clip is not None and not (clip.x0 <= x <= clip.x1 and clip.y0 <= y <= clip.y1):
            continue
        if cur is None or abs(y - cur["y"]) > 0.5 * max(size, cur["size"] * 0.8):
            cur = {"y": y, "text": "", "size": size}
            lines.append(cur)
        cur["text"] += ch
        cur["size"] = max(cur["size"], size) if ch.strip() else cur["size"]
    for ln in lines:
        ln["text"] = " ".join(ln["text"].split())
    return [ln for ln in lines if ln["text"]]


def pdf_lines(pdf: bytes) -> list[dict]:
    """Every body text line: page, y (baseline), text, font size."""
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pno, page in enumerate(d, start=1):
            for ln in page_lines(page):
                if "WriteAI" in ln["text"] or ln["text"].startswith("–"):
                    continue
                out.append({"page": pno, "y": round(ln["y"], 2), "text": ln["text"], "size": round(ln["size"], 2)})
    return out


def count_ink_underlines(pdf: bytes) -> int:
    """Horizontal strokes drawn in an ink colour (i.e. underlines)."""
    n = 0
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for page in d:
            for dr in page.get_drawings():
                col = dr.get("color")
                if col and any(max(abs(col[i] - ink[i]) for i in range(3)) < 0.02 for ink in INKS.values()):
                    n += sum(1 for it in dr["items"] if it[0] == "l" and abs(it[1].y - it[2].y) < 3)
    return n


def summary(pdf: bytes) -> dict:
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        meta = d.metadata.get("keywords") or ""
        pages = d.page_count
    return {"pages": pages, "keywords": meta, "underlines": count_ink_underlines(pdf), "lines": pdf_lines(pdf)}


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as fh:
        print(json.dumps(summary(fh.read())))
