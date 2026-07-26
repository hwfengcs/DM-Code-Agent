"""Tests for context budget helpers: token estimates, truncation, file ledger."""

from __future__ import annotations

from dm_agent.core.agent import ReactAgent
from dm_agent.memory.context_budget import (
    MIN_HEAD_CHARS,
    FileLedger,
    estimate_messages_tokens,
    estimate_tokens,
    estimate_tokens_from_chars,
    truncate_observation,
)


def test_estimate_tokens_from_chars_boundaries() -> None:
    assert estimate_tokens_from_chars(0) == 0
    assert estimate_tokens_from_chars(1) == 1
    assert estimate_tokens_from_chars(4) == 1
    assert estimate_tokens_from_chars(5) == 2
    assert estimate_tokens_from_chars(-10) == 0


def test_estimate_tokens_and_messages() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("") == 0
    messages = [
        {"role": "system", "content": "a" * 8},
        {"role": "user", "content": "b" * 4},
    ]
    assert estimate_messages_tokens(messages) == 3


def test_truncate_passthrough_when_disabled_or_small() -> None:
    text = "x" * 1000
    disabled = truncate_observation(text, max_chars=0)
    assert disabled.text == text
    assert not disabled.truncated

    small = truncate_observation("short", max_chars=100)
    assert small.text == "short"
    assert not small.truncated
    assert small.kept_chars == 5


def test_truncate_keeps_head_and_tail_with_marker() -> None:
    text = "HEAD" + "m" * 20000 + "TAIL"
    result = truncate_observation(text, max_chars=8000)
    assert result.truncated
    assert result.text.startswith("HEAD")
    assert result.text.endswith("TAIL")
    assert "[truncated: showing first" in result.text
    assert result.kept_chars <= 8000
    assert result.original_chars == len(text)
    # Failure-signature stability: the first 160 chars must be original text.
    assert result.text[:160] == text[:160]


def test_truncate_head_floor_when_cap_allows() -> None:
    text = "y" * 30000
    result = truncate_observation(text, max_chars=8000)
    head = result.text.split("\n[truncated:")[0]
    assert len(head) >= MIN_HEAD_CHARS


def test_truncate_small_cap_gives_whole_budget_to_head() -> None:
    text = "z" * 5000
    result = truncate_observation(text, max_chars=400)
    assert result.truncated
    assert result.kept_chars == 400
    head = result.text.split("\n[truncated:")[0]
    assert len(head) == 400


def test_truncate_marker_is_not_a_failure_observation() -> None:
    text = "ok line\n" * 5000
    result = truncate_observation(text, max_chars=1000)
    marker_start = result.text.index("[truncated:")
    marker_end = result.text.index("]", marker_start) + 1
    marker = result.text[marker_start:marker_end]
    assert not ReactAgent._is_failure_observation(marker)


def test_truncate_read_file_hint_contains_next_page() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 4001))
    result = truncate_observation(
        text,
        max_chars=1000,
        action="read_file",
        action_input={"path": "big.py"},
    )
    assert result.truncated
    assert 'next page: read_file {"path": "big.py", "line_start":' in result.text
    assert result.head_end_line >= 1


def test_truncate_read_file_hint_respects_existing_offset() -> None:
    text = "\n".join(f"line {i}" for i in range(1, 4001))
    result = truncate_observation(
        text,
        max_chars=1000,
        action="read_file",
        action_input={"path": "big.py", "line_start": 100},
    )
    assert '"line_start": ' in result.text
    # The suggested start is absolute: 100 - 1 + head_end_line.
    assert f'"line_start": {99 + result.head_end_line}' in result.text


def test_truncate_generic_hint_for_command_output() -> None:
    text = "out\n" * 5000
    result = truncate_observation(text, max_chars=1000, action="run_tests")
    assert "narrow the command" in result.text


def test_file_ledger_read_before_edit() -> None:
    ledger = FileLedger()
    assert ledger.check_edit("a.py") == "never_read"
    ledger.note_read("a.py", 1)
    assert ledger.check_edit("a.py") is None
    ledger.note_write("a.py", 2)
    assert ledger.check_edit("a.py") == "stale_read"
    ledger.note_read("a.py", 3)
    assert ledger.check_edit("a.py") is None


def test_file_ledger_normalizes_relative_and_absolute_paths() -> None:
    import os

    ledger = FileLedger()
    ledger.note_read("sub/../a.py", 1)
    assert ledger.check_edit(os.path.abspath("a.py")) is None


def test_file_ledger_reset() -> None:
    ledger = FileLedger()
    ledger.note_read("a.py", 1)
    ledger.reset()
    assert ledger.check_edit("a.py") == "never_read"
