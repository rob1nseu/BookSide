import asyncio
import json
import time

import pymupdf

from conftest import action, space, upload
from backend.app.documents import retrieve
from backend.app.outline import make_outline


def course_pdf(bookmarks=True):
    doc = pymupdf.open()
    page = doc.new_page()
    for y, text in [
        (70, "Chapter 1 Functions"),
        (120, "1.1 Sets"),
        (160, "SETS_ONLY: A set is a collection of distinct objects."),
        (280, "1.2 Functions"),
        (320, "FUNCTIONS_ONLY: Each input maps to exactly one output."),
    ]:
        page.insert_text((60, y), text)
    page = doc.new_page()
    page.insert_text((60, 40), "1.2 Functions", fontsize=9)  # running header
    page.insert_text((60, 120), "1.3 Inverse", fontsize=16)
    page.insert_text((60, 160), "INVERSE_ONLY: Invertible functions are one-to-one.")
    page = doc.new_page()
    page.insert_text((60, 120), "1.4 Elementary", fontsize=16)
    page.insert_text((60, 160), "ELEMENTARY_ONLY: Polynomials are elementary functions.")
    if bookmarks:
        doc.set_toc(
            [
                [1, "Chapter 1 Functions", 1],
                [2, "1.1 Sets", 1],
                [2, "1.2 Functions", 1],
                [2, "1.3 Inverse", 2],
                [2, "1.4 Elementary", 3],
            ]
        )
    return doc.tobytes()


def test_hierarchy_same_page_boundaries_and_no_repeated_headers(client):
    for bookmarks in (True, False):
        s = space(client, upload(client, course_pdf(bookmarks)))
        chapters = s["chapters"]
        assert [c["title"] for c in chapters] == [
            "Chapter 1 Functions",
            "1.1 Sets",
            "1.2 Functions",
            "1.3 Inverse",
            "1.4 Elementary",
        ]
        assert chapters[0]["is_group"] == 1
        assert all(c["parent_id"] == chapters[0]["id"] for c in chapters[1:])
        assert s["current_chapter"] == chapters[1]["id"]
        store = client.app.state.store
        local = retrieve(
            store,
            s["id"],
            "INVERSE_ONLY",
            store.one("SELECT * FROM chapters WHERE id=?", (chapters[1]["id"],)),
        )
        assert "SETS_ONLY" in local[0]["text"]
        assert "FUNCTIONS_ONLY" not in local[0]["text"]
        assert "INVERSE_ONLY" not in str(local)
        review = client.patch(f"/api/spaces/{s['id']}", json={"mode": "review"}).json()
        assert chapters[0]["id"] not in review["review_queue"]
        assert (
            client.patch(f"/api/spaces/{s['id']}", json={"chapter_id": chapters[0]["id"]}).status_code == 404
        )


def test_printed_toc_is_not_body_or_duplicate_chapters():
    pages = [
        dict(number=1, title="Contents", text="1.1 Sets ........ 1\n1.2 Functions ........ 1"),
        dict(
            number=2,
            title="Chapter 1 Functions",
            text="Chapter 1 Functions\n1.1 Sets\nSets content.\n1.2 Functions\nFunction content.",
        ),
        dict(number=3, title="1.2 Functions", text="1.2 Functions\nContinuation of the same section."),
    ]
    outline = make_outline(pages)
    assert len(outline) == 3
    assert all(item["page"] == 2 for item in outline)
    assert outline[1]["end_offset"] == pages[1]["text"].index("1.2 Functions")
    pages[0]["text"] = "1.1 Sets . . . . . 1\n1.2 Functions . . . . 1"
    supplemented = make_outline(pages, [[1, "Chapter 1 Functions", 2]])
    assert [s["title"] for s in supplemented] == ["Chapter 1 Functions", "1.1 Sets", "1.2 Functions"]


def test_sibling_preparation_and_prerequisites_before_teaching(client):
    s = space(client, upload(client, course_pdf()))
    target = s["chapters"][3]
    original = client.app.state.provider.generate
    calls = []

    async def capture(kind, context, progress):
        calls.append((kind, context))
        return await original(kind, context, progress)

    client.app.state.provider.generate = capture
    assert action(client, s["id"], chapter_id=target["id"], prepare_chapter=True)["status"] == "done"
    first = calls[0][1]
    assert first["chapter"]["title"] == "1.3 Inverse"
    assert [p["title"] for p in first["prerequisites"]] == ["1.1 Sets", "1.2 Functions"]
    for _ in range(100):
        detail = client.get(f"/api/spaces/{s['id']}").json()
        if all(c["lesson"] for c in detail["chapters"] if not c["is_group"]):
            break
        time.sleep(0.02)
    assert all(c["lesson"] for c in detail["chapters"] if not c["is_group"])
    assert detail["chapters"][1]["state"] == "未学习"
    assert detail["chapters"][0]["lesson"] is None


def test_foreground_preempts_preparation_and_stop_cancels_late_write(client):
    s = space(client, upload(client, course_pdf()))
    original = client.app.state.provider.generate
    calls = []

    async def delayed(kind, context, progress):
        calls.append(context["chapter"]["title"])
        if len(calls) > 1:
            await asyncio.sleep(0.5)
        return await original(kind, context, progress)

    client.app.state.provider.generate = delayed
    action(client, s["id"], prepare_chapter=True)
    time.sleep(0.3)
    assert action(client, s["id"], chapter_id=s["chapters"][3]["id"])["status"] == "done"
    assert client.post(f"/api/spaces/{s['id']}/preparation/stop").status_code == 200
    detail = client.get(f"/api/spaces/{s['id']}").json()
    assert all(c["preparation"] not in ("queued", "running") for c in detail["chapters"])
    assert detail["chapters"][3]["lesson"]


def test_option_reasoning_persisted_and_rechecked(client):
    s = space(client)
    action(client, s["id"])
    store = client.app.state.store
    q = store.one("SELECT * FROM questions WHERE chapter_id=? ORDER BY position", (s["current_chapter"],))
    payload = json.loads(q["payload"])
    payload.update(kind="choice", options=["A", "B"], answer="A")
    store.write("UPDATE questions SET payload=? WHERE id=?", (json.dumps(payload), q["id"]))
    original = client.app.state.provider.generate
    observed = []

    async def capture(kind, context, progress):
        if kind == "grade":
            observed.append(context)
            return dict(
                verdict="correct",
                explanation="The stated reasoning confuses inputs and outputs.",
                missing=["Check uniqueness"],
                next_step="Revisit the definition",
                sources=payload["sources"],
            ), {}
        return await original(kind, context, progress)

    client.app.state.provider.generate = capture
    result = action(
        client, s["id"], "answer", selected_option="B", text="Because an input can have two outputs."
    )
    assert result["result"]["feedback"]["verdict"] == "incorrect"
    assert observed[-1]["selected_option"] == "B"
    assert "two outputs" in observed[-1]["reasoning"]
    attempt_id = result["result"]["attempt_id"]
    client.post(f"/api/attempts/{attempt_id}/dispute")
    assert action(client, s["id"], "retry_grade")["status"] == "done"
    assert observed[-1]["reasoning"] == observed[0]["reasoning"]
    saved = store.one("SELECT * FROM attempts WHERE id=?", (attempt_id,))
    assert saved["selected_option"] == "B" and "two outputs" in saved["answer"]


def test_image_validation_transcription_and_no_attempt(client):
    s = space(client)
    doc = pymupdf.open(stream=course_pdf(), filetype="pdf")
    png = doc[0].get_pixmap().tobytes("png")
    response = client.post(f"/api/spaces/{s['id']}/answer-image", files={"file": ("answer.png", png)})
    assert response.status_code == 200 and response.json()["text"]
    assert client.app.state.store.all("SELECT * FROM attempts") == []
    assert (
        client.post(
            f"/api/spaces/{s['id']}/answer-image", files={"file": ("bad.png", b"not an image")}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/spaces/other/answer-image", files={"file": ("answer.png", png)}).status_code == 404
    )
    assert (
        client.post(
            f"/api/spaces/{s['id']}/answer-image", files={"file": ("big.png", b"x" * (5 * 1024 * 1024 + 1))}
        ).status_code
        == 413
    )


def test_numeric_expression_is_graded_as_math_not_mistaken_for_a_unit(client):
    s = space(client)
    action(client, s["id"])
    store = client.app.state.store
    question = store.one(
        "SELECT * FROM questions WHERE chapter_id=? ORDER BY position", (s["current_chapter"],)
    )
    payload = json.loads(question["payload"])
    payload.update(kind="number", answer="2", unit="")
    store.write("UPDATE questions SET payload=? WHERE id=?", (json.dumps(payload), question["id"]))
    calls = []

    async def grade(kind, context, progress):
        calls.append(context["answer"])
        return dict(
            verdict="correct",
            explanation="4 / 2 equals 2.",
            missing=[],
            next_step="Continue",
            sources=payload["sources"],
        ), {}

    client.app.state.provider.generate = grade
    result = action(client, s["id"], "answer", text="4/2")
    assert calls == ["4/2"]
    assert result["result"]["feedback"]["verdict"] == "correct"


def test_rebuild_preserves_old_records(client):
    s = space(client, upload(client, course_pdf()))
    action(client, s["id"])
    new = client.post(f"/api/spaces/{s['id']}/rebuild-outline").json()
    assert new["id"] != s["id"]
    assert client.get(f"/api/spaces/{s['id']}").json()["chapters"][1]["lesson"]
    assert client.get(f"/api/spaces/{new['id']}").json()["chapters"][1]["lesson"] is None


async def test_image_payload_uses_vision_blocks_without_text_budget_overflow(tmp_path):
    from backend.app.model import Provider

    provider = Provider(tmp_path)
    seen = []

    async def request(messages, *args):
        seen.extend(messages)
        return {"text": "x=2", "uncertain": False, "note": ""}, {}

    provider.request = request

    async def progress(_):
        pass

    result, usage = await provider.generate(
        "transcribe", {"_image": "data:image/png;base64," + "A" * 200000}, progress
    )
    assert result["text"] == "x=2"
    assert seen[1]["content"][1]["type"] == "image_url"
    assert usage["context_characters"] < 10000
