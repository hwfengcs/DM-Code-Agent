"""用真实 OpenAI SDK 和内存 HTTP transport 验证扩展；不连接服务或模型。"""

import json
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from dm_agent.clients.base_client import LLMError
from dm_agent.clients.llm_factory import create_llm_client
from dm_agent.extensions import discover_extensions
from examples import openai_compatible

EXTENSION = Path(__file__).resolve().parents[1] / "examples" / "openai_compatible.py"


def completion(content="done", **message):
    return {
        "id": "chatcmpl-offline",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, **message},
            }
        ],
    }


@pytest.fixture
def mock_sdk(monkeypatch):
    clients = []

    def install(handler):
        def factory(**kwargs):
            client = OpenAI(
                http_client=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs
            )
            clients.append(client)
            return client

        monkeypatch.setattr(openai_compatible, "OpenAI", factory)

    yield install
    for client in clients:
        client.close()


def test_chat_route_roles_parameters_and_cloud_key_isolation(mock_sdk, monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=completion("  completed  "))

    monkeypatch.setenv("OPENAI_API_KEY", "cloud-key-must-not-be-sent")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "another-cloud-key")
    monkeypatch.delenv("DM_COMPATIBLE_API_KEY", raising=False)
    mock_sdk(handle)
    client = openai_compatible.create_client(
        api_key="", model="qwen-test", base_url="http://127.0.0.1:9997/v1/"
    )
    messages = [
        {"role": "system", "content": "Return JSON actions."},
        {"role": "user", "content": "Inspect retry.py."},
    ]

    assert client.respond(messages, temperature=0.2) == "completed"
    assert len(requests) == 1
    assert str(requests[0].url) == "http://127.0.0.1:9997/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer local-no-key"
    assert json.loads(requests[0].content) == {
        "model": "qwen-test",
        "messages": messages,
        "temperature": 0.2,
    }


@pytest.mark.parametrize("status, attempts", [(401, 1), (429, 3)])
def test_only_transient_failures_use_one_bounded_retry_layer(mock_sdk, status, attempts):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "fixture error"}})

    mock_sdk(handle)
    client = openai_compatible.create_client(
        api_key="test-key", model="qwen-test", base_url="http://127.0.0.1:9997/v1"
    )
    client.respond_retry_backoff = 0

    with pytest.raises(LLMError, match="Chat Completions request failed"):
        client.respond([{"role": "user", "content": "test"}])
    assert len(requests) == attempts


def test_reasoning_only_response_is_not_treated_as_final_text(mock_sdk):
    mock_sdk(
        lambda request: httpx.Response(200, json=completion(None, reasoning_content="thinking"))
    )
    client = openai_compatible.create_client(
        api_key="test-key", model="qwen-test", base_url="http://127.0.0.1:9997/v1"
    )
    with pytest.raises(LLMError, match="reasoning_content alone is insufficient"):
        client.respond([{"role": "user", "content": "test"}])


def test_explicit_extension_loads_and_uses_only_its_own_key(monkeypatch, tmp_path):
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])
    monkeypatch.setenv("DM_COMPATIBLE_API_KEY", "local-server-key")
    discovery = discover_extensions(
        project_root=tmp_path, home_dir=tmp_path, explicit_paths=[EXTENSION]
    )
    client = create_llm_client(
        "openai-compatible",
        "",
        model="qwen-test",
        base_url="http://127.0.0.1:9997/v1",
        extension_registry=discovery.registry,
    )
    try:
        assert client.api_key == "local-server-key"
        assert client.client.max_retries == 0
    finally:
        client.client.close()


@pytest.mark.parametrize("missing", ["model", "base_url"])
def test_missing_endpoint_or_model_fails_before_sdk_construction(monkeypatch, missing):
    def forbidden(**kwargs):
        raise AssertionError("Must not construct a client with implicit cloud defaults")

    monkeypatch.setattr(openai_compatible, "OpenAI", forbidden)
    options = {"api_key": "", "model": "qwen-test", "base_url": "http://127.0.0.1:9997/v1"}
    options[missing] = ""
    with pytest.raises(ValueError, match="requires --base-url and --model"):
        openai_compatible.create_client(**options)
