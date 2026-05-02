# DM-Code-Agent Evals

This directory contains deterministic, no-API-key evaluation entry points and optional
real-model evaluation entry points for the agent.
The implementation lives in `dm_agent.evals` so it can also be used as a package.

## Run

```bash
dm-agent-eval
python evals/run_evals.py
```

Write reports:

```bash
dm-agent-eval --output eval_reports/latest.json --markdown eval_reports/latest.md
```

Run one ablation slice:

```bash
dm-agent-eval --variant full --variant no_planning
dm-agent-eval --task json_repair --task tool_failure_replan
```

Run a small live-model eval with DeepSeek:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key
dm-agent-eval --real --provider deepseek --variant full --task real_read_file
```

Run the default live-model experiment matrix and write reports:

```bash
dm-agent-eval --real --provider deepseek \
  --output eval_reports/real_deepseek.json \
  --markdown eval_reports/real_deepseek.md
```

## What It Measures

- Success rate
- Average steps
- Average tool calls
- Estimated prompt/completion tokens
- Optional estimated cost
- Recovery events: JSON repair, parse error, unknown tool, invalid arguments, replan
- Skill activation runs

These evals are deterministic and use a scripted fake LLM client. They are designed to make
agent behavior reproducible in CI and easy to discuss in interviews.

Real-model evals reuse the same task, variant, validation, and report schema, but call the
configured provider. They are intentionally separated from CI because they spend API quota and
can vary by provider/model version.
