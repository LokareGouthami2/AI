"""Upload validation: extension allow-list + magic-byte sniffing + limits.

We never trust the client-supplied filename or Content-Type.
"""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF

from backend.config import Settings

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
}


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ValidatedUpload:
    kind: str
    mime_type: str
    safe_name: str
    page_count: int


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFKC", name or "document")
    name = name.replace("\\", "/").split("/")[-1]  # drop any path component
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .")
    return (name or "document")[:200]


def _extension(name: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]+)$", name)
    return m.group(1).lower() if m else ""


def _check_pdf(data: bytes, settings: Settings) -> int:
    if not data.startswith(b"%PDF-"):
        raise UploadRejected("BAD_FILE_TYPE", "File does not look like a PDF.")
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass or doc.is_encrypted:
                raise UploadRejected("ENCRYPTED_PDF", "Password-protected PDFs are not supported.")
            pages = doc.page_count
    except UploadRejected:
        raise
    except Exception as exc:  # corrupt file
        raise UploadRejected("CORRUPT_FILE", "The PDF could not be opened.") from exc
    if pages == 0:
        raise UploadRejected("EMPTY_FILE", "The PDF has no pages.")
    if pages > settings.max_pages:
        raise UploadRejected("TOO_MANY_PAGES", f"PDF has {pages} pages; limit is {settings.max_pages}.")
    return pages


def _check_docx(data: bytes, settings: Settings) -> int:
    if not data.startswith(b"PK\x03\x04"):
        raise UploadRejected("BAD_FILE_TYPE", "File does not look like a DOCX document.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UploadRejected("BAD_FILE_TYPE", "ZIP archive is not a Word document.")
            infos = zf.infolist()
            if len(infos) > 2000:
                raise UploadRejected("ZIP_BOMB", "DOCX contains too many entries.")
            total = sum(i.file_size for i in infos)
            if total > settings.max_docx_uncompressed_mb * 1024 * 1024:
                raise UploadRejected("ZIP_BOMB", "DOCX expands to an unreasonable size.")
    except zipfile.BadZipFile as exc:
        raise UploadRejected("CORRUPT_FILE", "The DOCX file is corrupt.") from exc
    return 1


def _check_txt(data: bytes) -> int:
    if b"\x00" in data[:8192]:
        raise UploadRejected("BAD_FILE_TYPE", "File appears to be binary, not text.")
    from charset_normalizer import from_bytes

    best = from_bytes(data[:200_000]).best()
    if best is None:
        raise UploadRejected("BAD_ENCODING", "Could not detect the text encoding.")
    return 1


def validate_upload(filename: str, data: bytes, settings: Settings) -> ValidatedUpload:
    if not data:
        raise UploadRejected("EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise UploadRejected("FILE_TOO_LARGE", f"File exceeds {settings.max_upload_mb} MB.")
    safe = sanitize_filename(filename)
    kind = ALLOWED_EXTENSIONS.get(_extension(safe))
    if kind is None:
        raise UploadRejected("UNSUPPORTED_TYPE", "Only PDF, DOCX and TXT files are supported.")
    if kind == "pdf":
        pages = _check_pdf(data, settings)
    elif kind == "docx":
        pages = _check_docx(data, settings)
    else:
        pages = _check_txt(data)
    return ValidatedUpload(kind=kind, mime_type=MIME_TYPES[kind], safe_name=safe, page_count=pages)
