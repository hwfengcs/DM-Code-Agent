"""Command-line interface for coding benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .models import BenchmarkRunConfig
from .runner import (
    BENCH_VARIANTS,
    DEFAULT_BENCH_VARIANTS,
    build_benchmark_manifest,
    run_benchmark_suite,
    write_json_report,
    write_markdown_report,
)
from .tasks import BENCHMARK_SUITES, get_benchmark_tasks

ALL_SUITES = sorted(BENCHMARK_SUITES.keys())


def parse_args(argv: Any = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DM-Code-Agent coding benchmarks.")
    parser.add_argument(
        "--suite",
        choices=ALL_SUITES,
        default="coding",
        help="Benchmark suite to run.",
    )
    parser.add_argument("--list", action="store_true", help="List benchmark tasks and exit.")
    parser.add_argument("--task", action="append", help="Task id to run. Can be repeated.")
    parser.add_argument("--variant", action="append", help="Variant name to run. Can be repeated.")
    parser.add_argument(
        "--all-variants",
        action="store_true",
        help="Run all benchmark variants instead of the default full variant.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    parser.add_argument("--markdown", type=Path, help="Write Markdown report to this path.")
    parser.add_argument("--provider", default="deepseek", help="Provider for live benchmark runs.")
    parser.add_argument("--model", help="Model name for live benchmark runs.")
    parser.add_argument("--base-url", help="Base URL for live benchmark runs.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument("--timeout", type=int, default=120, help="LLM request timeout.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat count per task/variant.")
    parser.add_argument("--max-steps", type=int, help="Override task max steps.")
    parser.add_argument(
        "--enable-adaptive-replanning",
        action="store_true",
        help="Enable deterministic error-signal-aware replanning. Default is off.",
    )
    parser.add_argument(
        "--max-replans",
        type=int,
        default=-1,
        help="Maximum replans when adaptive replanning is enabled; -1 means unlimited.",
    )
    parser.add_argument(
        "--cost-per-1k-tokens",
        type=float,
        default=0.0,
        help="Estimated provider cost per 1K tokens for local economics reports.",
    )
    parser.add_argument(
        "--declare-allowed-files",
        action="store_true",
        help=(
            "Append each task's allowed_changed_files to the prompt handed to the "
            "agent. Default is off, because existing baselines were run without it. "
            "Does not change the suite signature, so reports stay comparable."
        ),
    )
    parser.add_argument("--test-timeout", type=int, default=30, help="Hidden test timeout.")
    parser.add_argument(
        "--per-test-credit",
        action="store_true",
        help=(
            "Advisory: also run hidden tests node-by-node and report partial "
            "credit (strict scoring unchanged). Default is off."
        ),
    )
    parser.add_argument(
        "--manifest-only",
        type=Path,
        help="Write the suite manifest JSON to this path and exit (keyless, no runs).",
    )
    parser.add_argument(
        "--keep-workspaces",
        action="store_true",
        help="Keep temporary workspaces and include their paths in the report.",
    )
    parser.add_argument("--workspace-root", help="Directory for kept workspaces.")
    parser.add_argument("--trace-dir", help="Directory for per-run JSONL traces.")
    parser.add_argument(
        "--show-agent-output",
        action="store_true",
        help="Show live agent stdout during benchmark runs.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    if args.max_replans < -1:
        print("--max-replans must be -1 or greater.", file=sys.stderr)
        return 2
    validation_error = _validate_feature_args(args)
    if validation_error:
        print(validation_error, file=sys.stderr)
        return 2

    if args.manifest_only:
        tasks = get_benchmark_tasks(args.suite)
        manifest = build_benchmark_manifest(
            suite=args.suite,
            tasks=tasks,
            variants=BENCH_VARIANTS,
        )
        args.manifest_only.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_only.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Manifest written: {args.manifest_only} ({manifest['suite_signature']})")
        return 0

    if args.list:
        listed_tasks = [task.to_public_dict() for task in get_benchmark_tasks(args.suite)]
        listed_variants = [variant.__dict__ for variant in BENCH_VARIANTS]
        print(
            json.dumps(
                {"suite": args.suite, "tasks": listed_tasks, "variants": listed_variants},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    variant_names = args.variant
    variants: list[Any] | None = None
    if args.all_variants:
        variants = BENCH_VARIANTS
        variant_names = None
    elif not variant_names:
        variants = DEFAULT_BENCH_VARIANTS

    try:
        report = run_benchmark_suite(
            suite=args.suite,
            task_ids=args.task,
            variants=variants,
            variant_names=variant_names,
            config=BenchmarkRunConfig(
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                timeout=args.timeout,
                temperature=args.temperature,
                repeat=args.repeat,
                max_steps=args.max_steps,
                test_timeout=args.test_timeout,
                keep_workspaces=args.keep_workspaces,
                workspace_root=args.workspace_root,
                trace_dir=args.trace_dir,
                quiet=not args.show_agent_output,
                enable_adaptive_replanning=args.enable_adaptive_replanning,
                max_replans=args.max_replans,
                cost_per_1k_tokens=args.cost_per_1k_tokens,
                declare_allowed_files=args.declare_allowed_files,
                per_test_credit=args.per_test_credit,
            ),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.output:
        write_json_report(report, args.output)
    if args.markdown:
        write_markdown_report(report, args.markdown)

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


def _validate_feature_args(args: argparse.Namespace) -> str:
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
