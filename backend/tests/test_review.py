import copy
import asyncio
import io
import json

import pytest
from PIL import Image

from backend.app.model import ModelError
from backend.app.review import validate_map
from conftest import action, space, upload
from test_human_feedback import course_pdf
from conftest import finish


def get_review(client, s):
    response = client.get(f"/api/spaces/{s['id']}/review", params={"chapter_id": s["current_chapter"]})
    assert response.status_code == 200, response.text
    return response.json()


def review_action(client, s, kind, **kwargs):
    current = get_review(client, s)["session"]
    args = dict(chapter_id=s["current_chapter"])
    if current:
        args.update(session_id=current["id"], question_id=(current["question"] or {}).get("id"))
    args.update(kwargs)
    return action(client, s["id"], kind, **args)


def start_review(client, s):
    assert review_action(client, s, "review_map")["status"] == "done"
    assert review_action(client, s, "review_start")["status"] == "done"
    return get_review(client, s)


def test_review_is_independent_cached_and_source_bound(client):
    s = space(client, upload(client, course_pdf()))
    store = client.app.state.store
    before = store.all("SELECT * FROM chapters WHERE space_id=?", (s["id"],))
    data = start_review(client, s)
    assert len(data["map"]["nodes"]) == 4
    assert len({n["chapter_id"] for n in data["map"]["nodes"]}) == 4
    assert "answer" not in data["session"]["question"]
    assert "hint" not in data["session"]["question"]
    assert "rubric" not in data["session"]["question"]
    original = client.app.state.provider.generate

    async def no_generate(*args):
        raise AssertionError("The cached map must not be regenerated")

    client.app.state.provider.generate = no_generate
    assert review_action(client, s, "review_map")["status"] == "done"
    client.app.state.provider.generate = original
    assert get_review(client, s)["session"]["id"] == data["session"]["id"]
    assert review_action(client, s, "review_start")["status"] == "failed"
    assert (
        review_action(client, s, "review_answer", text="Definition plus conditions and an example.")["status"]
        == "done"
    )
    data = get_review(client, s)
    assert "本轮已验证" in data["round_states"].values()
    assert review_action(client, s, "review_next")["status"] == "done"
    assert review_action(client, s, "review_help", text="Explain the wording")["status"] == "done"
    assert (
        review_action(client, s, "review_answer", text="A definition with all the conditions and examples.")[
            "status"
        ]
        == "done"
    )
    data = get_review(client, s)
    assert data["session"]["attempts"][-1]["assisted"] is True
    assert data["round_states"][data["session"]["question"]["node_id"]] == "需巩固"
    assert review_action(client, s, "review_next")["status"] == "done"
    skipped = get_review(client, s)["session"]["question"]["node_id"]
    assert review_action(client, s, "review_next")["status"] == "done"
    data = get_review(client, s)
    assert data["session"]["status"] == "done"
    assert skipped not in data["round_states"]
    assert data["session"]["attempts"][-1]["skipped"] is True
    assert store.all("SELECT * FROM chapters WHERE space_id=?", (s["id"],)) == before
    assert store.all("SELECT * FROM attempts") == []
    # A new round has its own evidence of mastery; prior results only guide selection.
    assert review_action(client, s, "review_start")["status"] == "done"
    assert get_review(client, s)["round_states"] == {}


@pytest.mark.parametrize(
    "damage", ["duplicate", "cycle", "depth", "source", "chapter", "missing", "reserved"]
)
def test_map_validation_rejects_invalid_model_output(damage):
    sections = [{"id": "section", "sources": ["page"]}]
    node = dict(
        id="a", parent_id=None, label="Concept", summary="Meaning", chapter_id="section", sources=["page"]
    )
    payload = dict(title="Chapter", nodes=[node])
    if damage == "duplicate":
        payload["nodes"].append(copy.deepcopy(node))
    elif damage == "cycle":
        node["parent_id"] = "a"
    elif damage == "depth":
        for ident, parent in [("b", "a"), ("c", "b"), ("d", "c")]:
            payload["nodes"].append(dict(node, id=ident, parent_id=parent))
    elif damage == "source":
        node["sources"] = ["foreign-page"]
    elif damage == "chapter":
        node["chapter_id"] = "foreign-chapter"
    elif damage == "missing":
        sections.append({"id": "omitted", "sources": ["page2"]})
    elif damage == "reserved":
        node["id"] = "__root"
    with pytest.raises(ModelError):
        validate_map(payload, sections, [])


def test_review_rejects_stale_question_and_foreign_session(client):
    s = space(client, upload(client, course_pdf()))
    data = start_review(client, s)
    old = data["session"]["question"]["id"]
    review_action(client, s, "review_next")
    assert (
        review_action(client, s, "review_answer", question_id=old, text="a stale answer")["status"]
        == "failed"
    )
    other = space(client)
    review_action(client, other, "review_map")
    assert (
        review_action(
            client, other, "review_help", session_id=data["session"]["id"], question_id=old, text="help"
        )["status"]
        == "failed"
    )
    assert get_review(client, s)["session"]["attempts"] == [get_review(client, s)["session"]["attempts"][0]]


def test_lecture_question_and_node_help_keep_separate_contexts(client):
    s = space(client)
    action(client, s["id"])
    store = client.app.state.store
    q = store.one("SELECT id FROM questions WHERE chapter_id=? ORDER BY position", (s["current_chapter"],))[
        "id"
    ]
    captured = []
    original = client.app.state.provider.generate

    async def capture(kind, context, progress):
        captured.append(copy.deepcopy({k: v for k, v in context.items() if not k.startswith("_")}))
        return await original(kind, context, progress)

    client.app.state.provider.generate = capture
    assert (
        action(client, s["id"], "ask_question", question_id=q, text="question-only marker")["status"]
        == "done"
    )
    assert store.all("SELECT * FROM attempts") == []
    assert captured[-1]["current_question"]["id"] == q
    assert action(client, s["id"], "ask", text="lecture-only marker")["status"] == "done"
    assert "current_question" not in captured[-1]
    assert "question-only marker" not in json.dumps(captured[-1]["history"])
    lecture = client.get(
        "/api/messages", params={"space_id": s["id"], "chapter_id": s["current_chapter"]}
    ).json()
    question = client.get("/api/messages", params={"space_id": s["id"], "question_id": q}).json()
    assert lecture[0]["text"] == "lecture-only marker"
    assert question[0]["text"] == "question-only marker"
    assert (
        action(client, s["id"], "answer", question_id=q, text="A complete definition and conditions.")[
            "status"
        ]
        == "done"
    )
    assert store.one("SELECT assisted FROM attempts")["assisted"] == 1
    data = start_review(client, s)
    node = data["map"]["nodes"][0]["id"]
    assert review_action(client, s, "review_node", node_id=node, text="node-only marker")["status"] == "done"
    rows = client.get(
        "/api/messages", params={"space_id": s["id"], "chapter_id": s["current_chapter"], "node_id": node}
    ).json()
    assert rows[0]["text"] == "node-only marker"
    assert review_action(client, s, "review_help", text="review-only marker")["status"] == "done"
    session = data["session"]
    rows = client.get(
        "/api/messages",
        params={"space_id": s["id"], "session_id": session["id"], "question_id": session["question"]["id"]},
    ).json()
    assert rows[0]["text"] == "review-only marker"
    exported = client.get(f"/api/spaces/{s['id']}/export").json()
    assert {"lecture-only marker", "question-only marker", "node-only marker", "review-only marker"} <= {
        m["text"] for m in exported["messages"]
    }
    assert exported["review_maps"] and exported["review_sessions"]


def test_original_image_reaches_grader_without_transcription_and_is_scoped(client):
    s = space(client)
    action(client, s["id"])
    store = client.app.state.store
    q = store.one("SELECT id FROM questions WHERE chapter_id=? ORDER BY position", (s["current_chapter"],))[
        "id"
    ]
    png = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(png, "PNG")
    observed = []
    original = client.app.state.provider.generate

    async def capture(kind, context, progress):
        observed.append((kind, context.get("_image")))
        return await original(kind, context, progress)

    client.app.state.provider.generate = capture
    response = client.post(
        f"/api/spaces/{s['id']}/answer-image",
        params={"target": q, "recognize": False},
        files={"file": ("answer.png", png.getvalue())},
    )
    assert response.status_code == 200, response.text
    image_id = response.json()["id"]
    assert observed == []
    assert client.get(f"/api/spaces/{s['id']}/attachments/{image_id}").content == png.getvalue()
    result = action(client, s["id"], "answer", question_id=q, attachment_id=image_id)
    assert result["status"] == "done", result
    assert observed[-1][0] == "grade" and observed[-1][1].startswith("data:image/png;base64,")

    assert store.one("SELECT attachment_id FROM attempts")["attachment_id"] == image_id
    action(client, s["id"], "next", question_id=q)
    assert (
        action(client, s["id"], "answer", attachment_id=image_id, selected_option="只背一个词")["status"]
        == "failed"
    )
    other = space(client)
    assert client.get(f"/api/spaces/{other['id']}/attachments/{image_id}").status_code == 404
    data = start_review(client, s)
    target = data["session"]["question"]["id"]
    response = client.post(
        f"/api/spaces/{s['id']}/answer-image",
        params={"target": target, "recognize": False},
        files={"file": ("answer.png", png.getvalue())},
    )
    assert response.status_code == 200
    result = review_action(client, s, "review_answer", attachment_id=response.json()["id"])
    assert result["status"] == "done", result
    assert observed[-1][0] == "grade" and observed[-1][1].startswith("data:image/png;base64,")
    assert client.delete(f"/api/spaces/{s['id']}").status_code == 200
    assert store.all("SELECT * FROM attachments WHERE space_id=?", (s["id"],)) == []
    assert store.all("SELECT * FROM review_sessions WHERE space_id=?", (s["id"],)) == []


def test_default_teaching_does_not_queue_the_chapter_and_status_is_lightweight(client):
    s = space(client, upload(client, course_pdf()))
    assert action(client, s["id"])["status"] == "done"
    chapters = client.get(f"/api/spaces/{s['id']}?compact=true").json()["chapters"]
    assert all(c["preparation"] not in ("queued", "running") for c in chapters)
    assert all(
        c["lesson"] is None and c["attempts"] == [] for c in chapters if c["id"] != s["current_chapter"]
    )
    status = client.get(f"/api/spaces/{s['id']}/status").json()
    assert len(status["chapters"]) == len(chapters)
    assert all("lesson" not in c and "attempts" not in c for c in status["chapters"])
    assert len(json.dumps(status)) < len(json.dumps(chapters))


def test_cancelled_review_cannot_commit_late_provider_result(client):
    s = space(client)
    original = client.app.state.provider.generate

    async def delayed(kind, context, progress):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass  # Simulate a provider that returns after cancellation.
        return await original(kind, context, progress)

    client.app.state.provider.generate = delayed
    body = {"action": "review_map", "chapter_id": s["current_chapter"], "request_key": "same-map-request"}
    first = client.post(f"/api/spaces/{s['id']}/actions", json=body).json()
    again = client.post(f"/api/spaces/{s['id']}/actions", json=body).json()
    assert again["id"] == first["id"]
    client.post(f"/api/runs/{first['id']}/cancel")
    assert finish(client, first["id"])["status"] == "cancelled"
    assert get_review(client, s)["map"] is None


def test_invalid_review_does_not_save_partial_map(client):
    s = space(client)
    original = client.app.state.provider.generate

    async def broken(kind, context, progress):
        value, usage = await original(kind, context, progress)
        value["nodes"][0]["sources"] = ["outside-space"]
        return value, usage

    client.app.state.provider.generate = broken
    assert review_action(client, s, "review_map")["status"] == "failed"
    assert get_review(client, s)["map"] is None
