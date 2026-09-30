"""Critical acceptance test (docs/design.md §12.4), backend half.

The browser half (real keyboard/undo/redo in TipTap) lives in
frontend/e2e/acceptance.spec.js and ends by running the same PDF checks.
Here the editor operations are applied to the WDM exactly as the editor's
converter would serialise them.
"""

import copy

import pymupdf

from backend.editor import wdm
from backend.quality.pdf_inspect import count_ink_underlines, pdf_lines
from backend.tests.conftest import wait_job


def _texts(content: dict) -> list[str]:
    return [wdm.block_plain_text(b) for b in wdm.iter_text_blocks(wdm.parse(content))]


def test_critical_acceptance_flow(client, pdf_bytes):
    # 1. Upload a PDF
    doc = client.post("/api/documents/upload", files={"file": ("ml.pdf", pdf_bytes, "application/pdf")}).json()
    did = doc["id"]
    assert wait_job(client, client.post(f"/api/documents/{did}/extract").json())["status"] == "succeeded"
    assert wait_job(client, client.post(f"/api/documents/{did}/analyze").json())["status"] == "succeeded"
    # 2. Generate Smart Notes
    assert wait_job(client, client.post(f"/api/documents/{did}/generate", json={"mode": "smart"}).json())["status"] == "succeeded"
    # 3. Open the editable document
    head = client.get(f"/api/documents/{did}/content").json()
    content = copy.deepcopy(head["content"])
    blocks = content["blocks"]

    # 4. Delete an entire paragraph (the first top-level paragraph with text)
    victim_idx = next(i for i, b in enumerate(blocks) if b["type"] == "paragraph" and b.get("content"))
    deleted_text = "".join(n.get("text", "") for n in blocks[victim_idx]["content"])
    del blocks[victim_idx]
    # 5. Press Enter twice → one empty paragraph between existing text and the new paragraph
    blocks.insert(victim_idx, {"type": "paragraph", "content": []})
    # 6. Add a new paragraph
    new_para = "This paragraph was typed by the student after pressing Enter twice."
    blocks.insert(victim_idx + 1, {"type": "paragraph", "content": [{"type": "text", "text": new_para}]})
    # 7. Add a heading
    blocks.insert(victim_idx + 2, {"type": "heading", "level": 2, "content": [{"type": "text", "text": "My Own Heading"}]})
    # 8. Modify several sentences
    modified = 0
    for b in blocks:
        for n in b.get("content", []) or []:
            if n.get("type") == "text" and "data" in n["text"] and modified < 2:
                n["text"] = n["text"].replace("data", "DATA-EDITED", 1)
                modified += 1
    for b in blocks:
        for item in b.get("items", []) or []:
            for ib in item["blocks"]:
                for n in ib.get("content", []) or []:
                    if n.get("type") == "text" and modified < 3:
                        n["text"] = n["text"] + " (revised)"
                        modified += 1
    assert modified >= 2
    # 9-10. Undo then redo is net-zero on the final document state; the editor
    # e2e test verifies the key handling. Here we save an intermediate state
    # and then the redone state to prove only the latest is used.
    intermediate = copy.deepcopy(content)
    intermediate["blocks"].append({"type": "paragraph", "content": [{"type": "text", "text": "UNDONE TEXT SHOULD NOT APPEAR"}]})
    r = client.put(f"/api/documents/{did}/content", json={"content": intermediate, "base_revision": head["revision"]})
    assert r.status_code == 200
    # 11. Save the document (latest state = after undo removed the extra text)
    r = client.put(f"/api/documents/{did}/content", json={"content": content, "base_revision": r.json()["revision"]})
    assert r.status_code == 200
    saved = r.json()
    # 12. Open Preview
    p = client.post(f"/api/documents/{did}/preview", json={"expected_revision": saved["revision"]}).json()
    assert p["revision"] == saved["revision"] and p["content_hash"] == saved["content_hash"]
    assert p["quality"]["passed"], p["quality"]["errors"]
    # 13. Generate the handwritten PDF
    j = wait_job(client, client.post(f"/api/documents/{did}/render", json={"expected_revision": saved["revision"]}).json())
    assert j["result"]["status"] == "succeeded", j["result"]["quality"]
    pdf = client.get(j["result"]["download_url"]).content

    # 14. Verify
    lines = [(ln["page"], ln["y"], ln["text"], ln["size"]) for ln in pdf_lines(pdf)]
    all_text = " ".join(t for _, _, t, _ in lines)
    assert deleted_text[:40] not in all_text, "deleted paragraph must be absent"
    assert new_para in all_text, "new paragraph must exist"
    assert "UNDONE TEXT SHOULD NOT APPEAR" not in all_text, "undone edits must not render"
    assert all_text.count("DATA-EDITED") >= 1 and "(revised)" in all_text, "modified sentences present"
    heading = next(ln for ln in lines if ln[2] == "My Own Heading")
    body_size = sorted(sz for _, _, t, sz in lines if t.startswith("This paragraph was typed"))[0]
    assert heading[3] > body_size * 1.1, "heading exists and is visually larger"
    # extra line break preserved: the gap above the new paragraph is larger than a normal line pitch
    new_line = next(ln for ln in lines if ln[2].startswith("This paragraph was typed"))
    same_page_above = [ln for ln in lines if ln[0] == new_line[0] and ln[1] < new_line[1]]
    if same_page_above:
        from backend.layout.settings import RenderSettings

        s = RenderSettings()
        gap = new_line[1] - max(y for _, y, _, _ in same_page_above)
        assert gap >= 2 * s.font_size * s.line_spacing - 1, f"blank line not preserved (gap {gap:.1f})"
    assert count_ink_underlines(pdf) == 0, "no unexpected underline"
    # final formatting matches the latest editor state (hash in PDF metadata)
    with pymupdf.open(stream=pdf, filetype="pdf") as d:
        assert f"writeai:content_hash={saved['content_hash']}" in d.metadata["keywords"]
    assert j["result"]["quality"]["pdf_audit"]["passed"]
