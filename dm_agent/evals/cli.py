"""Command-line interface for deterministic and real-model evals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .real_runner import REAL_DEFAULT_VARIANTS, RealEvalConfig, get_real_tasks, run_real_suite
from .runner import DEFAULT_VARIANTS, run_suite, write_json_report, write_markdown_report
from .tasks import get_builtin_tasks


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DM-Code-Agent evals.")
    parser.add_argument("--list", action="store_true", help="List built-in eval tasks and exit.")
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run live model evals instead of deterministic scripted evals.",
    )
    parser.add_argument("--task", action="append", help="Task id to run. Can be repeated.")
    parser.add_argument("--variant", action="append", help="Variant name to run. Can be repeated.")
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--markdown", type=Path, help="Write Markdown report to this path.")
    parser.add_argument("--provider", default="deepseek", help="Provider for --real evals.")
    parser.add_argument("--model", help="Model name for --real evals.")
    parser.add_argument("--base-url", help="Base URL for --real evals.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument(
        "--timeout", type=int, default=120, help="Request timeout for --real evals."
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for --real evals.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat count for each real task/variant pair.",
    )
    parser.add_argument(
        "--show-agent-output",
        action="store_true",
        help="Show live agent stdout during --real evals.",
    )
    parser.add_argument(
        "--cost-per-1k-tokens",
        type=float,
        default=0.0,
        help="Optional estimated cost per 1K tokens for reporting.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)

    if args.list:
        task_source = get_real_tasks() if args.real else get_builtin_tasks()
        variant_source = REAL_DEFAULT_VARIANTS if args.real else DEFAULT_VARIANTS
        tasks = [task.to_public_dict() for task in task_source]
        variants = [variant.__dict__ for variant in variant_source]
        print(json.dumps({"tasks": tasks, "variants": variants}, indent=2, ensure_ascii=False))
        return 0

    if args.real:
        report = run_real_suite(
            task_ids=args.task,
            variant_names=args.variant,
            config=RealEvalConfig(
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                timeout=args.timeout,
                temperature=args.temperature,
                repeat=args.repeat,
                cost_per_1k_tokens=args.cost_per_1k_tokens,
                quiet=not args.show_agent_output,
            ),
        )
    else:
        report = run_suite(
            task_ids=args.task,
            variant_names=args.variant,
            cost_per_1k_tokens=args.cost_per_1k_tokens,
        )

    if args.output:
        write_json_report(report, args.output)
    if args.markdown:
        write_markdown_report(report, args.markdown)

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
