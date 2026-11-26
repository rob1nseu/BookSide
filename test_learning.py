import asyncio
import uuid

from conftest import action, finish, pdf_bytes, pptx_bytes, space, upload


def test_upload_parse_pdf_pptx_and_notes(client):
    pdf = upload(client)
    ppt = upload(client, pptx_bytes(), "slides.pptx")
    pages = client.get(f"/api/documents/{ppt['id']}/pages").json()
    assert "check the domain" in pages[0]["notes"]
    assert pages[0]["number"] == 1
    assert len(client.get(f"/api/documents/{pdf['id']}/pages").json()) == 2
    assert client.get(f"/api/documents/{pdf['id']}/file").content.startswith(b"%PDF")


def test_same_file_dedup_and_space_isolation(client):
    data = pdf_bytes()
    doc = upload(client, data)
    assert upload(client, data)["id"] == doc["id"]
    first, second = space(client, doc), space(client, doc)
    assert action(client, first["id"])["status"] == "done"
    assert client.get("/api/spaces/" + second["id"]).json()["chapters"][0]["lesson"] is None
    assert client.delete("/api/spaces/" + first["id"]).status_code == 200
    assert client.get("/api/documents/" + doc["id"] + "/file").status_code == 200


def test_learning_answers_hidden_and_progress(client):
    s = space(client)
    run = action(client, s["id"])
    assert run["status"] == "done", run
    assert "questions" not in run["result"]
    detail = client.get("/api/spaces/" + s["id"]).json()
    q = detail["chapters"][0]["question"]
    assert "answer" not in q and "rubric" not in q and "hint" not in q
    graded = action(client, s["id"], "answer", text="A function maps each input to exactly one output.")
    assert graded["status"] == "done", graded
    assert graded["result"]["feedback"]["verdict"] == "correct"
    action(client, s["id"], "next")
    result = action(client, s["id"], "answer", text="结合定义与适用条件解释")
    assert result["status"] == "done", result
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["state"] == "已掌握"


def test_hints_and_skips_not_independent_pass(client):
    s = space(client)
    action(client, s["id"])
    action(client, s["id"], "hint")
    action(client, s["id"], "answer", text="A function maps each input to exactly one output.")
    action(client, s["id"], "next")
    action(client, s["id"], "answer", text="结合定义与适用条件解释")
    chapter = client.get("/api/spaces/" + s["id"]).json()["chapters"][0]
    assert chapter["state"] != "已掌握"
    assert chapter["attempts"][0]["assisted"] == 1
    before = chapter["state"]
    action(client, s["id"], "skip")
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["state"] == before


def test_duplicate_action_exactly_once(client):
    s = space(client)
    body = {"action": "teach", "request_key": str(uuid.uuid4())}
    first = client.post(f"/api/spaces/{s['id']}/actions", json=body).json()
    second = client.post(f"/api/spaces/{s['id']}/actions", json=body).json()
    assert first == second
    assert finish(client, first["id"])["status"] == "done"
    assert len(client.get("/api/messages", params={"space_id": s["id"]}).json()) == 1


def test_cancel_late_generation_does_not_commit(client):
    s = space(client)
    original = client.app.state.provider.generate

    async def slow(*args):
        await asyncio.sleep(0.5)
        return await original(*args)

    client.app.state.provider.generate = slow
    run = client.post(
        f"/api/spaces/{s['id']}/actions", json={"action": "teach", "request_key": str(uuid.uuid4())}
    ).json()
    assert client.post("/api/runs/" + run["id"] + "/cancel").status_code == 200
    assert finish(client, run["id"])["status"] == "cancelled"
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["lesson"] is None


def test_cross_space_chapter_rejected(client):
    first, second = space(client), space(client)
    response = client.post(
        f"/api/spaces/{first['id']}/actions",
        json={"action": "teach", "chapter_id": second["current_chapter"], "request_key": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_review_restores_original_chapter(client):
    s = space(client)
    chapter = s["chapters"][1]["id"]
    client.patch("/api/spaces/" + s["id"], json={"chapter_id": chapter})
    review = client.patch("/api/spaces/" + s["id"], json={"mode": "review"}).json()
    assert review["mode"] == "review"
    restored = client.patch("/api/spaces/" + s["id"], json={"mode": "learn"}).json()
    assert restored["current_chapter"] == chapter


def test_disputed_grade_removed_from_state(client):
    s = space(client)
    action(client, s["id"])
    result = action(client, s["id"], "answer", text="short")
    assert result["result"]["feedback"]["verdict"] == "partial"
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["state"] == "需要巩固"
    client.post("/api/attempts/" + result["result"]["attempt_id"] + "/dispute")
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["state"] == "已学习，待验证"
    assert action(client, s["id"], "retry_grade")["status"] == "done"


def test_partner_has_no_course_evidence_or_progress(client):
    s = space(client)
    contexts = []
    original = client.app.state.provider.generate

    async def capture(kind, context, progress):
        contexts.append(context)
        return await original(kind, context, progress)

    client.app.state.provider.generate = capture
    response = client.post(
        "/api/partner/actions",
        json={"action": "partner", "text": "今天累了", "request_key": str(uuid.uuid4())},
    )
    assert finish(client, response.json()["id"])["status"] == "done"
    assert contexts[0]["evidence"] == [] and "chapter" not in contexts[0]
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["state"] == "未学习"
    assert client.get("/api/messages", params={"space_id": s["id"]}).json() == []


def test_invalid_citation_never_commits(client):
    s = space(client)
    original = client.app.state.provider.generate

    async def invalid(kind, context, progress):
        value, usage = await original(kind, context, progress)
        value["sources"] = ["foreign-source"]
        return value, usage

    client.app.state.provider.generate = invalid
    assert action(client, s["id"])["status"] == "failed"
    assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["lesson"] is None


def test_scan_and_malformed_file_not_success(client):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    response = client.post("/api/documents", files={"file": ("scan.pdf", doc.tobytes())})
    import time

    for _ in range(100):
        d = next(d for d in client.get("/api/documents").json() if d["id"] == response.json()["id"])
        if d["status"] == "failed":
            break
        time.sleep(0.02)
    assert d["status"] == "failed"
    assert client.post("/api/documents", files={"file": ("bad.pdf", b"not pdf")}).status_code == 400
    assert client.post("/api/documents", files={"file": ("code.exe", b"payload")}).status_code == 400


def test_no_key_keeps_documents_usable(client):
    client.app.state.provider.demo = False
    client.app.state.provider.config["key"] = ""
    s = space(client)
    result = action(client, s["id"])
    assert result["status"] == "failed"
    assert "尚未配置" in result["error"]
    assert client.get("/api/documents").status_code == 200


def test_origin_and_csrf_boundary(client):
    assert client.post("/api/spaces", headers={"Origin": "https://evil.example"}, json={}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    client.headers.pop("x-learnest")
    assert client.post("/api/settings/check").status_code == 403


def test_key_never_returned_or_exported(client):
    fake = "fixture-secret-not-a-real-key"
    response = client.put("/api/settings", json={"model": "deepseek-flash", "key": fake})
    assert fake not in response.text
    assert fake not in client.get("/api/settings").text
    assert fake not in client.get("/api/diagnostics").text
