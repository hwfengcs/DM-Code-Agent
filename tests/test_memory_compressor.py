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
