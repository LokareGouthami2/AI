"""Inspect a rendered PDF (used by acceptance tests and for debugging).

    python -m backend.quality.pdf_inspect file.pdf   → JSON summary
"""

from __future__ import annotations

import json
import sys

import pymupdf

from backend.handwriting.styles import INKS


def pdf_lines(pdf: bytes) -> list[dict]:
    """Every text line in the body: page, y (top), text, max font size."""
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        for pno, page in enumerate(d, start=1):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(s["text"] for s in line["spans"]).strip()
                    if text and "WriteAI" not in text and not text.startswith("–"):
                        out.append({"page": pno, "y": round(line["bbox"][1], 2), "text": text, "size": round(max(s["size"] for s in line["spans"]), 2)})
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
