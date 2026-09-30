"""Editable document HEAD + version history.

* ``save`` is optimistic-concurrency controlled by ``base_revision``.
* Autosave does not create a version per save; a checkpoint version is
  created at most every CHECKPOINT_MINUTES of editing.
* Restore never destroys anything: the current head is snapshotted first.
"""

from __future__ import annotations

from datetime import UTC, timedelta

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.editor import wdm
from backend.models.entities import Document, DocumentContent, DocumentVersion, utcnow
from backend.services.errors import AppError, not_found

CHECKPOINT_MINUTES = 5
MAX_CONTENT_BYTES = 5 * 1024 * 1024


def _parse(content: dict) -> wdm.WDMDocument:
    import json

    if len(json.dumps(content)) > MAX_CONTENT_BYTES:
        raise AppError(413, "CONTENT_TOO_LARGE", "The document is too large to save.")
    try:
        return wdm.normalize(wdm.parse(content))
    except ValidationError as exc:
        errs = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()[:10]]
        raise AppError(422, "INVALID_DOCUMENT", "The document structure is invalid.", {"errors": errs}) from exc


def get_head(db: Session, document_id: str) -> DocumentContent:
    if db.get(Document, document_id) is None:
        raise not_found()
    head = db.get(DocumentContent, document_id)
    if head is None:
        raise AppError(404, "NO_CONTENT", "No editable document yet — generate one first.")
    return head


def _next_version_number(db: Session, document_id: str) -> int:
    n = db.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document_id))
    return (n or 0) + 1


def create_version(db: Session, document_id: str, source: str, label: str | None = None) -> DocumentVersion:
    head = get_head(db, document_id)
    last = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.version_number.desc()).limit(1))
    if last is not None and last.content_hash == head.content_hash and source in ("checkpoint", "pre_render", "pre_restore"):
        return last  # nothing changed since the last snapshot
    v = DocumentVersion(document_id=document_id, version_number=_next_version_number(db, document_id), revision=head.revision, content=head.content, content_hash=head.content_hash, source=source, label=label)
    db.add(v)
    db.flush()
    return v


def replace_content(db: Session, document_id: str, doc: wdm.WDMDocument, source: str, label: str | None = None) -> DocumentContent:
    """Write a new head (used by AI generation and restore) and snapshot it."""
    doc = wdm.normalize(doc)
    head = db.get(DocumentContent, document_id)
    if head is not None:
        create_version(db, document_id, "pre_restore" if source == "restored" else "checkpoint", "Before replacement")
        head.revision += 1
        head.content = wdm.dump(doc)
        head.content_hash = wdm.content_hash(doc)
        head.updated_at = utcnow()
    else:
        head = DocumentContent(document_id=document_id, revision=1, content=wdm.dump(doc), content_hash=wdm.content_hash(doc))
        db.add(head)
    db.flush()
    create_version(db, document_id, source, label)
    return head


def save(db: Session, document_id: str, content: dict, base_revision: int, force: bool = False) -> tuple[DocumentContent, int | None]:
    doc = _parse(content)
    head = db.get(DocumentContent, document_id)
    if db.get(Document, document_id) is None:
        raise not_found()
    if head is None:
        head = DocumentContent(document_id=document_id, revision=1, content=wdm.dump(doc), content_hash=wdm.content_hash(doc))
        db.add(head)
        db.commit()
        return head, None
    if head.revision != base_revision and not force:
        raise AppError(409, "STALE_REVISION", "The document was changed elsewhere.", {"current_revision": head.revision})
    new_hash = wdm.content_hash(doc)
    version_created = None
    if new_hash != head.content_hash:
        # Checkpoint the *previous* state if the last version is old enough.
        last = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.version_number.desc()).limit(1))
        if last is None or (utcnow() - _aware(last.created_at)) > timedelta(minutes=CHECKPOINT_MINUTES):
            version_created = create_version(db, document_id, "checkpoint", "Autosave checkpoint").version_number
        head.content = wdm.dump(doc)
        head.content_hash = new_hash
        head.revision += 1
        head.updated_at = utcnow()
    db.commit()
    return head, version_created


def _aware(dt):

    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def list_versions(db: Session, document_id: str) -> list[DocumentVersion]:
    if db.get(Document, document_id) is None:
        raise not_found()
    return list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(DocumentVersion.version_number.desc())).all())


def get_version(db: Session, document_id: str, number: int) -> DocumentVersion:
    v = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id, DocumentVersion.version_number == number))
    if v is None:
        raise not_found("Version")
    return v


def restore(db: Session, document_id: str, number: int) -> DocumentContent:
    v = get_version(db, document_id, number)
    doc = wdm.parse(v.content)
    head = replace_content(db, document_id, doc, source="restored", label=f"Restored from version {number}")
    db.commit()
    return head
