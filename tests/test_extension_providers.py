from __future__ import annotations

import pytest

from dm_agent.cli import main
from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.extensions import create_builtin_registry


def test_builtin_provider_registry_keeps_exact_names_defaults_and_error():
    registry = create_builtin_registry()

    assert registry.get_provider_names() == ["deepseek", "openai", "claude", "gemini"]
    assert PROVIDER_DEFAULTS == {
        "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
        "openai": {"model": "gpt-5", "base_url": ""},
        "claude": {"model": "claude-sonnet-4-5", "base_url": ""},
        "gemini": {"model": "gemini-2.5-flash", "base_url": ""},
    }

    with pytest.raises(
        ValueError,
        match="不支持的提供商: missing。支持的提供商: deepseek, openai, claude, gemini",
    ):
        create_llm_client("missing", "test-key")


def test_custom_provider_factory_is_selected_case_insensitively():
    registry = create_builtin_registry()
    captured = {}
    client = object()

    def factory(**kwargs):
        captured.update(kwargs)
        return client

    registry.api("custom").register_provider("Local-Gateway", factory)

    created = create_llm_client(
        "LOCAL-GATEWAY",
        "",
        model="local-model",
        base_url="http://127.0.0.1:8080",
        timeout=12,
        extension_registry=registry,
        custom_option=True,
    )

    assert created is client
    assert captured == {
        "api_key": "",
        "model": "local-model",
        "base_url": "http://127.0.0.1:8080",
        "timeout": 12,
        "custom_option": True,
    }


def test_cli_selects_explicit_extension_provider_without_api_key(monkeypatch, tmp_path, capsys):
    extension = tmp_path / "provider.py"
    extension.write_text(
        "\n".join(
            [
                "class LocalClient:",
                "    pass",
                "",
                "def create_client(**kwargs):",
                "    client = LocalClient()",
                "    client.options = kwargs",
                "    return client",
                "",
                "def setup(api):",
                "    api.register_provider('local-test', create_client)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])
    captured = {}

    def fake_run(config, task, **kwargs):
        captured["config"] = config
        captured["task"] = task
        captured["client"] = create_llm_client(
            provider=config.provider,
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
            extension_registry=kwargs["extension_registry"],
        )
        return 0

    monkeypatch.setattr("dm_agent.cli.run_single_task", fake_run)

    exit_code = main(
        [
            "provider smoke",
            "--extension",
            str(extension),
            "--provider",
            "local-test",
            "--model",
            "local-model",
        ]
    )

    assert exit_code == 0
    assert captured["config"].api_key == ""
    assert captured["config"].base_url == ""
    assert type(captured["client"]).__name__ == "LocalClient"
    assert "已加载 1 个外部扩展" in capsys.readouterr().out


def test_cli_resolves_api_key_from_the_final_provider(monkeypatch):
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    captured = {}

    def fake_run(config, task, **kwargs):
        captured["config"] = config
        return 0

    monkeypatch.setattr("dm_agent.cli.run_single_task", fake_run)

    assert main(["task", "--provider", "openai", "--no-extensions"]) == 0
    assert captured["config"].api_key == "openai-key"
    assert captured["config"].model == "gpt-5"


def test_no_extensions_disables_explicit_custom_provider(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("dm_agent.extensions.discovery.metadata.entry_points", lambda **kwargs: [])

    exit_code = main(["task", "--provider", "local-test", "--no-extensions"])

    assert exit_code == 2
    assert "不支持的提供商: local-test" in capsys.readouterr().err
