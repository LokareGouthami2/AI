"""Output schemas for every LLM task.

These are the ONLY shapes the LLM may return. They contain plain strings — no
markdown, HTML or formatting marks — so AI output cannot introduce underline,
highlighting or any other styling into the editor.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["easy", "medium", "hard"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoteBlock(_M):
    type: Literal["paragraph", "bullets", "numbered", "definition", "example", "formula", "key_point", "quote"]
    text: str = Field(default="", description="Plain text for paragraph/definition/example/formula/key_point/quote")
    term: str = Field(default="", description="Only for type=definition: the term being defined")
    items: list[str] = Field(default_factory=list, description="Only for bullets/numbered: one plain-text item per entry")


class NoteSection(_M):
    heading: str
    level: Literal[1, 2] = 1
    blocks: list[NoteBlock]
    source_pages: list[int] = Field(default_factory=list)


class NotesOutput(_M):
    title: str
    sections: list[NoteSection]


class AssignmentOutput(_M):
    title: str
    introduction: str
    objectives: list[str]
    main_sections: list[NoteSection]
    examples: list[str]
    conclusion: str
    references: list[str]


class ExamDefinition(_M):
    term: str
    definition: str
    source_pages: list[int] = Field(default_factory=list)


class ExamFormula(_M):
    name: str
    expression: str
    meaning: str


class ExamOutput(_M):
    title: str
    definitions: list[ExamDefinition]
    formulas: list[ExamFormula]
    key_concepts: list[str]
    important_questions: list[str]


class Flashcard(_M):
    question: str
    answer: str
    difficulty: Difficulty = "medium"
    source_pages: list[int] = Field(default_factory=list)


class FlashcardsOutput(_M):
    cards: list[Flashcard]


class QuizQuestion(_M):
    question: str
    options: list[str] = Field(description="Exactly four answer options")
    correct_index: int = Field(description="0-based index of the correct option")
    explanation: str
    difficulty: Difficulty = "medium"
    source_pages: list[int] = Field(default_factory=list)


class QuizOutput(_M):
    questions: list[QuizQuestion]


class RagAnswer(_M):
    answer: str | None = Field(description="Answer using ONLY the provided chunks, or null if they do not contain it")
    citations: list[str] = Field(description="ids of the chunks that support the answer, e.g. ['c2']")
    confidence: Literal["low", "medium", "high"] = "medium"
