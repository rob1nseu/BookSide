import json
import pytest
import httpx
from backend.app.model import Provider, ModelError


async def noop(_):
    pass


@pytest.mark.asyncio
async def test_invalid_json_repairs_once(tmp_path):
    model = Provider(tmp_path)
    calls = []

    async def request(messages, progress, tools=None):
        calls.append(messages.copy())
        if len(calls) == 1:
            raise ValueError("bad json")
        return {"text": "valid", "sources": []}, {}

    model.request = request
    result, _ = await model.generate("reply", {}, noop)
    assert result["text"] == "valid" and len(calls) == 2


@pytest.mark.asyncio
async def test_agent_search_is_scoped_and_bounded(tmp_path):
    model = Provider(tmp_path)
    searches = []

    async def request(messages, progress, tools=None):
        if tools:
            return {
                "_tool_calls": [
                    {
                        "id": str(len(searches)),
                        "type": "function",
                        "function": {"name": "search_materials", "arguments": '{"query":"domain"}'},
                    }
                ]
            }, {}
        return {"text": "依据资料回答", "sources": ["page-a"]}, {}

    model.request = request

    def search(query):
        searches.append(query)
        return [{"id": "page-a", "text": "bounded source"}]

    result, usage = await model.generate("reply", {"_search": search}, noop)
    assert result["sources"] == ["page-a"]
    assert len(searches) == usage["tool_rounds"] == 4


@pytest.mark.asyncio
async def test_unauthorized_tool_rejected(tmp_path):
    model = Provider(tmp_path)

    async def request(*args):
        return {"_tool_calls": [{"id": "x", "function": {"name": "shell", "arguments": "{}"}}]}, {}

    model.request = request
    with pytest.raises(ModelError, match="权限"):
        await model.generate("reply", {"_search": lambda _: []}, noop)


@pytest.mark.asyncio
async def test_sse_transport_and_secret_redaction(tmp_path, monkeypatch):
    model = Provider(tmp_path)
    model.config["key"] = "fixture-secret"
    response = json.dumps({"text": "你好", "sources": []}, ensure_ascii=False)
    events = [
        {"choices": [{"delta": {"content": response[:8]}}]},
        {
            "choices": [{"delta": {"content": response[8:]}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 30},
        },
    ]
    content = "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
    original = httpx.AsyncClient

    def client(**kwargs):
        return original(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text=content)), **kwargs
        )

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result, usage = await model.generate("partner", {}, noop)
    assert result["text"] == "你好"
    assert "fixture-secret" not in json.dumps(usage)


@pytest.mark.asyncio
async def test_broken_stream_and_auth_error_are_safe(tmp_path, monkeypatch):
    model = Provider(tmp_path)
    model.config["key"] = "fixture-secret"
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(401, text="fixture-secret")), **kwargs
        ),
    )
    with pytest.raises(ModelError) as error:
        await model.request([], noop)
    assert "fixture-secret" not in str(error.value)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, text='data: {"choices": []}\n\n')),
            **kwargs,
        ),
    )
    with pytest.raises(ModelError, match="中断"):
        await model.request([], noop)
