# Contributing to DM-Code-Agent

Thanks for helping improve DM-Code-Agent. The project is designed to stay small, readable,
and useful for people learning how code agents work.

## Local setup

```bash
uv sync --frozen --extra dev
```

Or the traditional way:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Development checks

Run these before opening a pull request:

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --list
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
python -m mypy dm_agent
```

CI installs from `uv.lock` (`uv sync --frozen --extra dev`) and runs the same commands on
Ubuntu and Windows for Python 3.10 / 3.11 / 3.12. **If you change dependencies in
`pyproject.toml`, re-run `uv lock` and commit the updated `uv.lock`** — CI fails on
`uv lock --check` otherwise.

## 提交前钩子

开发依赖安装完成后，为当前 clone 安装 hook：

```bash
uv run --frozen --extra dev pre-commit install
```

每次 commit 前会按顺序运行与 CI 相同的 Ruff、Black、mypy 与全量 pytest 命令。提交前也可
手动跑完整 hook，并检查所有已跟踪文件：

```bash
uv run --frozen --extra dev pre-commit run --all-files
```

若只需临时跳过一个明确无关的 hook，可用它的 id，例如 Bash 下
`SKIP=pytest git commit ...`，PowerShell 下先执行 `$env:SKIP="pytest"`。`git commit
--no-verify` 会跳过整套检查，只应在已用同一组命令手工验证且确有必要时使用；随后应清理
PowerShell 环境变量：`Remove-Item Env:SKIP`。

## Pull request guidelines

- Keep changes focused and easy to review.
- Add or update tests for behavior changes.
- Do not commit API keys, `.env`, `config.json`, or `mcp_config.json`.
- Prefer clear examples and docs for new agent capabilities.
- Use Conventional Commit prefixes (`feat:`, `fix:`, `refactor:`, `docs:`, `bench:`,
  `test:`, `chore:`) so `CHANGELOG.md` can be updated mechanically.
- Respect the layering contract: `core` / `tools` / `clients` / `memory` / `tracing` /
  `evals` / `benchmarks` must not import `dm_agent.cli`. Ruff's `TID251` enforces this;
  see the `banned-api` block in `pyproject.toml`.
- Do not add `# noqa` to source files. If a lint rule is genuinely wrong for this project,
  disable it in `pyproject.toml` with a written justification.
- **Never claim evaluation numbers you have not actually run.** Real SWE-bench / Docker /
  cross-model scoring is currently frozen.

## The first question to ask

> Does this really have to live in the kernel?

If your feature only needs to act at a few fixed points in the execution chain, it should be
an **extension**, not a new `--enable-xxx` flag and a new `if` branch in `ReactAgent`. The
kernel is deliberately minimal; PRs that grow it are likely to be sent back.

Read [`docs/extensions.md`](docs/extensions.md) and
[`docs/lifecycle-events.md`](docs/lifecycle-events.md) first. Adding a tool, a skill, a
provider, or a guard needs **zero changes** under `dm_agent/`.

## Good first contribution areas

- More test fixtures for tools and skills.
- More built-in skills (see "Adding a built-in skill" below).
- Better MCP server examples ([`docs/mcp.md`](docs/mcp.md)).
- Agent evaluation tasks and benchmark reports (see "Adding a benchmark task" below).

## Adding a tool

For your own use, or to distribute as a package: write an extension. No repository change
needed at all — see [`docs/extensions.md`](docs/extensions.md).

To ship a tool as a **built-in**, add it to `dm_agent/tools/__init__.py:_builtin_tools()` and
put the runner in a module under `dm_agent/tools/`. Built-ins are not a special case: they are
registered through the same `ExtensionAPI` as third-party extensions
(`register_builtin_tools(api)`, called from
`dm_agent/extensions/builtin.py:setup_builtin_extensions()`), they just happen to be the
lowest-priority source. Add a focused runner test under `tests/test_tools.py`.

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

A skill you only need locally can be a JSON file under `dm_agent/skills/custom/`, or come from
an extension via `api.register_skill(...)`. See [`docs/skills.md`](docs/skills.md).

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
