# Draft: A successful file read sent my coding agent into error recovery

Status: prepared, not published. Adapt the title and length to the community and disclose
that you maintain DM-Code-Agent. Evidence is linked below; no new benchmark result is claimed.

---

This valid Python import once sent my coding agent into failure recovery:

```python
from errors import NotFound
```

The read succeeded. My observation classifier scanned the whole tool response for failure
markers, including the substring `error`. Source code carried by a tool was being treated as
the tool's own status.

Adding post-edit source excerpts made the defect more visible: better feedback brought back
more source text that the same classifier could misread. In one historical review of 30 traces,
38 of 84 classified tool failures were false positives. Reclassifying those same observations
removed those 38 false positives while retaining the 46 previously detected real failures.
That is a result for the inspected observations, not a claim of universal accuracy or higher
agent success rates.

I maintain [DM-Code-Agent](https://github.com/hwfengcs/DM-Code-Agent), a local Python coding
agent built so these failures can be inspected. The fix distinguishes tool status from carried
content and uses process exit codes for command results. Unknown extension tools retain a
conservative fallback.

You can read the [full diagnosis and offline reproduction](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/articles/02-error-is-not-failure.en.md),
or try the [browser demo](https://hwfengcs.github.io/DM-Code-Agent/): two runs make the same
repair and both claim completion, but only one runs the tests. Their reports show the evidence
side by side. Assistant decisions in that demo are scripted; the edits and unittest checks
really execute, and no model key is needed.

The project exports a single HTML report that opens without a server. I would be interested
in concrete cases where your agent's final answer concealed a tool failure or missing check.
The [English setup guide](https://github.com/hwfengcs/DM-Code-Agent/blob/main/docs/getting-started.en.md)
covers the local workflow.

## Short version

Reading `from errors import NotFound` once triggered my coding agent's error recovery.
The tool succeeded; my classifier mistook source text for status.
I wrote up the failure and built an inspectable demo: two completed repairs, only one with
test evidence. Python, MIT, no-key demo, standalone HTML reports.

Demo: https://hwfengcs.github.io/DM-Code-Agent/

Source and diagnosis: https://github.com/hwfengcs/DM-Code-Agent
