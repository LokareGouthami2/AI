"""Render settings (validated) and their stable hash."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HandwritingStyle = Literal["neat", "casual", "cursive", "playful", "quick", "light"]


class RenderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: HandwritingStyle = "neat"
    ink: Literal["blue", "black"] = "blue"
    paper: Literal["ruled", "blank", "grid"] = "ruled"
    page_size: Literal["A4", "Letter"] = "A4"
    font_size: float = Field(default=16.0, ge=10.0, le=28.0)
    line_spacing: float = Field(default=1.6, ge=1.2, le=3.0)
    paragraph_spacing: int = Field(default=1, ge=0, le=3, description="blank ruled lines after each top-level block")
    margin_top_mm: float = Field(default=22.0, ge=5.0, le=60.0)
    margin_bottom_mm: float = Field(default=20.0, ge=5.0, le=60.0)
    margin_left_mm: float = Field(default=28.0, ge=5.0, le=60.0)
    margin_right_mm: float = Field(default=15.0, ge=5.0, le=60.0)
    page_numbers: bool = True
    watermark: bool = True
    variation: float = Field(default=1.0, ge=0.0, le=2.0, description="handwriting irregularity multiplier")
    seed: int = Field(default=0, ge=0, le=1_000_000)


def settings_hash(s: RenderSettings) -> str:
    return hashlib.sha256(json.dumps(s.model_dump(), sort_keys=True).encode()).hexdigest()
