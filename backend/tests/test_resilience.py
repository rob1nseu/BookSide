import asyncio
import json

import httpx
import pytest

from backend.app.model import ModelError, Provider
from backend.app.model_json import OutputError, parse_output


@pytest.mark.parametrize("raw,expected", [
    ('```json\n{"text":"ok", "sources":[],}\n```', "ok"),
    (r'{"text":"$\frac{1}{2}+\theta+\alpha$", "sources":[]}', r'$\frac{1}{2}+\theta+\alpha$'),
    (json.dumps({"text": "first\nsecond\tcolumn", "sources": []}), "first\nsecond\tcolumn"),
    (json.dumps({"text": r'$\frac{a}{b}$ and "quoted"', "sources": []}), r'$\frac{a}{b}$ and "quoted"'),
])
def test_conservative_output_repair(raw, expected):
    assert parse_output(raw)["text"] == expected


@pytest.mark.parametrize("raw", ['   ', '{"text":"partial', '[1,2]', '{"text":1} {"text":2}'])
def test_never_guess_truncated_or_ambiguous_output(raw):
    with pytest.raises(OutputError):
        parse_output(raw)


def stream(text):
    return 'data: ' + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}) + '\n\ndata: [DONE]\n\n'


@pytest.mark.asyncio
async def test_transient_retry_then_empty_output_repair(tmp_path, monkeypatch):
    provider = Provider(tmp_path)
    provider.config["key"] = "fixture-secret"
    attempts, progress = [], []
    original = httpx.AsyncClient

    def handle(request):
        attempts.append(json.loads(request.content))
        if len(attempts) == 1:
            return httpx.Response(503, text="private provider internals")
        return httpx.Response(200, text=stream(" " if len(attempts) == 2 else '{"text":"recovered","sources":[]}'))

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))

    async def update(value):
        assert provider.active_calls == 1
        progress.append(value)

    result, _ = await provider.generate("reply", {}, update)
    assert result["text"] == "recovered"
    assert len(attempts) == 3
    assert progress.count("有点小问题，等等哈...") >= 2
    assert "empty JSON" in attempts[-1]["messages"][-1]["content"]
    assert provider.active_calls == 0 and provider.last_activity > 0


@pytest.mark.asyncio
async def test_schema_repairs_bounded_and_actionable(tmp_path):
    provider, attempts = Provider(tmp_path), []

    async def request(messages, *_):
        attempts.append(list(messages))
        return {"sources": []}, {}

    async def progress(_):
        pass

    provider.request = request
    with pytest.raises(ModelError, match="还没准备好"):
        await provider.generate("reply", {}, progress)
    assert len(attempts) == 3
    assert '"text"' in attempts[-1][-1]["content"]
    assert provider.active_calls == 0


@pytest.mark.asyncio
async def test_cancel_resets_activity_without_retry(tmp_path):
    provider = Provider(tmp_path)
    started = asyncio.Event()

    async def request(*_):
        started.set()
        await asyncio.Event().wait()

    async def progress(_):
        pass

    provider.request = request
    task = asyncio.create_task(provider.generate("reply", {}, progress))
    await started.wait()
    assert provider.active_calls == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.active_calls == 0


def test_activity_endpoint_has_no_private_content(client):
    value = client.get("/api/companion/activity").json()
    assert value == {"active": 0, "last_activity": 0}
    assert client.post("/api/companion/open").json() == {"existing": False}


@pytest.mark.asyncio
async def test_lesson_is_regenerated_after_format_repairs_fail(tmp_path):
    from backend.app.model import demo_response
    provider = Provider(tmp_path)
    context = {"chapter": {"title": "Functions"}, "evidence": [{"id": "p1", "text": "A function maps inputs to outputs."}]}
    calls, statuses = [], []

    async def request(messages, *_):
        calls.append(messages)
        if len(calls) <= 3:
            raise OutputError("empty JSON output", "")
        if len(calls) == 4:
            return demo_response("lesson", context), {}
        return {"verdict": "accept", "reason": "consistent"}, {}

    async def progress(text):
        statuses.append(text)

    provider.request = request
    result, usage = await provider.generate("lesson", context, progress)
    assert result["sources"] == ["p1"]
    assert usage["regenerations"] == 1 and len(calls) == 5
    assert "有点小问题，等等哈..." in statuses
    assert not any("JSON" in s or "核验" in s for s in statuses)


@pytest.mark.asyncio
async def test_rejected_lesson_is_revised_automatically_with_original_evidence(tmp_path):
    provider = Provider(tmp_path)
    candidates, messages = [], []
    evidence = [{"id": "p1", "text": "x squared has derivative 2x"}]

    async def generate(kind, context, progress):
        if kind == "audit":
            return {"verdict": "reject" if len(candidates) == 1 else "accept", "reason": "Fix the derivative"}, {}
        candidates.append(context.copy())
        await progress("正在准备学习内容…")
        return {"title": "revised" if len(candidates) == 2 else "first"}, {}

    async def progress(text):
        messages.append(text)

    provider._generate = generate
    result, usage = await provider.generate("lesson", {"evidence": evidence}, progress)
    assert result["title"] == "revised" and usage["quality"] == "accept"
    assert candidates[1]["evidence"] == evidence
    assert candidates[1]["revision"]["issues"] == "Fix the derivative"
    assert messages[-1] == "有点小问题，等等哈..."
