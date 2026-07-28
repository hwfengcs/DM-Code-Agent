from threading import Lock

import pytest

from dm_agent.core.context_window import ContextWindow
from dm_agent.core.run_state import RunContext
from dm_agent.memory import ContextCompressor, Mem0StyleMemory
from dm_agent.memory.context_budget import estimate_messages_tokens
from dm_agent.memory.context_compressor import Compaction, apply_compaction


class _CompactionRecorder:
    def __init__(self):
        self.compactions = []
        self.events = []

    def __bool__(self):
        return True

    def record_compaction(self, payload, *, first_kept_index, folded_indexes):
        self.compactions.append(
            {
                "payload": dict(payload),
                "first_kept_index": first_kept_index,
                "folded_indexes": tuple(folded_indexes),
            }
        )

    def record(self, event, payload):
        self.events.append({"event": event, "payload": dict(payload)})


def _window_metadata():
    return {
        "compressed_messages": 0,
        "memory_items": 0,
        "memory_injection_count": 0,
        "memory_compression_count": 0,
        "memory_log_count": 0,
        "budget_compression_count": 0,
        "memory_invalidation_count": 0,
        "llm_summary_count": 0,
        "llm_summary_error_count": 0,
    }


def _growing_history(message_count, *, payload_chars=100):
    history = []
    for index in range(message_count):
        role = "user" if index % 2 == 0 else "assistant"
        prefix = "Task: inspect app.py " if index == 0 else f"turn {index} app.py completed "
        history.append({"role": role, "content": prefix + "x" * payload_chars})
    return history


def test_mem0_style_memory_adds_deduplicates_and_searches_by_scope():
    memory = Mem0StyleMemory()

    first = memory.add(
        "Observed failure: pytest failed in retry.py",
        type="episodic",
        scope={"agent_id": "dm", "run_id": "1"},
        metadata={"files": ["retry.py"]},
        importance=0.8,
    )
    second = memory.add(
        "Observed failure: pytest failed in retry.py",
        type="episodic",
        scope={"agent_id": "dm", "run_id": "1"},
        metadata={"files": ["tests/test_retry.py"]},
    )

    assert first == second
    assert len(memory) == 1
    hit = memory.search(
        "retry.py pytest failure",
        scope={"agent_id": "dm", "run_id": "1"},
        limit=1,
    )[0]
    assert hit.item.text.startswith("Observed failure")
    assert set(hit.item.metadata["files"]) == {"retry.py", "tests/test_retry.py"}
    assert memory.search("retry.py", scope={"agent_id": "other"}) == []


def test_mem0_style_memory_does_not_return_unrelated_memories():
    memory = Mem0StyleMemory()
    memory.add(
        "Observed failure: pytest failed in retry.py",
        scope={"agent_id": "dm"},
        metadata={"files": ["retry.py"]},
        importance=1.0,
    )

    assert memory.search("document README.md release notes", scope={"agent_id": "dm"}) == []


def test_context_compressor_uses_agent_memory_instead_of_flat_summary():
    history = [
        {"role": "user", "content": "任务：Fix retry.should_retry in retry.py"},
        {"role": "assistant", "content": "执行工具 read_file，输入：retry.py"},
        {"role": "user", "content": "观察：pytest returncode: 1 AssertionError in retry.py"},
        {"role": "assistant", "content": "执行工具 edit_file，输入：retry.py"},
        {"role": "user", "content": "观察：tests completed successfully"},
        {"role": "assistant", "content": "完成：retry.py fixed"},
        {"role": "user", "content": "Now explain retry.py"},
    ]
    compressor = ContextCompressor(compress_every=2, keep_recent=1)

    assert compressor.should_compress(history) is True
    compressed = compressor.compress(history)

    assert len(compressed) < len(history)
    assert compressor.memory_count > 0
    memory_block = compressed[0]["content"]
    assert memory_block.startswith("<agent_memory>")
    assert "retry.py" in memory_block
    assert "Observed failure" in memory_block or "Current task context" in memory_block
    assert compressed[-1]["content"] == "Now explain retry.py"


def test_context_compressor_waits_for_a_new_batch_before_recompressing():
    compressor = ContextCompressor(compress_every=3, keep_recent=1)
    history = [
        {"role": "user", "content": "Task: inspect app.py"},
        {"role": "assistant", "content": "Tool read_file app.py succeeded"},
        {"role": "user", "content": "Observation: pytest failed in app.py"},
        {"role": "assistant", "content": "Tool edit_file app.py completed"},
        {"role": "user", "content": "Summarize app.py"},
    ]

    assert compressor.should_compress(history) is True
    compressor.compress(history)

    history.extend(
        [
            {"role": "assistant", "content": "Done"},
            {"role": "user", "content": "One more small follow-up"},
        ]
    )
    assert compressor.memory_count > 0
    assert compressor.should_compress(history) is False

    history.extend(
        [
            {"role": "assistant", "content": "Answered follow-up"},
            {"role": "user", "content": "Second follow-up"},
            {"role": "assistant", "content": "Answered second follow-up"},
            {"role": "user", "content": "Third follow-up"},
        ]
    )
    assert compressor.should_compress(history) is True


def test_context_compressor_does_not_compress_before_recent_window_is_exceeded():
    compressor = ContextCompressor(compress_every=2, keep_recent=4)
    history = [
        {"role": "user", "content": "Task: inspect app.py"},
        {"role": "assistant", "content": "Tool read_file app.py succeeded"},
        {"role": "user", "content": "Observation: done"},
    ]

    assert compressor.should_compress(history) is False


def test_context_compressor_reports_memory_stats():
    compressor = ContextCompressor(compress_every=1, keep_recent=1)
    original = [
        {"role": "user", "content": "Task: inspect app.py"},
        {"role": "assistant", "content": "Tool read_file app.py succeeded"},
        {"role": "user", "content": "Observation: pytest failed in app.py"},
        {"role": "assistant", "content": "Tool edit_file app.py completed"},
        {"role": "user", "content": "Summarize app.py"},
    ]
    compressed = compressor.compress(original)
    stats = compressor.get_compression_stats(original, compressed)

    assert stats["saved_messages"] >= 1
    assert stats["memory_items"] == compressor.memory_count


def test_context_compressor_reset_clears_local_memory():
    compressor = ContextCompressor(compress_every=1, keep_recent=1)
    compressor.compress(
        [
            {"role": "user", "content": "Task: inspect app.py"},
            {"role": "assistant", "content": "Tool read_file app.py succeeded"},
            {"role": "user", "content": "Summarize app.py"},
        ]
    )

    assert compressor.memory_count > 0

    compressor.reset()

    assert compressor.memory_count == 0
    assert compressor.turn_count == 0


def test_context_compressor_reset_clears_all_conversation_scoped_state():
    compressor = ContextCompressor()
    compressor.memory.add("remember app.py")
    compressor.memory.superseded_count = 3
    compressor.turn_count = 5
    compressor._compression_count = 2
    compressor._last_compressed_turn_count = 4
    compressor.llm_summary_count = 2
    compressor.llm_summary_error_count = 1
    compressor.last_trigger = "token_budget"
    compressor.last_estimated_tokens = 321
    compressor.accept_beneficial_compaction(
        Compaction(
            first_kept_index=1,
            folded_indexes=(0,),
            summary="<agent_memory>remember app.py</agent_memory>",
        )
    )

    compressor.reset()

    assert compressor.memory_count == 0
    assert compressor.memory.superseded_count == 0
    assert compressor.turn_count == 0
    assert compressor.export_state()["compression_count"] == 0
    assert compressor.export_state()["last_compressed_turn_count"] == 0
    assert compressor.llm_summary_count == 0
    assert compressor.llm_summary_error_count == 0
    assert compressor.last_trigger == ""
    assert compressor.last_estimated_tokens == 0
    assert compressor.last_beneficial_compaction is None


def test_beneficial_compaction_state_roundtrips_resets_and_accepts_legacy_state():
    compaction = Compaction(
        first_kept_index=3,
        folded_indexes=(0, 1, 2),
        summary="<agent_memory>keep app.py</agent_memory>",
        trigger="cadence",
        estimated_tokens=120,
        memory_items=2,
    )
    compressor = ContextCompressor()
    compressor.memory.add("persist app.py")
    compressor.accept_beneficial_compaction(compaction)

    injected_memory = Mem0StyleMemory()
    restored = ContextCompressor(memory=injected_memory)
    restored.restore_state(compressor.export_state())

    assert restored.memory is injected_memory
    assert restored.memory_count == 1
    assert restored.last_beneficial_compaction == compaction

    legacy_state = compressor.export_state()
    legacy_state.pop("last_beneficial_compaction")
    restored.restore_state(legacy_state)
    assert restored.last_beneficial_compaction is None

    compressor.reset()
    assert compressor.last_beneficial_compaction is None


def test_token_budget_rejection_is_traced_without_counting_an_accepted_compression():
    compressor = ContextCompressor(compress_every=100, keep_recent=1, token_budget=10)
    recorder = _CompactionRecorder()
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=False,
        llm_compression=False,
        trace_writer=recorder,
    )
    context = RunContext(step_number=1, metadata=_window_metadata())
    history = _growing_history(3, payload_chars=20)

    sent = window.build_messages("system", history, context=context)

    phases = [event["payload"]["phase"] for event in recorder.events]
    assert sent[1:] == history
    assert phases == ["compress_rejected_no_savings", "post_compress_still_over"]
    assert context.metadata["budget_compression_count"] == 0
    assert recorder.compactions == []


def test_context_window_rejects_negative_candidates_then_accepts_and_reuses_sticky():
    compressor = ContextCompressor(compress_every=4, keep_recent=8, token_budget=0)
    recorder = _CompactionRecorder()
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=False,
        llm_compression=False,
        trace_writer=recorder,
    )
    context = RunContext(step_number=1, metadata=_window_metadata())

    for message_count in (17, 19, 21, 23):
        history = _growing_history(message_count)
        sent = window.build_messages("system", history, context=context)
        assert sent[1:] == history
        assert compressor.last_beneficial_compaction is None
        assert compressor.memory_count == 0
        assert compressor.export_state()["compression_count"] == 0
        assert recorder.compactions == []

    history = _growing_history(25)
    sent = window.build_messages("system", history, context=context)
    sticky = compressor.last_beneficial_compaction
    assert sticky is not None
    assert sent[1:] == apply_compaction(history, sticky)
    assert estimate_messages_tokens(sent[1:]) < estimate_messages_tokens(history)
    assert len(recorder.compactions) == 1

    grown_history = _growing_history(27)
    sticky_sent = window.build_messages("system", grown_history, context=context)
    assert sticky_sent[1:] == apply_compaction(grown_history, sticky)
    assert sticky_sent[-2:] == grown_history[-2:]
    assert len(recorder.compactions) == 1


def test_context_window_rejects_zero_saving_and_rolls_back_llm_summary_state(monkeypatch):
    class TrackingMemory(Mem0StyleMemory):
        def __init__(self):
            super().__init__()
            self.render_count = 0

        def render(self, query, **kwargs):
            self.render_count += 1
            return super().render(query, **kwargs)

        def capture_rollback_state(self):
            return {
                "base": super().capture_rollback_state(),
                "render_count": self.render_count,
            }

        def restore_rollback_state(self, state):
            super().restore_rollback_state(state["base"])
            self.render_count = state["render_count"]

    class SummaryClient:
        def respond(self, messages, **extra):
            return "summary"

    memory = TrackingMemory()
    compressor = ContextCompressor(
        SummaryClient(),
        compress_every=1,
        keep_recent=1,
        memory=memory,
        token_budget=0,
        use_llm_summary=True,
    )
    history = _growing_history(5, payload_chars=20)
    empty = Compaction(first_kept_index=0, folded_indexes=(), summary="")

    def zero_saving(_history):
        compressor._compression_count += 1
        compressor.llm_summary_count += 1
        compressor.memory.add("temporary memory")
        memory.render_count += 1
        return empty

    monkeypatch.setattr(compressor, "plan_compaction", zero_saving)
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=False,
        llm_compression=True,
    )

    sent = window.build_messages(
        "system", history, context=RunContext(step_number=1, metadata=_window_metadata())
    )

    assert sent[1:] == history
    assert compressor.memory_count == 0
    assert compressor.export_state()["compression_count"] == 0
    assert compressor.llm_summary_count == 0
    assert compressor.last_beneficial_compaction is None
    assert compressor.memory is memory
    assert memory.render_count == 0


def test_candidate_rollback_ignores_opaque_collaborators_and_preserves_identity():
    class OpaqueMemory(Mem0StyleMemory):
        def __init__(self):
            super().__init__()
            self.lock = Lock()
            self.backend = object()

    memory = OpaqueMemory()
    memory.add("stable memory")
    lock = memory.lock
    backend = memory.backend
    compressor = ContextCompressor(memory=memory)

    snapshot = compressor.snapshot_candidate_state()
    memory.add("temporary memory")
    compressor._compression_count = 9
    compressor.restore_candidate_state(snapshot)

    assert memory is compressor.memory
    assert memory.lock is lock
    assert memory.backend is backend
    assert [item.text for item in memory.items] == ["stable memory"]
    assert compressor.export_state()["compression_count"] == 0


def test_sticky_reuse_syncs_memory_gauges_without_counting_a_new_compression():
    compressor = ContextCompressor(compress_every=100, keep_recent=1, token_budget=0)
    compressor.memory.add("remember app.py")
    compressor.memory.superseded_count = 2
    compressor.llm_summary_count = 3
    compressor.llm_summary_error_count = 1
    sticky = Compaction(
        first_kept_index=1,
        folded_indexes=(0,),
        summary="<agent_memory>remember app.py</agent_memory>",
        memory_items=1,
    )
    compressor.accept_beneficial_compaction(sticky)
    metadata = _window_metadata()
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=True,
        llm_compression=True,
    )

    sent = window.build_messages(
        "system",
        _growing_history(3),
        context=RunContext(step_number=1, metadata=metadata),
    )

    assert sent[1:] == apply_compaction(_growing_history(3), sticky)
    assert metadata["memory_items"] == 1
    assert metadata["memory_invalidation_count"] == 2
    assert metadata["llm_summary_count"] == 3
    assert metadata["llm_summary_error_count"] == 1
    assert metadata["memory_injection_count"] == 0
    assert metadata["memory_compression_count"] == 0


def test_existing_hygiene_invalidations_are_not_reemitted_as_new_events():
    compressor = ContextCompressor(
        compress_every=1,
        keep_recent=1,
        token_budget=0,
        enable_hygiene=True,
    )
    compressor.memory.superseded_count = 2
    recorder = _CompactionRecorder()
    metadata = _window_metadata()
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=True,
        llm_compression=False,
        trace_writer=recorder,
    )

    window.build_messages(
        "system",
        _growing_history(17, payload_chars=180),
        context=RunContext(step_number=1, metadata=metadata),
    )

    assert metadata["memory_invalidation_count"] == 2
    assert not any(event["event"] == "memory_invalidation" for event in recorder.events)


def test_context_window_rolls_back_candidate_state_when_planning_raises(monkeypatch):
    compressor = ContextCompressor(compress_every=1, keep_recent=1, token_budget=0)
    history = _growing_history(5, payload_chars=20)

    def exploding_plan(_history):
        compressor._compression_count += 1
        compressor.memory.add("temporary memory")
        raise RuntimeError("custom memory failed")

    monkeypatch.setattr(compressor, "plan_compaction", exploding_plan)
    window = ContextWindow(
        compressor=compressor,
        enabled=True,
        memory_hygiene=False,
        llm_compression=False,
    )

    with pytest.raises(RuntimeError, match="custom memory failed"):
        window.build_messages(
            "system", history, context=RunContext(step_number=1, metadata=_window_metadata())
        )

    assert compressor.memory_count == 0
    assert compressor.export_state()["compression_count"] == 0


def test_context_compressor_token_budget_triggers_before_cadence():
    compressor = ContextCompressor(compress_every=50, keep_recent=1, token_budget=100)
    big = "x" * 300  # ~75 tokens per message
    history = [
        {"role": "user", "content": "Task: inspect app.py"},
        {"role": "assistant", "content": big},
        {"role": "user", "content": big},
        {"role": "assistant", "content": big},
        {"role": "user", "content": "Summarize app.py"},
    ]

    # Cadence alone (compress_every=50) would not fire; the budget does.
    assert compressor.should_compress(history) is True
    assert compressor.last_trigger == "token_budget"
    assert compressor.last_estimated_tokens > 100


def test_context_compressor_token_budget_zero_disables_size_trigger():
    compressor = ContextCompressor(compress_every=50, keep_recent=1, token_budget=0)
    big = "x" * 5000
    history = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": big},
        {"role": "user", "content": big},
        {"role": "assistant", "content": big},
        {"role": "user", "content": big},
    ]

    assert compressor.should_compress(history) is False


def test_context_compressor_cadence_trigger_reports_cadence():
    compressor = ContextCompressor(compress_every=2, keep_recent=1)
    history = [
        {"role": "user", "content": "Task: inspect app.py"},
        {"role": "assistant", "content": "Tool read_file app.py succeeded"},
        {"role": "user", "content": "Observation: pytest failed in app.py"},
        {"role": "assistant", "content": "Tool edit_file app.py completed"},
        {"role": "user", "content": "Summarize app.py"},
    ]

    assert compressor.should_compress(history) is True
    assert compressor.last_trigger == "cadence"


def test_context_compressor_budget_respects_recent_window_guard():
    # Even over budget, nothing is compressible until history exceeds the
    # verbatim recent window, so should_compress stays False.
    compressor = ContextCompressor(compress_every=50, keep_recent=4, token_budget=10)
    history = [
        {"role": "user", "content": "x" * 500},
        {"role": "assistant", "content": "x" * 500},
    ]

    assert compressor.should_compress(history) is False


def _hygiene_history():
    return [
        {"role": "user", "content": "任务：Fix retry.should_retry in retry.py"},
        {"role": "assistant", "content": "执行工具 read_file，输入：retry.py"},
        {"role": "user", "content": "观察：pytest returncode: 1 AssertionError in retry.py"},
        {"role": "assistant", "content": "执行工具 edit_file，输入：retry.py"},
        {"role": "user", "content": "观察：retry.py tests completed successfully returncode: 0"},
        {"role": "assistant", "content": "wrap up"},
        {"role": "user", "content": "Now explain retry.py"},
    ]


def test_memory_hygiene_supersedes_failure_after_success():
    compressor = ContextCompressor(compress_every=2, keep_recent=1, enable_hygiene=True)
    compressed = compressor.compress(_hygiene_history())

    assert compressor.memory.superseded_count >= 1
    failure_items = [
        item for item in compressor.memory.items if item.text.startswith("Observed failure")
    ]
    assert failure_items
    assert all(item.metadata.get("superseded_at_turn") is not None for item in failure_items)
    memory_block = compressed[0]["content"]
    if "Observed failure" in memory_block:
        assert "possibly stale" in memory_block


def test_memory_hygiene_disabled_keeps_failure_memories_fresh():
    compressor = ContextCompressor(compress_every=2, keep_recent=1)
    compressor.compress(_hygiene_history())

    assert compressor.memory.superseded_count == 0
    failure_items = [
        item for item in compressor.memory.items if item.text.startswith("Observed failure")
    ]
    assert failure_items
    assert all(item.metadata.get("superseded_at_turn") is None for item in failure_items)


def test_memory_hygiene_off_render_matches_legacy_output():
    # Guard the default path: with hygiene off, compression output is identical
    # to the legacy pipeline (no stale suffixes, no anchored query changes).
    history = _hygiene_history()
    legacy = ContextCompressor(compress_every=2, keep_recent=1)
    current = ContextCompressor(compress_every=2, keep_recent=1, enable_hygiene=False)

    assert legacy.compress(list(history)) == current.compress(list(history))


def test_hygiene_query_is_anchored_to_task_text():
    class RecordingMemory(Mem0StyleMemory):
        def __init__(self):
            super().__init__()
            self.last_query = ""

        def render(self, query, **kwargs):
            self.last_query = query
            return super().render(query, **kwargs)

    memory = RecordingMemory()
    compressor = ContextCompressor(
        compress_every=2, keep_recent=1, memory=memory, enable_hygiene=True
    )
    compressor.compress(_hygiene_history())

    assert memory.last_query.startswith("任务：Fix retry.should_retry")


class _SummaryClient:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = 0

    def respond(self, messages, **extra):
        self.calls += 1
        if self.fail:
            raise RuntimeError("summary backend unavailable")
        return "修复了 retry.py 的重试边界；测试已通过；无未解决问题。"


def test_llm_summary_adds_semantic_memory():
    client = _SummaryClient()
    compressor = ContextCompressor(client, compress_every=2, keep_recent=1, use_llm_summary=True)
    compressor.compress(_hygiene_history())

    assert client.calls == 1
    assert compressor.llm_summary_count == 1
    assert compressor.llm_summary_error_count == 0
    summaries = [
        item for item in compressor.memory.items if item.metadata.get("source") == "llm_summary"
    ]
    assert len(summaries) == 1
    assert summaries[0].type == "semantic"
    assert summaries[0].text.startswith("Summary of earlier context:")


def test_llm_summary_failure_falls_back_silently():
    client = _SummaryClient(fail=True)
    compressor = ContextCompressor(client, compress_every=2, keep_recent=1, use_llm_summary=True)
    compressed = compressor.compress(_hygiene_history())

    assert compressor.llm_summary_count == 0
    assert compressor.llm_summary_error_count == 1
    # Rule-based compression still produced a usable result.
    assert compressed
    assert compressor.memory_count > 0
