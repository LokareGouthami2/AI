"""Private file storage. Files are stored under random UUID names; the original
filename is display metadata only and is never used to build a path."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

from backend.config import get_settings


def _within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def save_upload(data: bytes, kind: str) -> tuple[str, str]:
    """Persist bytes; returns (stored_path, sha256)."""
    settings = get_settings()
    settings.ensure_dirs()
    name = f"{uuid.uuid4().hex}.{kind}"
    path = settings.upload_dir / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return str(path), hashlib.sha256(data).hexdigest()


def read_upload(stored_path: str) -> bytes:
    settings = get_settings()
    path = Path(stored_path)
    if not _within(settings.upload_dir, path):
        raise PermissionError("path outside upload directory")
    return path.read_bytes()


def delete_file(path_str: str | None) -> None:
    if not path_str:
        return
    settings = get_settings()
    path = Path(path_str)
    if not (_within(settings.upload_dir, path) or _within(settings.render_dir, path)):
        return
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def render_dir_for(document_id: str) -> Path:
    settings = get_settings()
    d = settings.render_dir / uuid.UUID(document_id).hex  # validates the id format
    d.mkdir(parents=True, exist_ok=True)
    return d


def delete_render_dir(document_id: str) -> None:
    settings = get_settings()
    d = settings.render_dir / uuid.UUID(document_id).hex
    if _within(settings.render_dir, d):
        shutil.rmtree(d, ignore_errors=True)


@contextlib.contextmanager
def secure_tempdir() -> Iterator[Path]:
    """Private temp directory that is always removed."""
    settings = get_settings()
    settings.ensure_dirs()
    d = Path(tempfile.mkdtemp(prefix="writeai-", dir=settings.tmp_dir))
    try:
        d.chmod(0o700)
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
