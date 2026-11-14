"""HTML exports keep the sharing boundary separate from the source audit log."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from dm_agent.tracing.cli import main
from dm_agent.tracing.export_html import export_session_report, save_session_report


def _entry(event: str, **payload: Any) -> dict[str, Any]:
    return {"event": event, "payload": payload}


def _events() -> list[dict[str, Any]]:
    return [
        _entry("runtime", provider="PRIVATE_PROVIDER", model="PRIVATE_MODEL"),
        _entry("run_start", task="Repair the counter", cwd="C:/private/workspace"),
        _entry("message", role="assistant", content="RAW_MESSAGE_PRIVATE"),
        _entry("llm_call", messages=[{"content": "RAW_PROMPT_PRIVATE"}]),
        _entry("checkpoint", state={"messages": ["CHECKPOINT_PRIVATE"]}),
        _entry(
            "tool_call", step_number=1, action="edit_file", failed=False, observation="Edit applied"
        ),
        _entry(
            "step",
            step_number=1,
            action="edit_file",
            action_input={"path": "counter.py", "old_string": "return 1", "new_string": "return 2"},
            observation="Edit applied",
        ),
        _entry("tool_call", step_number=2, action="run_tests", failed=False),
        _entry("step", step_number=2, action="run_tests", observation="returncode: 0\n2 passed"),
        _entry("step", step_number=3, action="finish"),
        _entry(
            "run_end",
            status="success",
            final_answer="Counter repaired",
            duration_seconds=1.25,
            metadata={"private": "METADATA_PRIVATE"},
        ),
    ]


def _write(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")


def test_summary_omits_all_freeform_fields_without_mutating_entries() -> None:
    entries = _events()
    entries.insert(2, _entry("step", action="PRIVATE_ACTION", observation="PRIVATE_OUTPUT"))
    entries.append(_entry("run_end", status="PRIVATE_STATUS", metadata={}))
    original = copy.deepcopy(entries)
    report = export_session_report(entries, source_name="PRIVATE_SOURCE")
    for private in (
        "PRIVATE_",
        "_PRIVATE",
        "Repair the counter",
        "Counter repaired",
        "Edit applied",
        "counter.py",
        "return 1",
        "return 2",
        "2 passed",
        "C:/private/workspace",
    ):
        assert private not in report
    assert "Summary only" in report
    assert "Custom action" in report
    assert "Unknown" in report
    assert "Exit 0" in report
    assert entries == original


def test_content_has_evidence_but_never_raw_messages_or_checkpoint() -> None:
    report = export_session_report(_events(), include_content=True)
    for content in ("Repair the counter", "Counter repaired", "Edit applied", "2 passed"):
        assert content in report
    assert "Replacement excerpt" in report
    assert "not a full repository diff" in report
    assert "+return 2" in report
    assert "-return 1" in report
    assert "RAW_" not in report
    assert "CHECKPOINT_PRIVATE" not in report
    assert "METADATA_PRIVATE" not in report
    assert "Review this file locally before sharing" in report


def test_content_redacts_known_secrets_urls_emails_and_local_paths(monkeypatch: Any) -> None:
    monkeypatch.setenv("TEST_ACCESS_TOKEN", "ENVIRONMENT_SECRET_VALUE")
    private_values = [
        "ENVIRONMENT_SECRET_VALUE",
        "sk-proj-abcdefghijklmnopqrstuv",
        "ghp_abcdefghijklmnopqrstu",
        "github_pat_abcdefghijklmnopqrstu",
        "AKIA1234567890ABCDEF",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMifQ.abcdefghi",
        "person@example.com",
        "https://private.example/api?secret=abc",
        '"api_key": "QUOTED_PRIVATE_KEY"',
        "password='PRIVATE_PASSWORD'",
        "Authorization: Bearer PRIVATE_BEARER",
        "Authorization: Basic PRIVATE_BASIC",
        "-----BEGIN PRIVATE KEY-----\nPEM_SECRET_VALUE\n-----END PRIVATE KEY-----",
        "C:\\Users\\Private User\\project\\file.py",
        "/Users/private/project/file.py",
        str(Path.home()),
    ]
    entries = [_entry("run_start", task="\n".join(private_values))]
    report = export_session_report(entries, include_content=True)
    for value in private_values:
        assert value not in report
    for value in (
        "QUOTED_PRIVATE_KEY",
        "PRIVATE_PASSWORD",
        "PRIVATE_BEARER",
        "PRIVATE_BASIC",
        "PEM_SECRET_VALUE",
        "Private User",
    ):
        assert value not in report
    assert "[secret redacted]" in report
    assert "[local path]" in report
    assert "[URL redacted]" in report
    assert "[email redacted]" in report


class _PageTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def test_untrusted_content_cannot_add_elements_scripts_or_network_requests() -> None:
    attack = '</script><script>alert(1)</script><img src="https://leak.example" onerror="x()">'
    attack += '<svg/onload="x()"><iframe src="file:///private">'
    entries = _events()
    entries[1]["payload"]["task"] = attack
    entries[6]["payload"]["observation"] = attack
    entries[6]["payload"]["action_input"]["new_string"] = attack
    report = export_session_report(entries, source_name=attack, include_content=True)
    parser = _PageTags()
    parser.feed(report)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert [tag for tag, _ in parser.tags].count("script") == 1
    assert not {"img", "svg", "iframe", "form", "link"}.intersection(tag for tag, _ in parser.tags)
    assert not any("src" in attrs or "onerror" in attrs for _, attrs in parser.tags)
    assert "default-src 'none'" in report
    script = re.search(r"<script>(.*?)</script>", report, flags=re.DOTALL)
    assert script is not None
    digest = base64.b64encode(hashlib.sha256(script[1].encode()).digest()).decode()
    assert f"'sha256-{digest}'" in report


def test_runs_keep_tasks_outcomes_and_verification_separate() -> None:
    entries = [
        *_events(),
        _entry("run_start", task="SECOND_TASK"),
        _entry("step", step_number=1, action="finish"),
        _entry("run_end", status="success", final_answer="SECOND_ANSWER"),
    ]
    report = export_session_report(entries, include_content=True)
    first, second = report.split('id="run-2"')
    assert 'id="run-1"' in first
    assert 'id="run-3"' not in report
    assert "Repair the counter" in first
    assert "Counter repaired" in first
    assert "SECOND_TASK" not in first
    assert "SECOND_ANSWER" not in first
    assert "Verification gap:" not in first
    assert "SECOND_TASK" in second
    assert "SECOND_ANSWER" in second
    assert "Counter repaired" not in second
    assert "Verification gap:" in second


@pytest.mark.parametrize("include_content", [False, True])
def test_scripted_identity_is_scoped_to_explicit_run_markers(include_content: bool) -> None:
    entries = [
        _entry("runtime", demo=True, source="scripted"),
        _entry("run_start", metadata={"demo": True, "source": "scripted", "private": "PRIVATE"}),
        _entry("run_end", status="success"),
        _entry("run_start"),
        _entry("run_end", status="success"),
        _entry("run_start", metadata={"demo": "true", "source": "scripted"}),
        _entry("run_end", status="success"),
        _entry("run_start", metadata={"demo": True, "source": "PRIVATE_SOURCE"}),
        _entry("run_end", status="success"),
    ]
    report = export_session_report(entries, include_content=include_content)
    header, *runs = re.split(r'<section class="run"[^>]*>', report)
    assert len(runs) == 4
    assert "Scripted demo" not in header
    assert "Scripted demo · no model call" in runs[0]
    assert all("Scripted demo" not in run for run in runs[1:])
    assert "PRIVATE" not in report


def test_incomplete_and_empty_logs_do_not_claim_success_or_running() -> None:
    report = export_session_report([_entry("run_start", task="unfinished")])
    assert "Incomplete" in report
    assert "does not claim that the process is still running" in report
    assert "Success reported" not in report
    assert "No entries recorded." in export_session_report([])
    assert "Unknown" in export_session_report([_entry("run_end")])


def test_interrupted_run_keeps_tool_receipt_without_following_step() -> None:
    entries = [
        _entry("run_start", task="Check a repair"),
        _entry("step", step_number=1, action="read_file"),
        _entry(
            "tool_call",
            step_number=2,
            action="run_tests",
            observation="returncode: 0\nEvidence survived interruption",
            failed=False,
        ),
    ]
    report = export_session_report(entries, include_content=True)
    assert "Evidence survived interruption" in report
    assert "Exit 0" in report
    assert "Verification actions</span><strong>1" in report
    assert "Recorded steps</span><strong>2" in report
    assert "Incomplete" in report


@pytest.mark.parametrize(
    "entries",
    [
        [None],
        [{"event": "run_start", "payload": []}],
        [_entry("run_end", metadata=[])],
        [_entry("step", action=[])],
        [_entry("step", action="run_tests", step_number={})],
        [_entry("run_end", status="error", metadata={"parse_error_count": "secret"})],
    ],
)
def test_malformed_session_is_rejected_without_embedding_invalid_data(entries: Any) -> None:
    with pytest.raises(ValueError):
        export_session_report(entries)


def test_save_preserves_source_and_requires_explicit_overwrite(tmp_path: Path) -> None:
    source, output = tmp_path / "session.jsonl", tmp_path / "reports" / "report.html"
    _write(source, _events())
    original = source.read_bytes()
    assert save_session_report(source, output) == output
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    with pytest.raises(ValueError, match="already exists"):
        save_session_report(source, output)
    save_session_report(source, output, force=True, include_content=True)
    assert "Repair the counter" in output.read_text(encoding="utf-8")
    assert source.read_bytes() == original


@pytest.mark.parametrize("alias", ["same", "hardlink", "symlink"])
def test_force_cannot_overwrite_source_or_alias(tmp_path: Path, alias: str) -> None:
    source = tmp_path / "session.jsonl"
    _write(source, _events())
    original = source.read_bytes()
    output = source if alias == "same" else tmp_path / "alias.html"
    if alias == "hardlink":
        output.hardlink_to(source)
    elif alias == "symlink":
        try:
            output.symlink_to(source)
        except OSError as exc:
            pytest.skip(f"Symlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="must not overwrite"):
        save_session_report(source, output, force=True)
    assert source.read_bytes() == original


def test_cli_export_and_errors(tmp_path: Path, capsys: Any) -> None:
    source, output = tmp_path / "session.jsonl", tmp_path / "report.html"
    _write(source, _events())
    arguments = ["export", str(source), "--output", str(output)]
    assert main(arguments) == 0
    assert "structure only" in capsys.readouterr().out
    assert main(arguments) == 2
    assert "already exists" in capsys.readouterr().err
    assert main([*arguments, "--include-content", "--force"]) == 0
    assert "Review the HTML locally before sharing" in capsys.readouterr().out
    source.write_text("{invalid", encoding="utf-8")
    assert main([*arguments, "--force"]) == 2
    assert "Cannot export session" in capsys.readouterr().err
    assert main(["export", str(tmp_path / "missing"), "--output", str(output), "--force"]) == 2


def test_offline_demo_cli_report_keeps_identity_and_real_local_verification(tmp_path: Path) -> None:
    from dm_agent.demo import run_demo

    destination = tmp_path / "demo"
    run_demo(destination)
    verified = tmp_path / "verified.html"
    unverified = tmp_path / "unverified.html"
    assert (
        main(
            [
                "export",
                str(destination / "sessions" / "verified.jsonl"),
                "--output",
                str(verified),
                "--include-content",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "export",
                str(destination / "sessions" / "unverified.jsonl"),
                "--output",
                str(unverified),
            ]
        )
        == 0
    )
    verified_report = verified.read_text(encoding="utf-8")
    unverified_report = unverified.read_text(encoding="utf-8")
    assert "Scripted demo · no model call" in verified_report
    assert "Scripted demo · no model call" in unverified_report
    assert "Exit 1" in verified_report
    assert "Exit 0" in verified_report
    assert "Replacement excerpt" in verified_report
    assert "Verification gap:" not in verified_report
    assert "Verification gap:" in unverified_report
