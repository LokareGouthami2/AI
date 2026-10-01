"""HTTP-level tests of the full backend (offline LLM, in-memory vectors)."""

import pymupdf

from backend.editor import wdm
from backend.tests.conftest import wait_job


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["llm_provider"] == "offline"
    assert "sk-" not in r.text  # never leaks keys


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_upload_rejections(client):
    r = client.post("/api/documents/upload", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_TYPE"
    r = client.post("/api/documents/upload", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 415 and r.json()["error"]["code"] == "BAD_FILE_TYPE"


def test_upload_all_formats(client, pdf_bytes, docx_bytes, txt_bytes):
    for name, data in (("a.pdf", pdf_bytes), ("b.docx", docx_bytes), ("c.txt", txt_bytes)):
        r = client.post("/api/documents/upload", files={"file": (name, data)})
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["status"] == "uploaded" and doc["kind"] == name.split(".")[1]
        j = wait_job(client, client.post(f"/api/documents/{doc['id']}/extract").json())
        assert j["status"] == "succeeded" and j["result"]["pages"] >= 1
        j = wait_job(client, client.post(f"/api/documents/{doc['id']}/analyze").json())
        assert j["status"] == "succeeded", j
    listing = client.get("/api/documents").json()
    assert len(listing) >= 3


def test_analysis(client, analyzed_doc):
    r = client.get(f"/api/documents/{analyzed_doc}/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["words"] > 100
    assert body["stats"]["label_distribution"]["HEADING"] >= 3
    assert body["segments"][0]["label"] == "TITLE"


def test_generate_all_modes(client, analyzed_doc):
    for mode in ("preserve", "clean", "smart", "assignment", "exam", "simple"):
        j = wait_job(client, client.post(f"/api/documents/{analyzed_doc}/generate", json={"mode": mode}).json())
        assert j["status"] == "succeeded", j
        c = client.get(f"/api/documents/{analyzed_doc}/content").json()
        doc = wdm.parse(c["content"])
        assert doc.blocks
    versions = client.get(f"/api/documents/{analyzed_doc}/versions").json()
    assert len([v for v in versions if v["source"] == "ai_generated"]) == 6


def test_generate_requires_analysis(client, pdf_bytes):
    doc = client.post("/api/documents/upload", files={"file": ("z.pdf", pdf_bytes)}).json()
    j = wait_job(client, client.post(f"/api/documents/{doc['id']}/generate", json={"mode": "smart"}).json())
    assert j["status"] == "failed" and "Analyze" in j["error"]


def test_content_save_and_concurrency(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    doc = c["content"]
    doc["blocks"].append({"type": "paragraph", "content": [{"type": "text", "text": "Added by the user."}]})
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": doc, "base_revision": c["revision"]})
    assert r.status_code == 200
    new_rev = r.json()["revision"]
    assert new_rev == c["revision"] + 1
    # stale base revision → 409
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": doc, "base_revision": c["revision"]})
    assert r.status_code == 409 and r.json()["error"]["details"]["current_revision"] == new_rev
    # force overwrite allowed
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": doc, "base_revision": 0, "force": True})
    assert r.status_code == 200
    # saving identical content does not bump the revision
    rev = r.json()["revision"]
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": doc, "base_revision": rev})
    assert r.json()["revision"] == rev
    got = client.get(f"/api/documents/{generated_doc}/content").json()
    assert "Added by the user." in str(got["content"])


def test_invalid_content_rejected(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    bad = {"blocks": [{"type": "script", "content": "alert(1)"}]}
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": bad, "base_revision": c["revision"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_DOCUMENT"
    bad = {"blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "x", "marks": ["highlight"]}]}]}
    r = client.put(f"/api/documents/{generated_doc}/content", json={"content": bad, "base_revision": c["revision"]})
    assert r.status_code == 422


def test_versions_and_restore(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    v = client.post(f"/api/documents/{generated_doc}/versions", json={"label": "before edit"}).json()
    edited = {"title": "x", "blocks": [{"type": "paragraph", "content": [{"type": "text", "text": "Totally replaced"}]}]}
    client.put(f"/api/documents/{generated_doc}/content", json={"content": edited, "base_revision": c["revision"]})
    detail = client.get(f"/api/documents/{generated_doc}/versions/{v['version_number']}").json()
    assert detail["diff_to_current"]["removed"] > 0
    r = client.post(f"/api/documents/{generated_doc}/versions/{v['version_number']}/restore")
    assert r.status_code == 200
    assert "Totally replaced" not in str(r.json()["content"])
    sources = [x["source"] for x in client.get(f"/api/documents/{generated_doc}/versions").json()]
    assert "restored" in sources and "pre_restore" in sources


def test_preview_validate_render_download(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    rev = c["revision"]
    settings = {"style": "casual", "ink": "black", "paper": "grid"}
    p = client.post(f"/api/documents/{generated_doc}/preview", json={"expected_revision": rev, "settings": settings})
    assert p.status_code == 200, p.text
    prev = p.json()
    assert prev["page_count"] >= 1 and prev["quality"]["passed"]
    img = client.get(prev["pages"][0]["url"])
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    # cached: same content+settings → same render id
    assert client.post(f"/api/documents/{generated_doc}/preview", json={"expected_revision": rev, "settings": settings}).json()["render_id"] == prev["render_id"]
    v = client.post(f"/api/documents/{generated_doc}/validate", json={"expected_revision": rev}).json()
    assert v["passed"]
    j = wait_job(client, client.post(f"/api/documents/{generated_doc}/render", json={"expected_revision": rev, "settings": settings}).json())
    assert j["status"] == "succeeded", j
    assert j["result"]["status"] == "succeeded", j["result"]["quality"]
    d = client.get(j["result"]["download_url"])
    assert d.status_code == 200 and d.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=d.content, filetype="pdf") as pdf:
        assert pdf.page_count == j["result"]["page_count"]
        assert c["content_hash"] in (pdf.metadata.get("keywords") or "")
    latest = client.get(f"/api/documents/{generated_doc}/download")
    assert latest.status_code == 200


def test_stale_revision_is_refused(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    r = client.post(f"/api/documents/{generated_doc}/preview", json={"expected_revision": c["revision"] - 1 if c["revision"] > 1 else 99})
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_REVISION"


def test_download_refuses_render_of_old_content(client, generated_doc):
    c = client.get(f"/api/documents/{generated_doc}/content").json()
    j = wait_job(client, client.post(f"/api/documents/{generated_doc}/render", json={"expected_revision": c["revision"]}).json())
    assert j["result"]["status"] == "succeeded"
    doc = c["content"]
    doc["blocks"].append({"type": "paragraph", "content": [{"type": "text", "text": "late edit"}]})
    client.put(f"/api/documents/{generated_doc}/content", json={"content": doc, "base_revision": c["revision"]})
    r = client.get(f"/api/documents/{generated_doc}/download")
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_RENDER"


def test_render_settings_roundtrip_and_validation(client, generated_doc):
    r = client.put(f"/api/documents/{generated_doc}/render-settings", json={"style": "cursive", "font_size": 18})
    assert r.status_code == 200 and r.json()["style"] == "cursive"
    assert client.get(f"/api/documents/{generated_doc}/render-settings").json()["font_size"] == 18
    bad = client.put(f"/api/documents/{generated_doc}/render-settings", json={"font_size": 200})
    assert bad.status_code == 422
    bad = client.put(f"/api/documents/{generated_doc}/render-settings", json={"style": "comic-sans"})
    assert bad.status_code == 422
    styles = client.get("/api/handwriting/styles").json()
    assert {s["id"] for s in styles} >= {"neat", "cursive"}


def test_ask_flashcards_quiz(client, analyzed_doc):
    a = client.post(f"/api/documents/{analyzed_doc}/ask", json={"question": "What does unsupervised learning find?"}).json()
    assert a["grounded"] and "unlabelled" in a["answer"]
    assert a["citations"] and a["citations"][0]["pages"]
    no = client.post(f"/api/documents/{analyzed_doc}/ask", json={"question": "Who won the 1966 football world cup?"}).json()
    assert no["answer"] is None and not no["grounded"]

    fc = client.post(f"/api/documents/{analyzed_doc}/flashcards", json={"count": 5}).json()
    assert fc["cards"]
    cards = fc["cards"]
    cards[0]["answer"] = "Edited answer"
    saved = client.put(f"/api/documents/{analyzed_doc}/flashcards/{fc['id']}", json={"cards": cards}).json()
    assert saved["cards"][0]["answer"] == "Edited answer"
    assert client.get(f"/api/documents/{analyzed_doc}/flashcards").json()["cards"][0]["answer"] == "Edited answer"

    qz = client.post(f"/api/documents/{analyzed_doc}/quiz", json={"count": 4}).json()
    assert qz["questions"]
    qs = qz["questions"]
    qs[0]["question"] = "Edited question?"
    assert client.put(f"/api/documents/{analyzed_doc}/quiz/{qz['id']}", json={"questions": qs}).json()["questions"][0]["question"] == "Edited question?"
    qs[0]["options"] = ["a", "a", "b", "c"]
    assert client.put(f"/api/documents/{analyzed_doc}/quiz/{qz['id']}", json={"questions": qs}).status_code == 422


def test_delete_cleans_up(client, generated_doc):
    from pathlib import Path

    from backend.database.session import SessionLocal
    from backend.models.entities import Document

    with SessionLocal() as db:
        stored = db.get(Document, generated_doc).stored_path
    assert Path(stored).exists()
    assert client.delete(f"/api/documents/{generated_doc}").status_code == 204
    assert not Path(stored).exists()
    assert client.get(f"/api/documents/{generated_doc}").status_code == 404
    assert client.get(f"/api/documents/{generated_doc}/content").status_code == 404


def test_unknown_ids_404(client):
    assert client.get("/api/documents/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_api_token_enforced(monkeypatch, client):
    from pydantic import SecretStr

    from backend.config import get_settings

    monkeypatch.setattr(get_settings(), "api_token", SecretStr("s3cret"))
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"X-API-Token": "s3cret"}).status_code == 200


def test_empty_secrets_in_env_mean_unset(monkeypatch):
    """Regression: a .env copied from .env.example has `WRITEAI_API_TOKEN=`;
    that must not lock every request behind an empty token."""
    from backend.config import Settings

    monkeypatch.setenv("WRITEAI_API_TOKEN", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  ")
    s = Settings()
    assert s.api_token is None and s.anthropic_api_key is None


def test_single_container_serves_web_ui(tmp_path, monkeypatch):
    """WRITEAI_STATIC_DIR: the API also serves the built SPA (one-container deploy)."""
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setenv("WRITEAI_STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            home = c.get("/")
            assert home.status_code == 200 and "id=root" in home.text
            assert "script-src 'self'" in home.headers["content-security-policy"]
            # Client-side routes fall back to index.html.
            assert "id=root" in c.get("/documents/abc/editor").text
            js = c.get("/assets/app.js")
            assert js.text == "console.log(1)" and "immutable" in js.headers["cache-control"]
            # No escaping the build folder; API paths stay JSON.
            assert "nope" not in c.get("/..%2Fsecret.txt").text
            assert c.get("/api/health").json()["ok"] is True
            assert c.get("/api/nope").status_code == 404
            assert c.get("/api/health").headers["content-security-policy"].startswith("default-src 'none'")
    finally:
        monkeypatch.delenv("WRITEAI_STATIC_DIR")
        get_settings.cache_clear()
