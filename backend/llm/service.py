"""LLM orchestration: prompt → provider → validation → repair → fallback.

Every public function returns validated, safe objects. If the LLM output is
malformed after one repair attempt, the deterministic offline engine's output
is used instead, and the result is marked ``status="fallback"``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from backend.editor import from_llm
from backend.editor.wdm import WDMDocument
from backend.llm import prompts
from backend.llm.provider import (
    AnthropicProvider,
    ExtractiveProvider,
    LLMError,
    LLMProvider,
    LLMResult,
    TaskRequest,
    get_provider,
)
from backend.llm.schemas import (
    AssignmentOutput,
    ExamOutput,
    FlashcardsOutput,
    NotesOutput,
    QuizOutput,
    RagAnswer,
)
from backend.nlp.structure import DocumentTree

log = logging.getLogger(__name__)

MODES = ("preserve", "clean", "smart", "assignment", "exam", "simple")
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "clean": NotesOutput,
    "smart": NotesOutput,
    "simple": NotesOutput,
    "assignment": AssignmentOutput,
    "exam": ExamOutput,
    "flashcards": FlashcardsOutput,
    "quiz": QuizOutput,
}
MAP_REDUCE_CHARS = 60_000


@dataclass
class GenerationMeta:
    provider: str
    model: str
    status: str  # ok | repaired | fallback
    input_tokens: int = 0
    output_tokens: int = 0
    notes: str | None = None
    output_json: dict | None = None


# ---------------------------------------------------------------------------
# Semantic validation (beyond the JSON schema)
# ---------------------------------------------------------------------------


def _valid_pages(pages: list[int], page_count: int) -> list[int]:
    return sorted({p for p in pages if isinstance(p, int) and 1 <= p <= page_count})


def validate_output(task: str, out: BaseModel, page_count: int) -> tuple[BaseModel, list[str]]:
    """Return a sanitised copy plus a list of *fatal* problems."""
    errors: list[str] = []
    out = out.model_copy(deep=True)
    if isinstance(out, NotesOutput):
        for s in out.sections:
            s.source_pages = _valid_pages(s.source_pages, page_count)
        out.sections = [s for s in out.sections if s.heading.strip() or s.blocks]
        if not out.sections:
            errors.append("sections must not be empty")
    elif isinstance(out, AssignmentOutput):
        if not out.introduction.strip():
            errors.append("introduction must not be empty")
        if not out.main_sections:
            errors.append("main_sections must not be empty")
    elif isinstance(out, ExamOutput):
        for d in out.definitions:
            d.source_pages = _valid_pages(d.source_pages, page_count)
        if not (out.definitions or out.key_concepts or out.important_questions):
            errors.append("exam output is empty")
    elif isinstance(out, FlashcardsOutput):
        seen, cards = set(), []
        for c in out.cards:
            c.question, c.answer = from_llm.clean_text(c.question), from_llm.clean_text(c.answer)
            c.source_pages = _valid_pages(c.source_pages, page_count)
            if c.question and c.answer and c.question.lower() not in seen:
                seen.add(c.question.lower())
                cards.append(c)
        out.cards = cards
    elif isinstance(out, QuizOutput):
        good = []
        for i, q in enumerate(out.questions):
            q.question = from_llm.clean_text(q.question)
            q.options = [from_llm.clean_text(o) for o in q.options]
            q.explanation = from_llm.clean_text(q.explanation)
            q.source_pages = _valid_pages(q.source_pages, page_count)
            problems = []
            if len(q.options) != 4:
                problems.append(f"question {i + 1} must have exactly 4 options (has {len(q.options)})")
            elif len({o.lower() for o in q.options}) != 4 or not all(q.options):
                problems.append(f"question {i + 1} options must be 4 distinct non-empty strings")
            if not 0 <= q.correct_index <= 3:
                problems.append(f"question {i + 1} correct_index must be 0-3")
            if not q.question:
                problems.append(f"question {i + 1} is empty")
            if problems:
                errors.extend(problems)
            else:
                good.append(q)
        out.questions = good
    return out, errors


# ---------------------------------------------------------------------------
# Core call with repair + fallback
# ---------------------------------------------------------------------------


def _call(provider: LLMProvider, req: TaskRequest, page_count: int) -> tuple[BaseModel, GenerationMeta]:
    offline = ExtractiveProvider()
    if isinstance(provider, ExtractiveProvider):
        res = provider.generate(req)
        out, errs = validate_output(req.task, res.output, page_count)
        return out, GenerationMeta(provider.name, provider.model, "ok", notes="; ".join(errs) or None)

    status = "ok"
    tokens_in = tokens_out = 0
    try:
        res: LLMResult = provider.generate(req)
        tokens_in, tokens_out = res.input_tokens, res.output_tokens
        errors = [res.error] if res.error else []
        out = res.output
        if out is not None:
            out, errors = validate_output(req.task, out, page_count)
        if errors and isinstance(provider, AnthropicProvider):
            log.warning("LLM output invalid (%s); attempting one repair", errors)
            repair = [
                {"role": "assistant", "content": res.raw or "{}"},
                {"role": "user", "content": prompts.REPAIR_TEMPLATE.format(errors="\n".join(f"- {e}" for e in errors), previous=(res.raw or "")[:20000])},
            ]
            res2 = provider.generate(req, repair_messages=repair)
            tokens_in += res2.input_tokens
            tokens_out += res2.output_tokens
            if res2.output is not None:
                out, errors = validate_output(req.task, res2.output, page_count)
                status = "repaired"
            else:
                errors = [res2.error or "repair failed"]
        if out is None or errors:
            raise LLMError("; ".join(errors) or "no output")
        return out, GenerationMeta(provider.name, provider.model, status, tokens_in, tokens_out)
    except (LLMError, ValidationError) as exc:
        log.warning("falling back to offline engine: %s", exc)
        res = offline.generate(req)
        out, _ = validate_output(req.task, res.output, page_count)
        return out, GenerationMeta(provider.name, provider.model, "fallback", tokens_in, tokens_out, notes=str(exc)[:500])


def _request(task: str, tree: DocumentTree, outline: str, **ctx) -> TaskRequest:
    instr = prompts.MODE_INSTRUCTIONS[task].format(count=ctx.get("count", 10))
    user = f"{instr}\n\n{prompts.document_block(outline)}"
    return TaskRequest(task=task, system=prompts.SYSTEM_BASE, user=user, output_model=OUTPUT_MODELS[task], context={"tree": tree, **ctx})


def _split_outline(tree: DocumentTree) -> list[str]:
    """Map-reduce support: split the outline at top-level headings into parts
    no larger than MAP_REDUCE_CHARS."""
    full = tree.to_outline_text()
    if len(full) <= MAP_REDUCE_CHARS:
        return [full]
    parts, cur = [], ""
    for line in full.split("\n"):
        if line.startswith("# ") and len(cur) > MAP_REDUCE_CHARS * 0.6:
            parts.append(cur)
            cur = f"TITLE: {tree.title}\n"
        cur += line + "\n"
        if len(cur) > MAP_REDUCE_CHARS:
            parts.append(cur)
            cur = f"TITLE: {tree.title}\n"
    if cur.strip():
        parts.append(cur)
    return parts


def generate_document(mode: str, tree: DocumentTree, page_count: int, keyphrases: list[str] | None = None) -> tuple[WDMDocument, GenerationMeta]:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    if mode == "preserve":
        doc = from_llm.tree_to_wdm(tree)
        return doc, GenerationMeta("deterministic", "tree-to-wdm", "ok", output_json=None)

    provider = get_provider()
    parts = _split_outline(tree)
    if mode in ("clean", "smart", "simple") and len(parts) > 1 and not isinstance(provider, ExtractiveProvider):
        # MAP: notes per part. REDUCE: concatenate sections (deterministic).
        sections, metas = [], []
        for part in parts:
            out, meta = _call(provider, _request(mode, tree, part, keyphrases=keyphrases), page_count)
            sections.extend(out.sections)
            metas.append(meta)
        merged = NotesOutput(title=tree.title, sections=sections)
        status = "fallback" if any(m.status == "fallback" for m in metas) else metas[0].status
        meta = GenerationMeta(provider.name, provider.model, status, sum(m.input_tokens for m in metas), sum(m.output_tokens for m in metas), notes=f"map-reduce over {len(parts)} parts")
        out = merged
    else:
        out, meta = _call(provider, _request(mode, tree, parts[0], keyphrases=keyphrases), page_count)

    if isinstance(out, NotesOutput):
        doc = from_llm.notes_to_wdm(out)
    elif isinstance(out, AssignmentOutput):
        doc = from_llm.assignment_to_wdm(out)
    else:
        doc = from_llm.exam_to_wdm(out)  # type: ignore[arg-type]
    meta.output_json = json.loads(out.model_dump_json())
    return doc, meta


def generate_flashcards(tree: DocumentTree, page_count: int, count: int, keyphrases: list[str] | None = None) -> tuple[FlashcardsOutput, GenerationMeta]:
    parts = _split_outline(tree)
    out, meta = _call(get_provider(), _request("flashcards", tree, parts[0], count=count, keyphrases=keyphrases), page_count)
    out.cards = out.cards[:count]
    return out, meta


def generate_quiz(tree: DocumentTree, page_count: int, count: int, keyphrases: list[str] | None = None) -> tuple[QuizOutput, GenerationMeta]:
    parts = _split_outline(tree)
    out, meta = _call(get_provider(), _request("quiz", tree, parts[0], count=count, keyphrases=keyphrases), page_count)
    out.questions = out.questions[:count]
    return out, meta


def answer_question(question: str, chunks: list[dict]) -> tuple[RagAnswer, GenerationMeta]:
    """Grounded answer. Citations are validated against the retrieved chunk ids."""
    provider = get_provider()
    ctx = "\n\n".join(f'<chunk id="{c["id"]}" pages="{c["page_start"]}-{c["page_end"]}">\n{c["text"]}\n</chunk>' for c in chunks)
    user = f"<document>\n{ctx}\n</document>\n\nQuestion (answer only from the chunks above): {question}"
    req = TaskRequest(task="rag", system=prompts.RAG_SYSTEM, user=user, output_model=RagAnswer, context={"question": question, "chunks": chunks}, max_tokens=2000)
    status, notes = "ok", None
    try:
        res = provider.generate(req)
        out = res.output
        if out is None:
            raise LLMError(res.error or "no output")
        meta = GenerationMeta(provider.name, provider.model, "ok", res.input_tokens, res.output_tokens)
    except LLMError as exc:
        out = ExtractiveProvider().generate(req).output
        meta = GenerationMeta(provider.name, provider.model, "fallback", notes=str(exc)[:300])
    valid_ids = {c["id"] for c in chunks}
    out.citations = [c for c in out.citations if c in valid_ids]
    if out.answer is not None:
        out.answer = from_llm.clean_text(out.answer)
    if out.answer and not out.citations:
        # An answer we cannot ground is not shown.
        out.answer = None
        meta.notes = "answer dropped: no valid citations"
    del status, notes
    return out, meta


_WS = re.compile(r"\s+")
