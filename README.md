<div align="center">

<picture>
  <source media="(max-width: 640px)" srcset="docs/media/readme-hero-mobile.svg">
  <img src="docs/media/readme-hero.svg" alt="DM-Code-Agent — Every change. In plain sight." width="1280">
</picture>

<h1>DM-Code-Agent</h1>

<p><strong>A coding agent you can inspect.</strong><br>Trace the changes. Diagnose the failure. Check the test evidence.</p>

<p>
  <a href="https://github.com/hwfengcs/DM-Code-Agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/hwfengcs/DM-Code-Agent/ci.yml?branch=main&amp;style=flat-square&amp;label=build&amp;labelColor=18251f" alt="CI status"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10%2B-81ecb0?style=flat-square&amp;labelColor=18251f" alt="Python 3.10 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-81ecb0?style=flat-square&amp;labelColor=18251f" alt="MIT license"></a>
</p>

<p><strong>English</strong> · <a href="README_ZH.md">简体中文</a></p>

<p>
  <a href="https://hwfengcs.github.io/DM-Code-Agent/"><strong>Interactive demo</strong></a> &nbsp; / &nbsp;
  <a href="#try-it-without-an-api-key"><strong>Quick start</strong></a> &nbsp; / &nbsp;
  <a href="docs/case-studies/failure-classification/README.md"><strong>Real maintenance case</strong></a> &nbsp; / &nbsp;
  <a href="docs/README.md"><strong>Docs</strong></a>
</p>

</div>

DM-Code-Agent works in your local repository and keeps an append-only record of each run.
Follow the evidence in the terminal or browser, then export a report another developer can open.

- **See the change.** Reads, edits, commands, and test output in one execution trail.
- **Find the gap.** Inspect failures, recovery attempts, and completion without recorded verification.
- **Make it yours.** Extend tools, providers, and lifecycle hooks around a readable Python agent.

## Watch the evidence

**Two runs. The same edit. Only one runs the tests.**

<a href="https://hwfengcs.github.io/DM-Code-Agent/">
  <picture>
    <source media="(prefers-reduced-motion: reduce)" srcset="docs/media/demo-preview.png">
    <img src="docs/media/readme-demo.gif" alt="A tested repair shows failing then passing checks; an untested repair shows a verification gap. Open the interactive demo to inspect both." width="880">
  </picture>
</a>

*10-second excerpt of the real browser walkthrough. Scripted assistant decisions; real file edits
and unittest checks. No model key required. [Watch all 38 seconds](docs/media/demo-walkthrough.mp4).*

## Try it without an API key

Python 3.10+, three commands. The release wheel includes the browser console; no Node.js needed.

```bash
pip install "dm-code-agent[web] @ https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl"
dm-agent-demo --output demo-run
dm-agent-web --sessions-dir demo-run/sessions --read-only
```

Open the complete local URL printed by the server. Choose `verified.jsonl` or `unverified.jsonl`
and inspect the difference. Use a new or empty output directory.

<details>
<summary><strong>Inside the demo · terminal inspection · HTML export</strong></summary>

| Run | Evidence |
| --- | --- |
| `verified.jsonl` | A retry-boundary bug, a failing test, an edit, and passing checks |
| `unverified.jsonl` | The same edit without a test run; the analyzer flags the verification gap |

The scripted client drives the real agent, file tools, and Python unittest. It makes no model
calls, reads no user configuration or extensions, and writes only to the chosen new or empty
directory. It demonstrates inspectability, not model performance.

```bash
dm-agent-trace analyze demo-run/sessions/unverified.jsonl
dm-agent-trace export demo-run/sessions/verified.jsonl --output report.html --include-content
```

Open `report.html` without a server. The demo contains only bundled sample code. For real sessions,
export defaults to a structural summary; `--include-content` adds redacted task, tool, and edit
excerpts. Review those reports before sharing: redaction cannot recognize every secret.

</details>

## Use it in your repository

Set your provider's key: `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `CLAUDE_API_KEY`, or `GEMINI_API_KEY`.
Run from a Git checkout you can review:

```bash
dm-agent "Inspect this repository and identify the modules that most need tests" --provider deepseek --trace sessions/review.jsonl --show-steps
dm-agent-trace analyze sessions/review.jsonl
```

**[Configuration and first task](docs/getting-started.en.md)** · **[Xinference / local-model recipe](docs/local-models.en.md)** · **[Web console](docs/web.md)**

The agent can modify files and run commands with your local permissions; it is not a sandbox.
`--trace` is redacted by default. Full model I/O, checkpoints, and tool replay have separate,
explicit controls. [Session privacy and replay](docs/tracing.md).

## What makes a run inspectable?

| Your question | The evidence you can inspect |
| --- | --- |
| **What changed?** | Ordered tool calls, arguments, observations, and replacement excerpts |
| **Where did it fail?** | Failure-stage analysis and recovery attempts |
| **Did it verify?** | Recorded validation actions and a verification-gap signal |
| **What changed between runs?** | Trace comparison and per-task benchmark regressions |
| **What happened to old context?** | Compaction appends derived records; originals remain available |

The CLI and console share the same analysis functions. Standalone HTML reports need no server.
Recorded checks are not a proof of correctness, and replacement excerpts are not a complete Git
diff. Explicit replay and checkpoint-based forks are available for local investigation.

## A real repair, with the rough edges left in

> **12 targeted checks passed. The broader suite still failed.**
>
> A live model attempted to repair a historical defect in this repository. Two broader checks
> remained failing, and the agent exhausted its step budget. The incomplete result is preserved
> with its patch, supplied tests, token usage, and an independent offline reproduction.

**[Inspect the live run](https://hwfengcs.github.io/DM-Code-Agent/cases/failure-classification.html)** · **[Read and reproduce the case](docs/case-studies/failure-classification/README.md)**

## Field notes

Small failures, useful lessons. Each article links its original evidence and an offline reproduction.

| Story | What we learned |
| --- | --- |
| [**More steps did not establish a better agent**](docs/articles/01-more-steps.en.md) | Pass counts rose from 22 to 24, alongside four regressions and 30.6% more estimated tokens. |
| [**When source code says “error”**](docs/articles/02-error-is-not-failure.en.md) | `from errors import NotFound` was mistaken for tool failure; reclassification removed 38 false positives in the inspected traces. |
| [**Find the text before changing the code**](docs/articles/03-content-anchored-edits.en.md) | Content-anchored edits addressed a line-range failure mode, then exposed another bug. |

The bundled benchmark has **30 hidden-test tasks** across coding and maintenance. Historical runs
support conclusions about those configurations, not a leaderboard claim. The demo is not an
evaluation. [Methodology](docs/benchmarks.md) · [Project status](docs/project-status.md) · [Research logs](docs/research-log/).

## Build and verify

<details>
<summary><strong>Develop from source — tests and deterministic evals need no API key</strong></summary>

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev
uv run --frozen dm-agent-demo --output demo-run
uv run --frozen python -m pytest
uv run --frozen python -m dm_agent.evals.cli --variant full --task direct_finish
```

The [contribution guide](CONTRIBUTING.md) and [agent instructions](AGENTS.md) list the complete
checks. [Extension examples](examples/) show how to add behavior outside the kernel.

</details>

## Find your next step

| Start here | Go deeper |
| --- | --- |
| [Getting started](docs/getting-started.en.md) · [中文首页](README_ZH.md) | [Architecture](docs/architecture.md) |
| [Local models / Xinference](docs/local-models.en.md) | [Provider extension example](examples/openai_compatible.py) |
| [CLI reference](docs/cli.md) · [Web console](docs/web.md) | [Extension API](docs/extensions.md) |
| [Sessions, privacy, and HTML export](docs/tracing.md) | [Benchmarks](docs/benchmarks.md) |
| [Bilingual articles](docs/articles/README.md) | [Full documentation index](docs/README.md) |

The homepage, setup guide, local-model recipe, and articles are bilingual; deeper reference docs
are mostly in Chinese. Reproducible issues and focused contributions are welcome.

<div align="center">

**If the evidence helps, give the project a star.**

[Contribute](CONTRIBUTING.md) · [Report a security issue](SECURITY.md) · [MIT license](LICENSE)

</div>
