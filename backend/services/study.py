"""Flashcards, quizzes and Ask-Your-Document."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.llm import service as llm_service
from backend.models.entities import Chunk, FlashcardSet, Generation, QALog, Quiz
from backend.rag.embedder import get_embedder
from backend.rag.retriever import retrieve
from backend.rag.store import get_store
from backend.services.documents import get_document, load_tree
from backend.services.errors import AppError, not_found


def generate_flashcards(db: Session, document_id: str, count: int) -> tuple[FlashcardSet, llm_service.GenerationMeta]:
    tree, pages, kp = load_tree(db, document_id)
    out, meta = llm_service.generate_flashcards(tree, pages, count, kp)
    gen = Generation(document_id=document_id, mode="flashcards", provider=meta.provider, model=meta.model, prompt_version="v1", input_tokens=meta.input_tokens, output_tokens=meta.output_tokens, output_json=out.model_dump(), status=meta.status, notes=meta.notes)
    db.add(gen)
    db.flush()
    fs = FlashcardSet(document_id=document_id, generation_id=gen.id, cards=[c.model_dump() for c in out.cards])
    db.add(fs)
    db.commit()
    return fs, meta


def save_flashcards(db: Session, document_id: str, set_id: str, cards: list[dict]) -> FlashcardSet:
    fs = db.get(FlashcardSet, set_id)
    if fs is None or fs.document_id != document_id:
        raise not_found("Flashcard set")
    fs.cards = cards
    db.commit()
    return fs


def latest_flashcards(db: Session, document_id: str) -> FlashcardSet | None:
    return db.scalar(select(FlashcardSet).where(FlashcardSet.document_id == document_id).order_by(FlashcardSet.created_at.desc()).limit(1))


def generate_quiz(db: Session, document_id: str, count: int) -> tuple[Quiz, llm_service.GenerationMeta]:
    tree, pages, kp = load_tree(db, document_id)
    out, meta = llm_service.generate_quiz(tree, pages, count, kp)
    gen = Generation(document_id=document_id, mode="quiz", provider=meta.provider, model=meta.model, prompt_version="v1", input_tokens=meta.input_tokens, output_tokens=meta.output_tokens, output_json=out.model_dump(), status=meta.status, notes=meta.notes)
    db.add(gen)
    db.flush()
    q = Quiz(document_id=document_id, generation_id=gen.id, questions=[x.model_dump() for x in out.questions])
    db.add(q)
    db.commit()
    return q, meta


def save_quiz(db: Session, document_id: str, quiz_id: str, questions: list[dict]) -> Quiz:
    q = db.get(Quiz, quiz_id)
    if q is None or q.document_id != document_id:
        raise not_found("Quiz")
    for i, item in enumerate(questions):
        if len({o.strip().lower() for o in item["options"]}) != 4:
            raise AppError(422, "INVALID_QUIZ", f"Question {i + 1} needs four different options.")
    q.questions = questions
    db.commit()
    return q


def latest_quiz(db: Session, document_id: str) -> Quiz | None:
    return db.scalar(select(Quiz).where(Quiz.document_id == document_id).order_by(Quiz.created_at.desc()).limit(1))


def ask(db: Session, document_id: str, question: str) -> dict:
    get_document(db, document_id)
    t0 = time.time()
    rows = db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.order_index)).all()
    if not rows:
        raise AppError(409, "NOT_ANALYZED", "Analyze the document first.")
    chunks = [{"id": r.id, "text": r.text, "page_start": r.page_start, "page_end": r.page_end, "section_path": r.section_path} for r in rows]
    hits = retrieve(question, document_id, chunks, get_embedder(), get_store(), top_k=5)
    # Short aliases (c1..c5) for the prompt; mapped back to real ids afterwards.
    alias = {f"c{i + 1}": h for i, h in enumerate(hits)}
    ctx = [{"id": a, "text": h.text, "page_start": h.page_start, "page_end": h.page_end} for a, h in alias.items()]
    if ctx:
        ans, meta = llm_service.answer_question(question, ctx)
        provider, status = meta.provider, meta.status
    else:
        ans, provider, status = None, "none", "no_context"
    citations = []
    if ans is not None and ans.answer:
        for a in ans.citations:
            h = alias[a]
            citations.append({"chunk_id": h.id, "pages": list(range(h.page_start, h.page_end + 1)), "section": h.section_path, "excerpt": h.text[:300]})
    answer = ans.answer if ans is not None else None
    db.add(QALog(document_id=document_id, question=question, answer=answer, cited_chunk_ids=[c["chunk_id"] for c in citations], grounded=bool(answer and citations), latency_ms=int((time.time() - t0) * 1000)))
    db.commit()
    return {
        "answer": answer,
        "grounded": bool(answer and citations),
        "confidence": ans.confidence if ans is not None else "low",
        "citations": citations,
        "provider": provider,
        "status": status,
    }
