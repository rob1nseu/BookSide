from fastapi.testclient import TestClient
from conftest import action, space
from backend.app.db import now, uid
from backend.app.main import create_app
from backend.app.memory import consolidate
from backend.app.model import Provider


def test_restart_preserves_learning_and_interrupts_old_runs(tmp_path):
    provider = Provider(tmp_path, demo=True)
    with TestClient(create_app(tmp_path, provider), headers={"X-LearNest": "1"}) as client:
        s = space(client)
        assert action(client, s["id"])["status"] == "done"
        store = client.app.state.store
        store.write(
            "INSERT INTO runs(id,scope,space_id,chapter_id,action,request_key,status,created) VALUES(?,?,?,?,?,?,?,?)",
            (
                "interrupted-test",
                s["id"],
                s["id"],
                s["current_chapter"],
                "ask",
                "restart-key",
                "running",
                now(),
            ),
        )
    with TestClient(create_app(tmp_path, provider)) as client:
        assert client.get("/api/spaces/" + s["id"]).json()["chapters"][0]["lesson"] is not None
        assert client.get("/api/runs/interrupted-test").json()["status"] == "interrupted"


async def test_memory_delete_during_generation_cannot_resurrect(client):
    s = space(client)
    store = client.app.state.store
    source_id = uid()
    store.write(
        "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
        (source_id, s["id"], s["id"], "user", "请先举例", 0, now()),
    )
    memory = client.post(
        "/api/memories",
        json={"scope": "space", "space_id": s["id"], "text": "先举例", "source_id": source_id},
    ).json()

    class Delayed:
        async def generate(self, *args):
            client.delete("/api/memories/" + memory["id"])
            return {
                "summary": "先举例",
                "source_ids": [source_id],
                "items": [{"text": "用户喜欢先看例子", "source_id": source_id}],
            }, {}

    await consolidate(store, Delayed(), s["id"], s["id"])
    assert client.get("/api/memories", params={"space_id": s["id"]}).json() == []
    assert store.one("SELECT * FROM summaries WHERE thread=?", (s["id"],)) is None


async def test_memory_rejects_assistant_claim_as_user_fact(client):
    s = space(client)
    store = client.app.state.store
    source_id = uid()
    store.write(
        "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
        (source_id, s["id"], s["id"], "assistant", "你擅长数学", 0, now()),
    )

    class Bad:
        async def generate(self, *args):
            return {
                "summary": "擅长数学",
                "source_ids": [source_id],
                "items": [{"text": "擅长数学", "source_id": source_id}],
            }, {}

    await consolidate(store, Bad(), s["id"], s["id"])
    assert client.get("/api/memories", params={"space_id": s["id"]}).json() == []
