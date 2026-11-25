from conftest import space
from backend.app.db import now, uid
from backend.app.tutoring import compact_history, history_context, memory_context


def test_scoped_memory_and_pause(client):
    a, b = space(client), space(client)
    for scope, text in [("space", "课程A记忆"), ("partner", "仅伙伴记忆"), ("global", "通用偏好")]:
        assert (
            client.post("/api/memories", json={"scope": scope, "space_id": a["id"], "text": text}).status_code
            == 201
        )
    store = client.app.state.store
    assert {x["text"] for x in memory_context(store, a["id"])} == {"课程A记忆", "通用偏好"}
    assert {x["text"] for x in memory_context(store, b["id"])} == {"通用偏好"}
    assert {x["text"] for x in memory_context(store, None, True)} == {"仅伙伴记忆", "通用偏好"}
    client.put("/api/memory-settings", json={"paused": True})
    assert memory_context(store, a["id"]) == []


def test_memory_dedup_delete_and_source_guard(client):
    s = space(client)
    body = {"scope": "space", "space_id": s["id"], "text": "先给例子"}
    a = client.post("/api/memories", json=body).json()
    b = client.post("/api/memories", json=body).json()
    assert a["id"] == b["id"]
    client.delete("/api/memories/" + a["id"])
    assert client.get("/api/memories", params={"space_id": s["id"]}).json() == []
    assert client.app.state.store.one("SELECT active FROM memories WHERE id=?", (a["id"],))["active"] == 0
    assert client.post("/api/memories", json={**body, "source_id": "unknown"}).status_code == 400


def test_summary_preserves_archive_and_skips_private_messages(client):
    s = space(client)
    store = client.app.state.store
    for i in range(30):
        store.write(
            "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
            (uid(), s["id"], s["id"], "user", f"message-{i}", 0, now()),
        )
    store.write(
        "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
        (uid(), s["id"], s["id"], "user", "private-memory", 1, now()),
    )
    compact_history(store, s["id"])
    summary = store.one("SELECT * FROM summaries WHERE thread=?", (s["id"],))
    assert summary["watermark"]
    assert "private-memory" not in summary["text"]
    assert len(store.all("SELECT * FROM messages WHERE thread=?", (s["id"],))) == 31
    assert len(history_context(store, s["id"])["recent"]) <= 12
