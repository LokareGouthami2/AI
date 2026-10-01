"""Render settings (validated) and their stable hash."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HandwritingStyle = Literal["neat", "casual", "cursive", "playful", "quick", "light", "ballpoint", "print"]


class RenderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: HandwritingStyle = "quick"
    ink: Literal["blue", "black"] = "blue"
    # "assignment": unruled sheet with a top header line and a left margin
    # line, like loose exam / assignment paper.
    paper: Literal["ruled", "blank", "grid", "assignment"] = "ruled"
    page_size: Literal["A4", "Letter"] = "A4"
    font_size: float = Field(default=16.0, ge=10.0, le=28.0)
    line_spacing: float = Field(default=1.6, ge=1.2, le=3.0)
    paragraph_spacing: int = Field(default=1, ge=0, le=3, description="blank ruled lines after each top-level block")
    margin_top_mm: float = Field(default=22.0, ge=5.0, le=60.0)
    margin_bottom_mm: float = Field(default=20.0, ge=5.0, le=60.0)
    margin_left_mm: float = Field(default=28.0, ge=5.0, le=60.0)
    margin_right_mm: float = Field(default=15.0, ge=5.0, le=60.0)
    page_numbers: bool = True
    page_number_position: Literal["bottom", "top-right"] = "bottom"
    # Written at the top-left of every page, one under the other
    # (e.g. student name and roll / ID number).
    header_name: str = Field(default="", max_length=80)
    header_id: str = Field(default="", max_length=80)
    # Opt-in: a hand-drawn line under every heading. Never on unless the user
    # chooses it (underline marks in the text are a separate, explicit thing).
    underline_headings: bool = False
    # Scanned look only: faint mirrored writing from the back of the sheet.
    show_through: bool = False
    watermark: bool = False  # optional small "Generated with WriteAI" footer
    output: Literal["scanned", "clean"] = "scanned"  # scanned-document look or clean vector PDF
    variation: float = Field(default=1.0, ge=0.0, le=2.0, description="handwriting irregularity multiplier")
    seed: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("header_name", "header_id")
    @classmethod
    def _single_line(cls, v: str) -> str:
        # One printable line: no control characters or line breaks.
        return " ".join("".join(ch for ch in " ".join(v.split()) if ch.isprintable()).split())


def settings_hash(s: RenderSettings) -> str:
    return hashlib.sha256(json.dumps(s.model_dump(), sort_keys=True).encode()).hexdigest()
