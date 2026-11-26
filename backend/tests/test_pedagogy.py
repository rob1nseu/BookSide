import pytest
from pydantic import ValidationError
from backend.app.pedagogy import concept_summary, policy
from backend.app.model import Provider, ModelError
from backend.app.schemas import Question


def test_mastery_requires_distinct_unassisted_evidence():
    questions = [{"id": str(i), "prompt": "variant", "concept": "chain rule"} for i in range(2)]
    attempts = [{"question_id": "0", "feedback": {"verdict": "correct"}}]
    assert concept_summary(questions, attempts)[0]["state"] == "初步验证"
    attempts.append({"question_id": "1", "feedback": {"verdict": "correct"}, "assisted": True})
    assert concept_summary(questions, attempts)[0]["state"] == "初步验证"
    attempts[1]["assisted"] = False
    assert concept_summary(questions, attempts)[0]["state"] == "已验证"
    attempts.insert(0, {"question_id": "1", "feedback": {"verdict": "incorrect", "error_type": "condition"}})
    assert concept_summary(questions, attempts)[0]["errors"] == ["condition"]


def test_duplicate_options_rejected():
    with pytest.raises(ValidationError):
        Question(
            kind="choice",
            prompt="choose",
            answer="A",
            rubric="reason",
            hint="hint",
            options=["A", " A"],
            sources=["p"],
        )


def test_arithmetic_is_bounded_and_never_executes_code():
    from backend.app.arithmetic import value

    assert value("8/2") == value("4")
    assert value("__import__('os').system('echo unsafe')") is None
    assert value("2**99999") is None
    assert value("1/0") is None
    assert value("1e999") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["reject", "uncertain", "accept"])
async def test_audit_gates_publication(tmp_path, verdict):
    provider = Provider(tmp_path)
    calls = []

    async def generate(kind, context, progress):
        calls.append(kind)
        return (
            {"verdict": verdict, "reason": "evidence check"} if kind == "audit" else {"questions": []}
        ), {}

    provider._generate = generate

    async def progress(_):
        pass

    if verdict == "accept":
        result, usage = await provider.generate("lesson", {"evidence": []}, progress)
        assert usage["quality"] == "accept"
    else:
        with pytest.raises(ModelError):
            await provider.generate("lesson", {"evidence": []}, progress)
    assert calls == ["lesson", "audit"]
    assert policy("partner") == ""


@pytest.mark.asyncio
async def test_explicit_no_answer_never_calls_model(tmp_path):
    model = Provider(tmp_path)
    async def fail(*args):
        raise AssertionError("No network needed for an explicit non-answer")
    model._generate = fail
    result, _ = await model.generate("grade", {"answer": "我不知道"}, fail)
    assert result["verdict"] == "uncertain"


def test_upgrade_backs_up_existing_database(tmp_path):
    from backend.app.db import Store
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("DROP TABLE run_stages")
        db.execute("DELETE FROM migrations WHERE version=6")
    updated = Store(tmp_path)
    assert updated.one("SELECT version FROM migrations WHERE version=6")
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1


@pytest.mark.asyncio
async def test_action_budget_is_shared_and_reset():
    from backend.app.runtime import bounded_action, spend, budget
    @bounded_action
    async def action():
        for _ in range(4):
            spend("tools")
        with pytest.raises(ModelError):
            spend("tools")
    await action()
    assert budget.get() is None


@pytest.mark.asyncio
async def test_page_read_tool_uses_scoped_callback(tmp_path):
    import json
    provider = Provider(tmp_path)
    calls = []
    async def request(messages, progress, tools=None):
        if not calls:
            return {"_tool_calls": [{"id": "read", "type": "function", "function": {
                "name": "read_material_page", "arguments": json.dumps({"page_id": "p1"})}}]}, {}
        return {"text": "依据原页解释", "sources": ["p1"]}, {}
    def read(page_id):
        calls.append(page_id)
        return [{"id": page_id, "text": "原页定义"}]
    async def progress(_):
        pass
    provider.request = request
    result, _ = await provider.generate("reply", {"_search": lambda _: [], "_read_page": read}, progress)
    assert calls == ["p1"] and result["sources"] == ["p1"]
