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
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --list
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
```

CI runs the same matrix on Ubuntu and Windows for Python 3.10 / 3.11 / 3.12.

## Pull request guidelines

- Keep changes focused and easy to review.
- Add or update tests for behavior changes.
- Do not commit API keys, `.env`, `config.json`, or `mcp_config.json`.
- Prefer clear examples and docs for new agent capabilities.
- Use Conventional Commit prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `bench:`,
  `test:`, `chore:`) so `CHANGELOG.md` can be updated mechanically.

## Good first contribution areas

- More test fixtures for tools and skills.
- More built-in skills (see "Adding a built-in skill" below).
- Better MCP server examples.
- Agent evaluation tasks and benchmark reports (see "Adding a benchmark task" below).

## Adding a built-in skill

A skill bundles a domain-specific system prompt and zero or more specialized tools.
The minimum surface is `dm_agent/skills/base.py:BaseSkill`.

1. Create a new file under `dm_agent/skills/builtin/`, e.g. `rust_expert.py`.
2. Subclass `BaseSkill`. Implement:
   - `get_metadata()` returning a `SkillMetadata(name=..., display_name=..., description=...,
     keywords=[...], version=...)`.
   - `get_system_prompt_section()` returning the prompt fragment to inject when active.
   - `get_tools()` returning a list of `Tool` instances (can be empty).
3. Register it in `dm_agent/skills/builtin/__init__.py:get_builtin_skills()`.
4. Add a focused unit test under `tests/test_skills_and_mcp.py` that activates the skill
   on a task whose keywords match, and asserts the metadata and tool count.
5. If the skill ships a tool, write a test for that tool's runner separately.

The selector matches activation by keyword overlap. Keep the keyword list specific —
"python" matches everything; "django, fastapi, sqlalchemy" is more useful.

## Adding a benchmark task

The maintenance suite (`dm_agent/benchmarks/tasks.py:get_maintenance_tasks()`) is where
new realistic repository tasks should land first.

1. Add a `BenchmarkTask` entry. Required fields:
   - `task_id`: short, kebab-case, unique.
   - `prompt`: written so the agent can solve from the task text alone.
   - `setup_files`: starting workspace, including a small visible test the agent can run.
   - `hidden_files`: hidden tests run *after* the agent finishes; these decide pass/fail.
   - `max_steps`: budget the agent has.
   - `tags`: free-form labels used in reports.
2. Optional but encouraged:
   - `allowed_changed_files`: limit which files the agent may touch.
   - `required_changed_files`: files the agent must touch (e.g., regression tests).
3. Add a row to `tests/test_coding_benchmarks.py` (or the maintenance equivalent) that
   loads the task and verifies metadata round-trips through `to_public_dict()`.
4. Optional: run the task with a real provider once and attach a fresh
   `bench_reports/*.md` to the PR. Include the seed and provider used.

A good task is one where:

- The visible tests are insufficient to fully specify behavior.
- The hidden tests cover an edge case the agent should infer from the prompt.
- Solving it requires multiple file reads, not just a single edit.

## Adding a research-log entry

If your contribution is significant enough to warrant a write-up — for example a new
algorithm, a non-trivial ablation, or a negative result — add a Markdown entry under
`docs/research-log/NN-slug.md` and link it from `docs/research-log/README.md`. Keep the
format described in that README.

