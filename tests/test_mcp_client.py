"""Deterministic JSON-RPC transport checks using queues and a local fake server."""

import io
import json
import sys
from types import SimpleNamespace

import dm_agent.mcp.client as mcp_module
from dm_agent.core.observation import is_failure_observation
from dm_agent.mcp.client import MCPClient


def test_stdout_drains_buffered_responses_after_process_exit():
    client = MCPClient("stub", "unused", [])
    response = json.dumps({"id": 1, "result": {"tools": []}})
    client.process = SimpleNamespace(stdout=io.StringIO(response + "\n"), poll=lambda: 0)
    client._running = True

    client._read_stdout()

    assert client._stdout_queue.get_nowait() == response
    assert client._stdout_queue.empty()


def test_stdout_stops_at_eof_even_if_process_is_alive():
    client = MCPClient("stub", "unused", [])
    reads = []

    def readline():
        reads.append(True)
        if len(reads) > 1:
            client._running = False
        return ""

    client.process = SimpleNamespace(stdout=SimpleNamespace(readline=readline), poll=lambda: None)
    client._running = True

    client._read_stdout()

    assert len(reads) == 1


def test_notification_does_not_prevent_request_timeout(monkeypatch):
    client = MCPClient("stub", "unused", [], request_timeout=0.1)
    client.process = SimpleNamespace(stdin=io.StringIO())
    notification = json.dumps({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
    client._stdout_queue.put(notification)
    clock = iter([0.0, 0.0, 0.2])
    monkeypatch.setattr(mcp_module.time, "monotonic", lambda: next(clock))

    assert client._send_message("tools/list") is None

    assert client._stdout_queue.get_nowait() == notification
    assert client._stdout_queue.empty()


def test_request_finds_matching_response_and_preserves_unrelated_messages():
    client = MCPClient("stub", "unused", [])
    client.process = SimpleNamespace(stdin=io.StringIO())
    notification = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress"})
    client._stdout_queue.put(notification)
    client._stdout_queue.put(json.dumps(["not a JSON-RPC message"]))
    client._stdout_queue.put(json.dumps({"id": 1, "result": {"tools": []}}))

    assert client._send_message("tools/list") == {"tools": []}

    assert client._stdout_queue.get_nowait() == notification
    assert client._stdout_queue.empty()


def test_tool_result_keeps_all_text_blocks_and_error_status(monkeypatch):
    client = MCPClient("stub", "unused", [])
    monkeypatch.setattr(
        client,
        "_send_message",
        lambda *args: {
            "isError": True,
            "content": [{"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}],
        },
    )

    observation = client.call_tool("stub", {})

    assert observation == "MCP tool error: 第一段\n第二段"
    assert is_failure_observation(observation, action="mcp_stub_stub")


def test_mcp_initialization_unicode_spaces_and_stderr_backpressure(tmp_path):
    server = tmp_path / "fake server with spaces.py"
    server.write_text(
        "import json, sys\n"
        "sys.stderr.write('diagnostic ' + 'x' * 100000 + '\\n')\n"
        "sys.stderr.flush()\n"
        "initialized = False\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    method = request['method']\n"
        "    if method == 'notifications/initialized':\n"
        "        initialized = True\n"
        "        continue\n"
        "    if method == 'initialize':\n"
        "        result = {'protocolVersion': '2024-11-05', 'capabilities': {}}\n"
        "    elif method == 'tools/list' and initialized:\n"
        "        result = {'tools': [{'name': 'echo', 'description': '本地测试'}]}\n"
        "    else:\n"
        "        result = {'content': [{'type': 'text', 'text': '你好'}]}\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result},\n"
        "                     ensure_ascii=False), flush=True)\n",
        encoding="utf-8",
    )
    client = MCPClient(
        "local-stub", sys.executable, [str(server)], env={"PYTHONUTF8": "1"}, request_timeout=3
    )
    try:
        assert client.start()
        assert client.get_tools()[0]["description"] == "本地测试"
        assert client.call_tool("echo", {}) == "你好"
    finally:
        client.stop()
