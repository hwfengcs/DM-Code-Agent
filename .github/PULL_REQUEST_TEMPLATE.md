<!--
Thanks for opening a pull request to DM-Code-Agent.

Please make sure your change is in scope (`AGENTS.md`, `CONTRIBUTING.md`)
and that you have run the local development checks listed below.
-->

## Summary

<!-- One short paragraph describing what this PR changes and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / capability
- [ ] Refactor (no behavior change)
- [ ] Documentation only
- [ ] Benchmark / eval change
- [ ] Trace schema or replay change
- [ ] Tooling / CI

## Implementation notes

<!--
Anything reviewers need to know to make sense of the diff:
- new modules, key files, public API additions
- prompt or trace schema changes
- migration / backward-compat notes
-->

## Verification

Run before requesting review:

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m dm_agent.benchmarks.cli --suite maintenance --list
python -m ruff check .
python -m black --check .
```

If this change touches benchmarks or live-model behavior:

- [ ] Attached relevant `bench_reports/*.md` or `eval_reports/*.md`.
- [ ] Documented the model and provider used.
- [ ] Documented the random seed / sampling parameters.

## Safety checklist

- [ ] No API keys, `.env`, `config.json`, or `mcp_config.json` in the diff.
- [ ] No new default-on dangerous tool replay or shell execution paths.
- [ ] Trace defaults still keep full LLM I/O capture opt-in.

## Related issues / research log

<!--
Link to issues, discussions, or `docs/research-log/*.md` entries that motivated
this change.
-->
