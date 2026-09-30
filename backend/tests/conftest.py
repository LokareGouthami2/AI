import os
import tempfile

# Configure the app for tests BEFORE any backend module is imported.
_TMP = tempfile.mkdtemp(prefix="writeai-test-")
os.environ.update(
    WRITEAI_ENV="test",
    WRITEAI_DATA_DIR=_TMP,
    WRITEAI_LLM_PROVIDER="mock",
    WRITEAI_EMBEDDING_BACKEND="hashing",
)
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.tests.fixtures.builders import build_docx, build_pdf, build_scanned_pdf, build_txt  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def pdf_bytes() -> bytes:
    return build_pdf()


@pytest.fixture(scope="session")
def scanned_pdf_bytes() -> bytes:
    return build_scanned_pdf()


@pytest.fixture(scope="session")
def docx_bytes() -> bytes:
    return build_docx()


@pytest.fixture(scope="session")
def txt_bytes() -> bytes:
    return build_txt()


def wait_job(client, job: dict) -> dict:
    """Jobs run inline in tests; fetch the final state."""
    r = client.get(f"/api/jobs/{job['id']}")
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def analyzed_doc(client, pdf_bytes):
    """Upload + extract + analyze the sample PDF; returns the document id."""
    r = client.post("/api/documents/upload", files={"file": ("ml_notes.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    assert wait_job(client, client.post(f"/api/documents/{doc_id}/extract").json())["status"] == "succeeded"
    assert wait_job(client, client.post(f"/api/documents/{doc_id}/analyze").json())["status"] == "succeeded"
    return doc_id


@pytest.fixture
def generated_doc(client, analyzed_doc):
    job = wait_job(client, client.post(f"/api/documents/{analyzed_doc}/generate", json={"mode": "smart"}).json())
    assert job["status"] == "succeeded", job
    return analyzed_doc
