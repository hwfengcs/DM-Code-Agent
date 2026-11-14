# Getting started

[简体中文](getting-started.md) · [Project](../README.md) · [Browser demo](https://hwfengcs.github.io/DM-Code-Agent/)

Inspect a complete run without a model key, then try a small task in your own repository.

## Install

Use Python 3.10+ in a virtual environment. The release wheel includes the browser console;
you do not need Node.js:

```bash
python -m pip install "dm-code-agent[web] @ https://github.com/hwfengcs/DM-Code-Agent/releases/download/v2.1.0/dm_code_agent-2.1.0-py3-none-any.whl"
```

For an isolated tool installation, replace `python -m pip install` with `uv tool install`.
Leave out `[web]` if you only need the CLI. Packages and checksums are attached to
[v2.1.0](https://github.com/hwfengcs/DM-Code-Agent/releases/tag/v2.1.0).
Package-name installation from PyPI is not available yet; use the release URL above.

## Inspect your first run

```bash
dm-agent-demo --output demo-run
dm-agent-web --sessions-dir demo-run/sessions --read-only
```

Open the complete local URL printed by the server, including its access token. Choose a run:

| Run | Evidence to inspect |
| --- | --- |
| `verified.jsonl` | Four tests, one initial failure, a retry-boundary edit, then four passing tests |
| `unverified.jsonl` | The same edit, followed by completion without a test run; a verification-gap warning |

The demo uses scripted assistant decisions with real file tools and Python unittest. It makes
no model requests, reads no user configuration or extensions, and only writes to a new or empty
output directory. For a second run, use another directory name. This demonstrates the inspection
workflow; it does not measure model performance. Installation itself needs network access.

Terminal equivalents:

```bash
dm-agent-trace view demo-run/sessions/verified.jsonl
dm-agent-trace analyze demo-run/sessions/unverified.jsonl
dm-agent-trace diff demo-run/sessions/unverified.jsonl demo-run/sessions/verified.jsonl
```

## Save a report

```bash
dm-agent-trace export demo-run/sessions/verified.jsonl --output repair.html --include-content
```

Open `repair.html` in any browser. The file works without a server and shows test evidence,
execution steps, and replacement excerpts. This demo contains only bundled sample code.

For your own sessions, omit `--include-content` to start with a structural summary. Adding it
includes redacted content that you should review before sharing: automatic redaction cannot
recognize every secret. Replacement excerpts are not a complete Git diff. Export refuses to
overwrite an existing report unless you add `--force`, and cannot overwrite the source session.

## Connect a model

In your target repository, create a `.env` file for the provider you want to use:

```dotenv
DEEPSEEK_API_KEY=your-key
```

| Environment variable | Provider argument |
| --- | --- |
| `DEEPSEEK_API_KEY` | `--provider deepseek` (default) |
| `OPENAI_API_KEY` | `--provider openai` |
| `CLAUDE_API_KEY` | `--provider claude` |
| `GEMINI_API_KEY` | `--provider gemini` |

Existing environment variables take precedence over `.env`. DM reads `./.env` first and then
`~/.dm_agent/.env`; the latter is useful for a global installation. Keep keys out of Git.

Start with a small task whose answer you can check:

```bash
dm-agent "Inspect this repository and identify the modules that most need tests" --provider deepseek --max-steps 12 --trace sessions/review.jsonl --show-steps
dm-agent-trace analyze sessions/review.jsonl
```

Then try one specific maintenance task, such as adding a regression test for a known edge case.
Review `git diff` and run the relevant tests yourself. The agent runs with your local file and
command permissions; use a Git checkout you can review. It is not a sandbox.

The built-in `openai` provider uses the Responses API. A server that only exposes
`/v1/chat/completions` needs the [Chat Completions extension recipe](local-models.en.md),
which includes Xinference/Qwen configuration and troubleshooting.

## Configuration and the console

Non-secret settings live in `./config.json` or `~/.dm_agent/config.json`. A project file takes
precedence over the user file. Command-line arguments override saved settings:

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "max_steps": 12,
  "show_steps": true
}
```

Run `dm-agent-web` for the conversation and inspection console. Use
`dm-agent-web --sessions-dir sessions --read-only` to inspect existing sessions only.
`--trace` is redacted by default. Full model I/O capture and checkpoint recovery are separate
options; a trace and a checkpoint must never point at the same file.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| `dm-agent` is not found | Activate the installation environment; with `uv tool install`, check `uv tool update-shell` |
| `demo-run` already contains files | Choose a new output path; keep the original evidence |
| Missing API key | Check the provider's variable above and the `.env` location in the target workspace |
| Local console returns unauthorized | Open the complete token-bearing URL printed by that server process |
| Local model returns 404 on `/responses` | Use the Chat Completions extension instead of changing only `--base-url` |
| Agent says it finished | Inspect the recorded tests and changes; completion alone is not proof of correctness |

## Develop from source

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
uv sync --frozen --extra dev
uv run --frozen dm-agent-demo --output demo-run
uv run --frozen python -m pytest
uv run --frozen python -m dm_agent.evals.cli --variant full --task direct_finish
```

Tests and deterministic evals need no API key. The [contribution guide](../CONTRIBUTING.md)
lists the complete checks. Read the [engineering articles](articles/README.md) for small,
reproducible examples of failures found through traces.
