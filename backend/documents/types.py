"""Data types shared by the extraction and NLP stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class TextLine:
    text: str
    page: int  # 1-based
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    font_size: float = 11.0
    is_bold: bool = False
    is_italic: bool = False
    font_name: str = ""
    source: str = "text_layer"  # text_layer | ocr | docx | txt
    style: str | None = None  # DOCX paragraph style name, if any
    ocr_confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractedPage:
    number: int
    width: float
    height: float
    source: str
    lines: list[TextLine] = field(default_factory=list)
    ocr_confidence: float | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


@dataclass
class ExtractedDocument:
    kind: str
    pages: list[ExtractedPage] = field(default_factory=list)

    @property
    def lines(self) -> list[TextLine]:
        return [line for p in self.pages for line in p.lines]

    @property
    def page_count(self) -> int:
        return len(self.pages)
