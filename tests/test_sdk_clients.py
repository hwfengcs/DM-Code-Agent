"""Offline checks for SDK client configuration; no model requests are made."""

from types import SimpleNamespace

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
