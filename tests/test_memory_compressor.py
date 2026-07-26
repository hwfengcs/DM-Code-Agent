from dm_agent.memory import ContextCompressor, Mem0StyleMemory


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
