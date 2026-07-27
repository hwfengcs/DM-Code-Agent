from dm_agent.cli import Config, create_agent
from dm_agent.core.events import BeforeToolCallEvent
from dm_agent.extensions import ExtensionRegistry
from dm_agent.skills import ConfigSkill
from dm_agent.tools import Tool


def _tool(name: str, result: str) -> Tool:
    return Tool(name=name, description=name, runner=lambda arguments: result)


def _skill(name: str, prompt: str) -> ConfigSkill:
    return ConfigSkill({"name": name, "prompt_addition": prompt})


def test_extension_api_registers_and_overrides_named_capabilities():
    registry = ExtensionRegistry()
    builtin = registry.api("builtin")
    external = registry.api("external")

    builtin.register_tool(_tool("echo", "builtin"))
    builtin.register_skill(_skill("python", "builtin"))
    builtin.register_provider("Example", lambda **kwargs: "builtin")

    external.register_tool(_tool("echo", "external"))
    external.register_skill(_skill("python", "external"))
    external.register_provider("EXAMPLE", lambda **kwargs: "external")

    assert [tool.name for tool in registry.get_tools()] == ["echo"]
    assert registry.get_tools()[0].execute({}) == "external"
    assert [skill.get_metadata().name for skill in registry.get_skills()] == ["python"]
    assert registry.get_skills()[0].get_prompt_addition() == "external"
    assert registry.get_provider_names() == ["example"]
    factory = registry.get_provider_factory("eXaMpLe")
    assert factory is not None
    assert factory() == "external"


def test_extension_api_on_replays_handlers_into_fresh_event_buses():
    registry = ExtensionRegistry()
    api = registry.api("test-extension")
    calls: list[str] = []

    def guard(event: BeforeToolCallEvent):
        calls.append(event.tool_name)
        return {"block": True, "reason": "blocked"}

    api.on("before_tool_call", guard)

    first_bus = registry.create_event_bus()
    second_bus = registry.create_event_bus()
    assert first_bus is not second_bus

    event = BeforeToolCallEvent(
        tool_name="run_shell",
        arguments={"command": "echo ok"},
        step_number=1,
        run_id="run-1",
    )
    assert first_bus.emit_before_tool_call(event) == {"block": True, "reason": "blocked"}
    assert second_bus.emit_before_tool_call(event) == {"block": True, "reason": "blocked"}
    assert calls == ["run_shell", "run_shell"]


def test_extension_api_rejects_invalid_registration_values():
    registry = ExtensionRegistry()
    api = registry.api("invalid")

    try:
        api.register_provider("", lambda **kwargs: None)
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("empty provider name should fail")

    try:
        api.on("unknown", lambda event: None)
    except ValueError as exc:
        assert "Unsupported lifecycle event" in str(exc)
    else:
        raise AssertionError("unknown event should fail")


def test_failed_setup_does_not_leave_partial_registrations():
    registry = ExtensionRegistry()

    def broken_setup(api):
        api.register_tool(_tool("partial", "partial"))
        raise RuntimeError("boom")

    try:
        registry.apply_setup(broken_setup, source="broken")
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("broken setup should fail")

    assert registry.get_tools() == []


def test_cli_create_agent_materializes_a_fresh_bus_for_each_agent():
    registry = ExtensionRegistry()
    calls: list[str] = []

    def observer(event):
        calls.append(event.run_id)

    registry.api("observer").on("before_tool_call", observer)
    config = Config(api_key="test-key")
    tool = _tool("noop", "ok")
    client = type("FakeClient", (), {"respond": lambda self, messages, **kwargs: "{}"})()

    first = create_agent(config, client, [tool], extension_registry=registry)
    second = create_agent(config, client, [tool], extension_registry=registry)

    assert first.event_bus is not second.event_bus
    first.event_bus.emit_before_tool_call(BeforeToolCallEvent("noop", {}, 1, "first"))
    second.event_bus.emit_before_tool_call(BeforeToolCallEvent("noop", {}, 1, "second"))
    assert calls == ["first", "second"]
