"""Preview / validate / final render — always from the stored HEAD at the
revision the client names (never stale content, never raw AI output)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.documents import storage
from backend.editor import wdm
from backend.handwriting.styles import STYLES
from backend.layout.engine import layout
from backend.layout.settings import RenderSettings, settings_hash
from backend.models.entities import Document, RenderJob, RenderSettingsRow, utcnow
from backend.pdf.render import rasterize, render_pdf
from backend.pdf.scan import FINAL_DPI, scanned_pdf
from backend.pdf.scan import PREVIEW_DPI as SCAN_PREVIEW_DPI
from backend.quality.checker import audit_pdf, check_layout
from backend.services import content as content_service
from backend.services.errors import AppError, not_found

PREVIEW_DPI = 110


def get_settings_for(db: Session, document_id: str) -> RenderSettings:
    row = db.get(RenderSettingsRow, document_id)
    return RenderSettings.model_validate(row.settings) if row else RenderSettings()


def save_settings(db: Session, document_id: str, settings: RenderSettings) -> RenderSettings:
    if db.get(Document, document_id) is None:
        raise not_found()
    row = db.get(RenderSettingsRow, document_id)
    if row:
        row.settings = settings.model_dump()
    else:
        db.add(RenderSettingsRow(document_id=document_id, settings=settings.model_dump()))
    db.commit()
    return settings


def _pinned_head(db: Session, document_id: str, expected_revision: int):
    head = content_service.get_head(db, document_id)
    if head.revision != expected_revision:
        raise AppError(409, "STALE_REVISION", "Save the latest edits before rendering.", {"current_revision": head.revision, "expected_revision": expected_revision})
    return head, wdm.parse(head.content)


def build_pdf(dl, settings: RenderSettings, meta: dict, dpi: int) -> tuple[bytes, bytes]:
    """(output PDF, vector PDF). For "scanned" output the visible pages are
    scan-processed images with an invisible text layer; the vector PDF is
    kept for the underline audit."""
    visible = render_pdf(dl, meta)
    if settings.output == "clean":
        return visible, visible
    layer = render_pdf(dl, meta, text_layer_only=True)
    seed_key = f"{meta.get('content_hash', '')}:{settings.seed}"
    return scanned_pdf(visible, layer, seed_key, dpi=dpi, show_through=settings.show_through, look=settings.output, thin_px=STYLES[settings.style].thin_px, through=settings.show_through_level, pen_shadow=settings.pen_shadow), visible


def _meta(head, title: str, s_hash: str) -> dict:
    return {"content_hash": head.content_hash, "revision": head.revision, "settings_hash": s_hash[:16], "title": title}


def validate(db: Session, document_id: str, expected_revision: int, settings: RenderSettings | None) -> dict:
    head, doc = _pinned_head(db, document_id, expected_revision)
    s = settings or get_settings_for(db, document_id)
    dl = layout(doc, s, head.content_hash)
    return check_layout(doc, dl).to_dict()


def preview(db: Session, document_id: str, expected_revision: int, settings: RenderSettings | None, pages: list[int] | None) -> dict:
    head, doc = _pinned_head(db, document_id, expected_revision)
    s = settings or get_settings_for(db, document_id)
    s_hash = settings_hash(s)
    out_dir = storage.render_dir_for(document_id)
    # Cache key includes the content hash: an edit can never hit an old entry.
    key = f"preview-{head.content_hash[:16]}-{s_hash[:16]}"
    existing = db.scalar(select(RenderJob).where(RenderJob.document_id == document_id, RenderJob.kind == "preview", RenderJob.content_hash == head.content_hash, RenderJob.settings_hash == s_hash, RenderJob.status == "succeeded"))
    if existing and all(Path(p).exists() for p in existing.preview_paths):
        job = existing
    else:
        dl = layout(doc, s, head.content_hash)
        report = check_layout(doc, dl)
        pdf, _ = build_pdf(dl, s, _meta(head, doc.title, s_hash), SCAN_PREVIEW_DPI)
        pngs = rasterize(pdf, dpi=PREVIEW_DPI)
        paths = []
        for i, png in enumerate(pngs, start=1):
            p = out_dir / f"{key}-p{i}.png"
            p.write_bytes(png)
            paths.append(str(p))
        job = RenderJob(document_id=document_id, kind="preview", revision=head.revision, content_hash=head.content_hash, settings_hash=s_hash, status="succeeded", preview_paths=paths, quality_report=report.to_dict(), finished_at=utcnow())
        db.add(job)
        db.commit()
    page_list = [{"number": i, "url": f"/api/documents/{document_id}/renders/{job.id}/pages/{i}.png"} for i in range(1, len(job.preview_paths) + 1) if not pages or i in pages]
    return {"render_id": job.id, "revision": job.revision, "content_hash": job.content_hash, "page_count": len(job.preview_paths), "pages": page_list, "quality": job.quality_report}


def render_final(document_id: str, expected_revision: int, settings: dict | None) -> dict:
    """Final PDF (runs as a background job)."""
    from backend.database.session import session_scope

    with session_scope() as db:
        head, doc = _pinned_head(db, document_id, expected_revision)
        s = RenderSettings.model_validate(settings) if settings else get_settings_for(db, document_id)
        s_hash = settings_hash(s)
        content_service.create_version(db, document_id, "pre_render", f"Rendered revision {head.revision}")
        meta = _meta(head, doc.title, s_hash)
        head_hash, revision = head.content_hash, head.revision
    dl = layout(doc, s, head_hash)
    report = check_layout(doc, dl)
    status = "succeeded"
    output_path = None
    pdf_audit = None
    if report.passed:
        pdf, vector = build_pdf(dl, s, meta, FINAL_DPI)
        expected = {"content_hash": head_hash, "revision": revision}
        audit = audit_pdf(doc, dl, vector, expected)
        if pdf is not vector:
            # Scanned output: also read the final file's text layer back.
            scan_audit = audit_pdf(doc, dl, pdf, expected, check_strokes=False)
            audit.errors += scan_audit.errors
            audit.warnings += scan_audit.warnings
            audit.passed = audit.passed and scan_audit.passed
            audit.checks = audit.checks + ["scan_text_layer"]
        pdf_audit = audit.to_dict()
        if audit.passed:
            out = storage.render_dir_for(document_id) / f"final-{head_hash[:16]}-{s_hash[:16]}.pdf"
            out.write_bytes(pdf)
            output_path = str(out)
        else:
            status = "rejected_by_quality"
    else:
        status = "rejected_by_quality"
    quality = report.to_dict()
    quality["pdf_audit"] = pdf_audit
    with session_scope() as db:
        job = RenderJob(document_id=document_id, kind="final", revision=revision, content_hash=head_hash, settings_hash=s_hash, status=status, output_path=output_path, quality_report=quality, finished_at=utcnow())
        db.add(job)
        db.flush()
        render_id = job.id
    return {"render_id": render_id, "status": status, "revision": revision, "content_hash": head_hash, "page_count": len(dl.pages), "quality": quality, "download_url": f"/api/documents/{document_id}/download?render_id={render_id}" if output_path else None}


def get_render(db: Session, document_id: str, render_id: str) -> RenderJob:
    job = db.get(RenderJob, render_id)
    if job is None or job.document_id != document_id:
        raise not_found("Render")
    return job


def latest_final(db: Session, document_id: str, render_id: str | None) -> RenderJob:
    if render_id:
        job = get_render(db, document_id, render_id)
    else:
        job = db.scalar(select(RenderJob).where(RenderJob.document_id == document_id, RenderJob.kind == "final", RenderJob.status == "succeeded").order_by(RenderJob.created_at.desc()).limit(1))
        if job is None:
            raise AppError(404, "NO_RENDER", "No final PDF has been generated yet.")
        head = content_service.get_head(db, document_id)
        if head.content_hash != job.content_hash:
            raise AppError(409, "STALE_RENDER", "The document changed after the last PDF was generated. Generate it again.", {"render_revision": job.revision, "current_revision": head.revision})
    if job.kind != "final" or not job.output_path or not Path(job.output_path).exists():
        raise AppError(404, "NO_RENDER", "That render has no PDF.")
    return job
