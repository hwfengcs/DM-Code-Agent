# Contributing to DM-Code-Agent

Thanks for helping improve DM-Code-Agent. The project is designed to stay small, readable,
and useful for people learning how code agents work.

## Local setup

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

On Linux or macOS, activate with `source .venv/bin/activate`.

## Development checks

Run these before opening a pull request:

```bash
python -m compileall dm_agent main.py
python -m pytest
python -m ruff check .
python -m black --check .
```

## Pull request guidelines

- Keep changes focused and easy to review.
- Add or update tests for behavior changes.
- Do not commit API keys, `.env`, `config.json`, or `mcp_config.json`.
- Prefer clear examples and docs for new agent capabilities.

## Good first contribution areas

- More test fixtures for tools and skills.
- More built-in skills.
- Better MCP server examples.
- Agent evaluation tasks and benchmark reports.
