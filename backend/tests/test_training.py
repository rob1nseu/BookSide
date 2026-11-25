import json
from conftest import action, space


def test_training_new_plan_can_pass_without_rewriting_old_assisted_attempt(client):
    s = space(client)
    action(client, s["id"])
    action(client, s["id"], "hint")
    action(client, s["id"], "answer", text="The function maps each input to one output.")
    action(client, s["id"], "train")
    detail = client.get("/api/spaces/" + s["id"]).json()["chapters"][0]
    assert detail["question_index"] == 0 and detail["question_count"] == 2
    action(client, s["id"], "answer", text="Each input must have exactly one output in its domain.")
    action(client, s["id"], "next")
    action(client, s["id"], "answer", text="结合定义与适用条件解释")
    detail = client.get("/api/spaces/" + s["id"]).json()["chapters"][0]
    assert detail["state"] == "通过当前检查"
    assert detail["attempts"][0]["assisted"] == 1


def test_numeric_tolerance_units_and_uncertain(client):
    s = space(client)
    action(client, s["id"])
    store = client.app.state.store
    question = store.one(
        "SELECT * FROM questions WHERE chapter_id=? ORDER BY position LIMIT 1", (s["current_chapter"],)
    )
    payload = json.loads(question["payload"])
    payload.update(kind="number", answer="4", tolerance=0.01, unit="m")
    store.write("UPDATE questions SET payload=? WHERE id=?", (json.dumps(payload), question["id"]))
    assert action(client, s["id"], "answer", text="4.005 m")["result"]["feedback"]["verdict"] == "correct"
    assert action(client, s["id"], "answer", text="4 cm")["result"]["feedback"]["verdict"] == "incorrect"
    assert (
        action(client, s["id"], "answer", text="I do not know")["result"]["feedback"]["verdict"]
        == "uncertain"
    )


def test_dispute_gets_only_one_recheck(client):
    s = space(client)
    action(client, s["id"])
    original = action(client, s["id"], "answer", text="not sure")["result"]["attempt_id"]
    client.post("/api/attempts/" + original + "/dispute")
    assert action(client, s["id"], "retry_grade")["status"] == "done"
    assert action(client, s["id"], "retry_grade")["status"] == "failed"
