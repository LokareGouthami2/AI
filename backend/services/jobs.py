"""Minimal background job runner backed by the ``jobs`` table.

Long operations (extract / analyze / generate / render) run in a thread pool
and report status via GET /api/jobs/{id}. In tests they run inline. The
interface is what would be swapped for RQ/Celery when scaling out.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from backend.config import get_settings
from backend.database.session import session_scope
from backend.models.entities import Job, utcnow

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="writeai-job")


def create_job(kind: str, document_id: str | None) -> str:
    with session_scope() as db:
        job = Job(kind=kind, document_id=document_id, status="queued")
        db.add(job)
        db.flush()
        return job.id


def _run(job_id: str, fn: Callable[..., dict | None], args: tuple) -> None:
    with session_scope() as db:
        job = db.get(Job, job_id)
        job.status = "running"
        job.progress = 0.05
    try:
        result = fn(*args)
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status, job.progress, job.result, job.finished_at = "succeeded", 1.0, result or {}, utcnow()
    except Exception as exc:  # report, never crash the worker
        from backend.services.errors import AppError

        msg = exc.message if isinstance(exc, AppError) else "The operation failed. See server logs for details."
        log.error("job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
        with session_scope() as db:
            job = db.get(Job, job_id)
            job.status, job.error, job.finished_at = "failed", msg, utcnow()


def submit(kind: str, document_id: str | None, fn: Callable[..., dict | None], *args) -> str:
    job_id = create_job(kind, document_id)
    if get_settings().env == "test":
        _run(job_id, fn, args)
    else:
        _executor.submit(_run, job_id, fn, args)
    return job_id
