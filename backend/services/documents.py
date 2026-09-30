"""Document lifecycle: upload → extract → analyze → generate, plus delete."""

from __future__ import annotations

import logging
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.session import session_scope
from backend.documents import storage
from backend.documents.extract import extract
from backend.documents.validation import UploadRejected, validate_upload
from backend.editor import wdm
from backend.llm import service as llm_service
from backend.ml.predict import get_classifier
from backend.models.entities import (
    Analysis,
    Chunk,
    Document,
    DocumentContent,
    DocumentPage,
    Generation,
    utcnow,
)
from backend.models.entities import (
    Segment as SegmentRow,
)
from backend.nlp.preprocess import preprocess
from backend.nlp.stats import document_stats
from backend.nlp.structure import DocumentTree, build_tree
from backend.rag.chunker import chunk_tree
from backend.rag.embedder import get_embedder
from backend.rag.store import get_store
from backend.services import content as content_service
from backend.services.errors import AppError, not_found

log = logging.getLogger(__name__)


def get_document(db: Session, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise not_found()
    return doc


def upload(db: Session, filename: str, data: bytes) -> Document:
    settings = get_settings()
    try:
        v = validate_upload(filename, data, settings)
    except UploadRejected as exc:
        raise AppError(413 if exc.code == "FILE_TOO_LARGE" else 415 if exc.code in ("UNSUPPORTED_TYPE", "BAD_FILE_TYPE") else 422, exc.code, exc.message) from exc
    path, sha = storage.save_upload(data, v.kind)
    title = re.sub(r"\.[A-Za-z0-9]+$", "", v.safe_name).replace("_", " ").strip() or "Untitled"
    doc = Document(
        title=title[:300],
        original_name=v.safe_name,
        stored_path=path,
        mime_type=v.mime_type,
        kind=v.kind,
        sha256=sha,
        size_bytes=len(data),
        page_count=v.page_count,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _set_status(document_id: str, status: str, error: str | None = None) -> None:
    with session_scope() as db:
        d = db.get(Document, document_id)
        if d:
            d.status, d.error = status, error


def run_extract(document_id: str) -> dict:
    _set_status(document_id, "extracting")
    try:
        with session_scope() as db:
            d = get_document(db, document_id)
            data = storage.read_upload(d.stored_path)
            kind = d.kind
        extracted = extract(kind, data)
        with session_scope() as db:
            db.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))
            for p in extracted.pages:
                db.add(DocumentPage(document_id=document_id, page_number=p.number, text=p.text, source=p.source, ocr_confidence=p.ocr_confidence, width=p.width, height=p.height))
            d = db.get(Document, document_id)
            d.page_count = extracted.page_count
            d.status = "extracted"
        ocr_pages = [p.number for p in extracted.pages if p.source == "ocr"]
        return {"pages": extracted.page_count, "ocr_pages": ocr_pages, "characters": sum(len(p.text) for p in extracted.pages)}
    except AppError:
        _set_status(document_id, "failed", "Extraction failed.")
        raise
    except Exception as exc:
        _set_status(document_id, "failed", "Text extraction failed for this file.")
        raise AppError(422, "EXTRACTION_FAILED", "Text extraction failed for this file.") from exc


def run_analyze(document_id: str) -> dict:
    """NLP preprocessing + ML classification + stats + RAG index."""
    _set_status(document_id, "analyzing")
    with session_scope() as db:
        d = get_document(db, document_id)
        data = storage.read_upload(d.stored_path)
        kind, title = d.kind, d.title
        ocr_pages = [p.page_number for p in d.pages if p.source == "ocr"]
        ocr_conf = {p.page_number: p.ocr_confidence for p in d.pages if p.ocr_confidence is not None}
    extracted = extract(kind, data, allow_ocr=True)
    segments = preprocess(extracted)
    if not segments:
        _set_status(document_id, "failed", "No readable text was found in this document.")
        raise AppError(422, "NO_TEXT", "No readable text was found in this document.")
    clf = get_classifier()
    preds = clf.classify(segments)
    from backend.ml.features import segment_samples

    samples = segment_samples(segments)
    full_text = "\n".join(s.text if s.text.endswith((".", "?", "!", ":")) else s.text + "." for s in segments)
    stats = document_stats(full_text)
    label_counts: dict[str, int] = {}
    for p in preds:
        label_counts[p.label] = label_counts.get(p.label, 0) + 1
    stats.update(
        segments=len(segments),
        label_distribution=label_counts,
        low_confidence_segments=sum(1 for p in preds if p.source == "rule"),
        classifier_version=clf.version,
        ocr_pages=ocr_pages,
        ocr_confidence=ocr_conf,
        pages=extracted.page_count,
    )
    tree = build_tree([s.text for s in segments], [p.label for p in preds], [s.page for s in segments], title)
    chunks = chunk_tree(tree)
    embedder = get_embedder()
    store = get_store()
    with session_scope() as db:
        db.execute(delete(SegmentRow).where(SegmentRow.document_id == document_id))
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.execute(delete(Analysis).where(Analysis.document_id == document_id))
        for i, (seg, pred, sample) in enumerate(zip(segments, preds, samples)):
            db.add(SegmentRow(document_id=document_id, page_number=seg.page, order_index=i, text=seg.text, features={k: round(v, 4) for k, v in sample["layout"].items()}, predicted_label=pred.label, confidence=round(pred.confidence, 4), model_version=clf.version if pred.source == "model" else "rules"))
        chunk_rows = []
        for c in chunks:
            row = Chunk(document_id=document_id, order_index=c.order_index, text=c.text, section_path=c.section_path[:500], page_start=c.page_start, page_end=c.page_end, token_count=c.token_count, embedding_model=embedder.name)
            db.add(row)
            chunk_rows.append(row)
        db.flush()
        stats["title"] = tree.title
        stats["chunks"] = len(chunk_rows)
        db.add(Analysis(document_id=document_id, stats=stats))
        d = db.get(Document, document_id)
        d.status = "analyzed"
        if tree.title and tree.title != title and len(tree.title) < 150:
            d.title = tree.title
        ids = [r.id for r in chunk_rows]
        texts = [r.text for r in chunk_rows]
        metas = [{"page_start": r.page_start, "page_end": r.page_end} for r in chunk_rows]
    store.delete_document(document_id)
    if ids:
        store.add(document_id, ids, embedder.embed(texts), metas)
    return {"segments": len(segments), "chunks": len(ids), "labels": label_counts}


def load_tree(db: Session, document_id: str) -> tuple[DocumentTree, int, list[str]]:
    d = get_document(db, document_id)
    rows = db.scalars(select(SegmentRow).where(SegmentRow.document_id == document_id).order_by(SegmentRow.order_index)).all()
    if not rows:
        raise AppError(409, "NOT_ANALYZED", "Analyze the document first.")
    tree = build_tree([r.text for r in rows], [r.predicted_label for r in rows], [r.page_number for r in rows], d.title)
    analysis = db.scalar(select(Analysis).where(Analysis.document_id == document_id))
    keyphrases = (analysis.stats.get("keyphrases") if analysis else None) or []
    return tree, max(d.page_count, 1), keyphrases


def run_generate(document_id: str, mode: str) -> dict:
    _set_status(document_id, "generating")
    try:
        with session_scope() as db:
            tree, pages, keyphrases = load_tree(db, document_id)
        doc, meta = llm_service.generate_document(mode, tree, pages, keyphrases)
        with session_scope() as db:
            gen = Generation(document_id=document_id, mode=mode, provider=meta.provider, model=meta.model, prompt_version="v1", input_tokens=meta.input_tokens, output_tokens=meta.output_tokens, output_json=meta.output_json or {}, status=meta.status, notes=meta.notes)
            db.add(gen)
            head = content_service.replace_content(db, document_id, doc, source="ai_generated", label=f"AI generated ({mode})")
            d = db.get(Document, document_id)
            d.status = "ready"
            return {"mode": mode, "revision": head.revision, "status": meta.status, "provider": meta.provider, "blocks": len(doc.blocks)}
    except AppError:
        _set_status(document_id, "analyzed")
        raise


def list_documents(db: Session) -> list[dict]:
    docs = db.scalars(select(Document).order_by(Document.updated_at.desc())).all()
    heads = {h.document_id: h.revision for h in db.scalars(select(DocumentContent)).all()}
    out = []
    for d in docs:
        out.append({**{c: getattr(d, c) for c in ("id", "title", "original_name", "kind", "size_bytes", "page_count", "status", "error", "created_at", "updated_at")}, "has_content": d.id in heads, "revision": heads.get(d.id)})
    return out


def delete_document(db: Session, document_id: str) -> None:
    d = get_document(db, document_id)
    stored = d.stored_path
    db.delete(d)
    db.commit()
    storage.delete_file(stored)
    storage.delete_render_dir(document_id)
    try:
        get_store().delete_document(document_id)
    except Exception:  # pragma: no cover
        log.warning("could not delete vectors for %s", document_id)


def blank_document(title: str) -> wdm.WDMDocument:
    return wdm.WDMDocument(title=title, blocks=[wdm.heading(1, title), wdm.Paragraph()])


_ = utcnow  # re-exported for services that stamp times
