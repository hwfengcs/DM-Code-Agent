# When source code says “error,” did the tool fail?

[中文](02-error-is-not-failure.zh.md) · [All articles](README.md) · [Interactive demo](https://hwfengcs.github.io/DM-Code-Agent/)

Reading this valid Python line once triggered failure recovery in DM-Code-Agent:

```python
from errors import NotFound
```

The file existed. The read succeeded. The problem was the agent's observation classifier: it searched the entire tool output for failure markers, including the substring `error`.

## A status channel mixed with a content channel

An observation can contain the tool's own status—“file not found,” for example—or content the tool is carrying, such as source code and subprocess stdout. Searching both as if they were status turns vocabulary into control flow.

This became more visible after the editing tool started returning the changed code. Better edit feedback brought more source text into observations, exposing an existing classification bug more often.

In the historical August 5, 2026 review, the same 30 saved traces contained 296 tool calls. The old classifier marked 84 as failures; 38 were false positives.

| Source of false failure classifications | Count |
| --- | ---: |
| Edit feedback containing source code | 18 |
| `read_file` content | 12 |
| `run_python` printing `ERROR:` with exit code 0 | 6 |
| Directory listing | 1 |
| Test output | 1 |
| Total | 38 |

Counting replanning events instead gives **34 false triggers among 78 replans (43.6%)**. These are different denominators. The preceding editing experiment counted 17 replans specifically triggered by edit feedback, not every false trigger.

## Reproduce the distinction

After installing the [project](../../README.md), run this small Python example. It calls the current classifier directly and makes no model or network calls:

```python
from dm_agent.core.observation import is_failure_observation

source = "1 | from errors import NotFound"
assert "error" in source.lower()  # The old substring rule fires.
assert not is_failure_observation(source, action="read_file")

output = "stdout:\nERROR: expected fixture text\nreturncode: 0"
assert not is_failure_observation(output, action="run_python")
assert is_failure_observation("returncode: 2", action="run_python")
assert is_failure_observation(
    "Tool execution failed: permission denied", action="read_file"
)
print("Source text is not tool status.")
```

The fix separates evidence by origin. Kernel failures are recognized at the beginning of the observation. Built-in file tools use their known refusal/status positions, not the returned file body. Execution tools use their reported exit code; a successful command may legitimately print `ERROR:`. Syntax-check failures after a file edit remain failure signals.

Unknown extension tools still use a conservative text-marker fallback because their output format is not guaranteed. This change did not make every tool response structured or eliminate every possible ambiguity.

## Validate the classifier separately from the agent

Reclassifying the same saved corpus removed the 38 false positives, retained all 46 previously recognized true failures, and found four previously missed failures. This is direct evidence about that classifier on that corpus; it is not a claim of zero false positives on arbitrary repositories.

A later live run showed replans falling from 78 to 23. That run also included linter handling and Windows newline changes, so it cannot isolate the effect of the classifier on the overall agent. The offline comparison answers the narrower question much more clearly: did the status decision improve for already observed tool outputs?

The practical rule is simple: carry status separately from payload when possible. When compatibility requires text observations, use the producing tool's contract and its status positions. Treat code, quoted examples, and command output as content unless an explicit status signal says otherwise.

## Evidence

- [Full historical analysis and counting definitions, devlog 39](../research-log/39-observation-failure-classification.md)
- [The earlier edit-feedback side effect, devlog 38](../research-log/38-edit-file-precision.md)
- [Current classifier](../../dm_agent/core/observation.py) and [behavior tests](../../tests/test_observation_failure.py)
- [Report for the reviewed run](../../bench_reports/editfix-20260804.json)

[DM-Code-Agent](../../README.md) keeps tool observations available for this kind of offline investigation. [Try the demo](../getting-started.md) to inspect failures, recovery, and verification evidence without an API key.
