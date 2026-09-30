"""Request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.layout.settings import RenderSettings

Mode = Literal["preserve", "clean", "smart", "assignment", "exam", "simple"]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_name: str
    kind: str
    size_bytes: int
    page_count: int
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    has_content: bool = False
    revision: int | None = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str | None
    kind: str
    status: str
    progress: float
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class GenerateRequest(BaseModel):
    mode: Mode = "smart"


class ContentOut(BaseModel):
    document_id: str
    revision: int
    content_hash: str
    content: dict
    updated_at: datetime


class ContentSaveRequest(BaseModel):
    content: dict
    base_revision: int = Field(ge=0)
    force: bool = False


class ContentSaveOut(BaseModel):
    revision: int
    content_hash: str
    updated_at: datetime
    version_created: int | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    revision: int
    content_hash: str
    source: str
    label: str | None
    created_at: datetime


class VersionCreate(BaseModel):
    label: str | None = Field(default=None, max_length=200)


class RenderRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    settings: RenderSettings | None = None
    pages: list[int] | None = Field(default=None, max_length=50)


class PreviewOut(BaseModel):
    render_id: str
    revision: int
    content_hash: str
    page_count: int
    pages: list[dict]
    quality: dict


class RenderOut(BaseModel):
    render_id: str
    status: str
    revision: int
    content_hash: str
    page_count: int
    quality: dict
    download_url: str | None


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


class Citation(BaseModel):
    chunk_id: str
    pages: list[int]
    section: str
    excerpt: str


class AskOut(BaseModel):
    answer: str | None
    grounded: bool
    confidence: str
    citations: list[Citation]
    provider: str
    status: str


class StudyGenerateRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)


class FlashcardIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=3000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    source_pages: list[int] = Field(default_factory=list)


class FlashcardSetOut(BaseModel):
    id: str
    cards: list[dict]
    provider: str | None = None
    status: str | None = None
    updated_at: datetime


class FlashcardSaveRequest(BaseModel):
    cards: list[FlashcardIn] = Field(max_length=200)


class QuizQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(default="", max_length=2000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    source_pages: list[int] = Field(default_factory=list)


class QuizOut(BaseModel):
    id: str
    questions: list[dict]
    provider: str | None = None
    status: str | None = None
    updated_at: datetime


class QuizSaveRequest(BaseModel):
    questions: list[QuizQuestionIn] = Field(max_length=100)
