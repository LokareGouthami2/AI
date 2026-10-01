"""REST API. See docs/design.md §9 for the endpoint contract."""

from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from backend.api.deps import SESSION_COOKIE, rate_limit, require_token, session_value, token_ok
from backend.config import get_settings
from backend.database.session import get_db
from backend.editor import wdm
from backend.editor.diff import diff_documents
from backend.layout.settings import RenderSettings
from backend.models.entities import Analysis, Job, Segment
from backend.schemas import api as S
from backend.services import content as content_service
from backend.services import documents as doc_service
from backend.services import jobs
from backend.services import render as render_service
from backend.services import study as study_service
from backend.services.errors import AppError, not_found

router = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
# Login endpoints must be reachable before logging in.
auth_router = APIRouter(prefix="/api/auth")


@auth_router.get("/status")
def auth_status(request: Request):
    return {"password_required": get_settings().api_token is not None, "logged_in": token_ok(request)}


@auth_router.post("/login", dependencies=[Depends(rate_limit("login", 10))])
def auth_login(body: S.LoginIn, request: Request, response: Response):
    token = get_settings().api_token
    if token is None:
        return {"ok": True}
    if not hmac.compare_digest(body.password.encode(), token.get_secret_value().encode()):
        raise AppError(401, "WRONG_PASSWORD", "That password is not correct.")
    response.set_cookie(
        SESSION_COOKIE,
        session_value(token.get_secret_value()),
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        path="/api",
    )
    return {"ok": True}


@auth_router.post("/logout")
def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/api")
    return {"ok": True}


def _job_out(db: Session, job_id: str) -> S.JobOut:
    return S.JobOut.model_validate(db.get(Job, job_id))


# ---------------------------------------------------------------- documents


@router.get("/documents", response_model=list[S.DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return doc_service.list_documents(db)


@router.post("/documents/upload", response_model=S.DocumentOut, status_code=201, dependencies=[Depends(rate_limit("upload", 20))])
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # never read more than limit+1 bytes
    if len(data) > limit:
        raise AppError(413, "FILE_TOO_LARGE", f"File exceeds {get_settings().max_upload_mb} MB.")
    doc = doc_service.upload(db, file.filename or "document", data)
    return {**S.DocumentOut.model_validate(doc).model_dump(), "has_content": False}


@router.get("/documents/{document_id}", response_model=S.DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    d = doc_service.get_document(db, document_id)
    head = db.get(content_service.DocumentContent, document_id)
    return {**S.DocumentOut.model_validate(d).model_dump(), "has_content": head is not None, "revision": head.revision if head else None}


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc_service.delete_document(db, document_id)
    return Response(status_code=204)


@router.post("/documents/{document_id}/extract", response_model=S.JobOut, status_code=202)
def extract(document_id: str, db: Session = Depends(get_db)):
    doc_service.get_document(db, document_id)
    job_id = jobs.submit("extract", document_id, doc_service.run_extract, document_id)
    db.expire_all()
    return _job_out(db, job_id)


@router.post("/documents/{document_id}/analyze", response_model=S.JobOut, status_code=202)
def analyze(document_id: str, db: Session = Depends(get_db)):
    doc_service.get_document(db, document_id)
    job_id = jobs.submit("analyze", document_id, doc_service.run_analyze, document_id)
    db.expire_all()
    return _job_out(db, job_id)


@router.get("/documents/{document_id}/analysis")
def get_analysis(document_id: str, db: Session = Depends(get_db)):
    from sqlalchemy import select

    doc_service.get_document(db, document_id)
    a = db.scalar(select(Analysis).where(Analysis.document_id == document_id))
    if a is None:
        raise AppError(404, "NOT_ANALYZED", "The document has not been analyzed yet.")
    segs = db.scalars(select(Segment).where(Segment.document_id == document_id).order_by(Segment.order_index)).all()
    return {
        "stats": a.stats,
        "segments": [{"page": s.page_number, "text": s.text[:400], "label": s.predicted_label, "confidence": s.confidence, "source": "rules" if s.model_version == "rules" else "model"} for s in segs],
    }


@router.post("/documents/{document_id}/generate", response_model=S.JobOut, status_code=202, dependencies=[Depends(rate_limit("generate", 10))])
def generate(document_id: str, body: S.GenerateRequest, db: Session = Depends(get_db)):
    doc_service.get_document(db, document_id)
    job_id = jobs.submit("generate", document_id, doc_service.run_generate, document_id, body.mode)
    db.expire_all()
    return _job_out(db, job_id)


# ------------------------------------------------------------------ content


@router.get("/documents/{document_id}/content", response_model=S.ContentOut)
def get_content(document_id: str, db: Session = Depends(get_db)):
    head = content_service.get_head(db, document_id)
    return S.ContentOut(document_id=document_id, revision=head.revision, content_hash=head.content_hash, content=head.content, updated_at=head.updated_at)


@router.put("/documents/{document_id}/content", response_model=S.ContentSaveOut)
def put_content(document_id: str, body: S.ContentSaveRequest, db: Session = Depends(get_db)):
    head, version = content_service.save(db, document_id, body.content, body.base_revision, body.force)
    return S.ContentSaveOut(revision=head.revision, content_hash=head.content_hash, updated_at=head.updated_at, version_created=version)


@router.get("/documents/{document_id}/versions", response_model=list[S.VersionOut])
def list_versions(document_id: str, db: Session = Depends(get_db)):
    return content_service.list_versions(db, document_id)


@router.post("/documents/{document_id}/versions", response_model=S.VersionOut, status_code=201)
def create_version(document_id: str, body: S.VersionCreate, db: Session = Depends(get_db)):
    v = content_service.create_version(db, document_id, "manual_save", body.label or "Saved version")
    db.commit()
    return v


@router.get("/documents/{document_id}/versions/{number}")
def get_version(document_id: str, number: int, db: Session = Depends(get_db)):
    v = content_service.get_version(db, document_id, number)
    head = content_service.get_head(db, document_id)
    diff = diff_documents(wdm.parse(v.content), wdm.parse(head.content))
    return {"version": S.VersionOut.model_validate(v).model_dump(), "content": v.content, "diff_to_current": diff}


@router.post("/documents/{document_id}/versions/{number}/restore", response_model=S.ContentOut)
def restore_version(document_id: str, number: int, db: Session = Depends(get_db)):
    head = content_service.restore(db, document_id, number)
    return S.ContentOut(document_id=document_id, revision=head.revision, content_hash=head.content_hash, content=head.content, updated_at=head.updated_at)


# ---------------------------------------------------------------- rendering


@router.get("/documents/{document_id}/render-settings", response_model=RenderSettings)
def get_render_settings(document_id: str, db: Session = Depends(get_db)):
    doc_service.get_document(db, document_id)
    return render_service.get_settings_for(db, document_id)


@router.put("/documents/{document_id}/render-settings", response_model=RenderSettings)
def put_render_settings(document_id: str, body: RenderSettings, db: Session = Depends(get_db)):
    return render_service.save_settings(db, document_id, body)


@router.get("/handwriting/styles")
def handwriting_styles():
    from backend.handwriting.styles import STYLES

    return [{"id": k, "label": v.label} for k, v in STYLES.items()]


@router.post("/documents/{document_id}/preview", response_model=S.PreviewOut, dependencies=[Depends(rate_limit("render", 30))])
def preview(document_id: str, body: S.RenderRequest, db: Session = Depends(get_db)):
    return render_service.preview(db, document_id, body.expected_revision, body.settings, body.pages)


@router.get("/documents/{document_id}/renders/{render_id}/pages/{number}.png")
def preview_page(document_id: str, render_id: str, number: int, db: Session = Depends(get_db)):
    job = render_service.get_render(db, document_id, render_id)
    if not 1 <= number <= len(job.preview_paths):
        raise not_found("Page")
    path = Path(job.preview_paths[number - 1])
    if not path.exists():
        raise not_found("Page")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=86400, immutable"})


@router.post("/documents/{document_id}/validate")
def validate(document_id: str, body: S.RenderRequest, db: Session = Depends(get_db)):
    return render_service.validate(db, document_id, body.expected_revision, body.settings)


@router.post("/documents/{document_id}/render", response_model=S.JobOut, status_code=202, dependencies=[Depends(rate_limit("render", 20))])
def render(document_id: str, body: S.RenderRequest, db: Session = Depends(get_db)):
    content_service.get_head(db, document_id)
    job_id = jobs.submit("render", document_id, render_service.render_final, document_id, body.expected_revision, body.settings.model_dump() if body.settings else None)
    db.expire_all()
    return _job_out(db, job_id)


@router.get("/documents/{document_id}/download")
def download(document_id: str, render_id: str | None = Query(default=None), db: Session = Depends(get_db)):
    job = render_service.latest_final(db, document_id, render_id)
    d = doc_service.get_document(db, document_id)
    safe = "".join(ch for ch in d.title if ch.isalnum() or ch in " -_")[:80].strip() or "writeai"
    return FileResponse(job.output_path, media_type="application/pdf", filename=f"{safe} (handwritten).pdf")


# -------------------------------------------------------------------- study


@router.post("/documents/{document_id}/ask", response_model=S.AskOut, dependencies=[Depends(rate_limit("ask", 30))])
def ask(document_id: str, body: S.AskRequest, db: Session = Depends(get_db)):
    return study_service.ask(db, document_id, body.question)


@router.post("/documents/{document_id}/flashcards", response_model=S.FlashcardSetOut, dependencies=[Depends(rate_limit("generate", 10))])
def flashcards(document_id: str, body: S.StudyGenerateRequest, db: Session = Depends(get_db)):
    fs, meta = study_service.generate_flashcards(db, document_id, body.count)
    return S.FlashcardSetOut(id=fs.id, cards=fs.cards, provider=meta.provider, status=meta.status, updated_at=fs.updated_at)


@router.get("/documents/{document_id}/flashcards", response_model=S.FlashcardSetOut | None)
def get_flashcards(document_id: str, db: Session = Depends(get_db)):
    fs = study_service.latest_flashcards(db, document_id)
    return S.FlashcardSetOut(id=fs.id, cards=fs.cards, updated_at=fs.updated_at) if fs else None


@router.put("/documents/{document_id}/flashcards/{set_id}", response_model=S.FlashcardSetOut)
def save_flashcards(document_id: str, set_id: str, body: S.FlashcardSaveRequest, db: Session = Depends(get_db)):
    fs = study_service.save_flashcards(db, document_id, set_id, [c.model_dump() for c in body.cards])
    return S.FlashcardSetOut(id=fs.id, cards=fs.cards, updated_at=fs.updated_at)


@router.post("/documents/{document_id}/quiz", response_model=S.QuizOut, dependencies=[Depends(rate_limit("generate", 10))])
def quiz(document_id: str, body: S.StudyGenerateRequest, db: Session = Depends(get_db)):
    q, meta = study_service.generate_quiz(db, document_id, body.count)
    return S.QuizOut(id=q.id, questions=q.questions, provider=meta.provider, status=meta.status, updated_at=q.updated_at)


@router.get("/documents/{document_id}/quiz", response_model=S.QuizOut | None)
def get_quiz(document_id: str, db: Session = Depends(get_db)):
    q = study_service.latest_quiz(db, document_id)
    return S.QuizOut(id=q.id, questions=q.questions, updated_at=q.updated_at) if q else None


@router.put("/documents/{document_id}/quiz/{quiz_id}", response_model=S.QuizOut)
def save_quiz(document_id: str, quiz_id: str, body: S.QuizSaveRequest, db: Session = Depends(get_db)):
    q = study_service.save_quiz(db, document_id, quiz_id, [x.model_dump() for x in body.questions])
    return S.QuizOut(id=q.id, questions=q.questions, updated_at=q.updated_at)


# --------------------------------------------------------------------- jobs


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("Job")
    return job
