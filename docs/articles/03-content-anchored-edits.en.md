# Content-anchored edits reduced collateral damage

[中文](03-content-anchored-edits.zh.md) · [All articles](README.md) · [Interactive demo](https://hwfengcs.github.io/DM-Code-Agent/)

An agent wants to change one assignment. It selects a line range that is one line too wide. The edit succeeds, but a neighboring variable disappears. Python still parses, so the mistake surfaces only when the code runs.

In DM-Code-Agent's historical traces, this failure consumed steps that looked like a reasoning problem. Changing the edit contract gave us a more direct intervention.

## Fresh reads do not guarantee the right range

The first diagnosis blamed stale line numbers. Inspection showed that a read-before-edit guard already blocked stale reads. The remaining problem was that the model could read current line numbers and still choose the wrong interval. The old edit receipt said which lines were replaced but did not show the resulting code.

The August 4, 2026 change bundled three related pieces:

1. Prefer `old_string` / `new_string`: the old text must match exactly once, including whitespace. Zero or multiple matches leave the file untouched.
2. Return edited code with fresh line numbers and surrounding context.
3. Parse edited Python for syntax errors and report them. This is feedback, not a rollback or a proof that the program works.

The model still chooses the text and replacement. Unique matching lowers location risk; it cannot guarantee that the selected text or new logic is correct.

## A minimal, isolated reproduction

After installing the [project](../../README.md), run this Python example. It uses only a temporary directory and the real editing function:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from dm_agent.tools.file_tools import edit_file

with TemporaryDirectory() as directory:
    path = Path(directory) / "example.py"
    source = "limit = 3\nlabel = 'keep me'\n"
    path.write_text(source, encoding="utf-8")
    edit_file({"path": str(path), "old_string": "limit = 3",
               "new_string": "limit = 4"})
    assert path.read_text(encoding="utf-8") == "limit = 4\nlabel = 'keep me'\n"

    path.write_text(source + source, encoding="utf-8")
    before = path.read_bytes()
    edit_file({"path": str(path), "old_string": "limit = 3",
               "new_string": "limit = 4"})
    assert path.read_bytes() == before  # Ambiguous match: no write.
    edit_file({"path": str(path), "old_string": "limit = 99",
               "new_string": "limit = 4"})
    assert path.read_bytes() == before  # Missing match: no write.
print("Unique replacement succeeded; ambiguous and missing matches changed nothing.")
```

This checks the tool's location contract. It does not simulate model quality, the agent's read guard, or whether a real repair is correct.

## What the historical run showed

The baseline and changed tool ran the same 30-task benchmark with `deepseek-chat` and the same model settings, allowed-file policy, and scoring. There was one run per configuration. The intervention included both implementation and tool-description changes, so it cannot isolate each component's effect.

| Measure | Baseline | Changed tool |
| --- | ---: | ---: |
| Trace-identified editing self-damage | 13 events / 6 tasks | 0 events / 0 tasks |
| `edit_file` calls | 63 | 47 |
| Calls using `old_string` | 0 | 47 |
| Unmatched `old_string` calls | Not applicable | 0 |
| Total steps | 350 | 325 |
| Estimated tokens | 1,458,155 | 1,401,267 |
| Passed tasks | 22/30 | 25/30 |

The self-damage category comes from the historical trace review, including the agent recognizing its own mistaken edits. It is useful mechanism-level evidence for this sample, not a guarantee of zero future damage. The pass-count change included five fixes and two regressions; it does not independently establish a general improvement in model success.

There was no syntax-check hit in the changed run. That experiment therefore provides no direct evidence for the syntax check's contribution. It could not have caught every original mistake anyway: removing a needed assignment can leave perfectly valid syntax.

## The improvement exposed a second bug

Returning more code also exposed the classifier that searched observations for `error`. Replans rose from 58 to 78; the original review attributed 17 to edit feedback. Successful edits containing `from errors import NotFound` could be classified as failures.

That cost belongs alongside the benefits. Estimated tokens still fell 3.9% and steps 7.1% in this run, but the feedback path needed its own fix. [The next article](02-error-is-not-failure.en.md) explains why tool status must be distinguished from the code it carries.

To inspect the saved outcome comparison without model calls:

```bash
python -m dm_agent.benchmarks.score_diff bench_reports/ablation-scope-20260804.json bench_reports/editfix-20260804.json
```

Run from the repository root. Exit code 1 is expected because there are regressions. This compares stored results; it does not recreate the historical model run.

## Evidence

- [Full editing investigation, correction, and tradeoffs, devlog 38](../research-log/38-edit-file-precision.md)
- [Baseline report](../../bench_reports/ablation-scope-20260804.json) and [changed-tool report](../../bench_reports/editfix-20260804.json)
- [Current editing implementation](../../dm_agent/tools/file_tools.py)
- [Failure-classification follow-up, devlog 39](../research-log/39-observation-failure-classification.md)

[DM-Code-Agent](../../README.md) makes these tool interactions inspectable. [Try the no-key demo](../getting-started.en.md) to see a content-anchored edit together with its test evidence and exported report.
