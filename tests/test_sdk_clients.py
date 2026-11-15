"""Offline checks for SDK client configuration; no model requests are made."""

from types import SimpleNamespace

import pytest

import dm_agent.clients.claude_client as claude_module
import dm_agent.clients.gemini_client as gemini_module
import dm_agent.clients.openai_client as openai_module


def test_openai_sdk_uses_configured_endpoint_timeout_and_one_retry_layer(monkeypatch):
    calls = []
    monkeypatch.setattr(openai_module, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(openai_module, "OpenAI", lambda **kwargs: calls.append(kwargs))

    client = openai_module.OpenAIClient(
        "test-key", base_url="https://example.invalid/v1/", timeout=17, respond_retries=4
    )

    assert calls == [
        {
            "api_key": "test-key",
            "base_url": "https://example.invalid/v1",
            "timeout": 17,
            "max_retries": 0,
        }
    ]
    assert client.respond_retries == 4


def test_claude_sdk_uses_configured_endpoint_timeout_and_one_retry_layer(monkeypatch):
    calls = []
    monkeypatch.setattr(claude_module, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(
        claude_module,
        "anthropic",
        SimpleNamespace(Anthropic=lambda **kwargs: calls.append(kwargs)),
    )

    client = claude_module.ClaudeClient(
        "test-key", base_url="https://example.invalid/", timeout=19, respond_retries=3
    )

    assert calls == [
        {
            "api_key": "test-key",
            "base_url": "https://example.invalid",
            "timeout": 19,
            "default_headers": {"anthropic-version": "2023-06-01"},
            "max_retries": 0,
        }
    ]
    assert client.respond_retries == 3


def test_gemini_sdk_uses_milliseconds_and_disables_internal_retries(monkeypatch):
    calls = []
    monkeypatch.setattr(gemini_module, "GENAI_AVAILABLE", True)
    monkeypatch.setattr(
        gemini_module, "genai", SimpleNamespace(Client=lambda **kwargs: calls.append(kwargs))
    )

    client = gemini_module.GeminiClient(
        "test-key", base_url="https://example.invalid/", timeout=23, respond_retries=5
    )

    calls[0]["http_options"] = calls[0]["http_options"].model_dump(exclude_none=True)
    assert calls == [
        {
            "api_key": "test-key",
            "http_options": {
                "base_url": "https://example.invalid",
                "timeout": 23000,
                "retry_options": {"attempts": 1},
            },
        }
    ]
    assert client.respond_retries == 5


def test_empty_sdk_endpoint_preserves_provider_default(monkeypatch):
    calls = []
    monkeypatch.setattr(openai_module, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(openai_module, "OpenAI", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(claude_module, "ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(
        claude_module,
        "anthropic",
        SimpleNamespace(Anthropic=lambda **kwargs: calls.append(kwargs)),
    )
    monkeypatch.setattr(gemini_module, "GENAI_AVAILABLE", True)
    monkeypatch.setattr(
        gemini_module, "genai", SimpleNamespace(Client=lambda **kwargs: calls.append(kwargs))
    )

    openai_module.OpenAIClient("test-key")
    claude_module.ClaudeClient("test-key")
    gemini_module.GeminiClient("test-key")

    assert calls[0]["base_url"] is None
    assert calls[1]["base_url"] is None
    assert calls[2]["http_options"].base_url is None


@pytest.mark.parametrize("model, sampling", [("gpt-5", False), ("gpt-4.1", True)])
def test_openai_preserves_roles_and_maps_generation_parameters(monkeypatch, model, sampling):
    calls = []
    monkeypatch.setattr(
        openai_module,
        "OpenAI",
        lambda **kw: SimpleNamespace(
            responses=SimpleNamespace(create=lambda **kw: calls.append(kw))
        ),
    )
    messages = [{"role": role, "content": role} for role in ("system", "user", "assistant")]
    client = openai_module.OpenAIClient("test-key", model=model)
    client.complete(messages, temperature=0.2, max_tokens=200)
    assert calls[0]["input"] == messages
    assert calls[0]["max_output_tokens"] == 200
    assert ("temperature" in calls[0]) is sampling
    assert "max_tokens" not in calls[0]


def test_gemini_preserves_roles_and_all_system_messages(monkeypatch):
    calls = []
    monkeypatch.setattr(
        gemini_module.genai,
        "Client",
        lambda **kw: SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **kw: calls.append(kw))
        ),
    )
    client = gemini_module.GeminiClient("test-key")
    client.complete(
        [
            {"role": "system", "content": "first"},
            {"role": "system", "content": "second"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    assert [content.role for content in calls[0]["contents"]] == ["user", "model"]
    config = calls[0]["config"]
    assert config.system_instruction == "first\n\nsecond"
    assert config.temperature == 0.2 and config.max_output_tokens == 200


def test_claude_keeps_all_system_messages_and_custom_version(monkeypatch):
    calls, configuration = [], []

    def create(**kwargs):
        configuration.append(kwargs)
        return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: calls.append(kw)))

    monkeypatch.setattr(claude_module.anthropic, "Anthropic", create)
    client = claude_module.ClaudeClient("test-key", anthropic_version="custom-version")
    client.complete(
        [{"role": "system", "content": "first"}, {"role": "system", "content": "second"}]
    )
    assert calls[0]["system"] == "first\n\nsecond"
    assert configuration[0]["default_headers"]["anthropic-version"] == "custom-version"
