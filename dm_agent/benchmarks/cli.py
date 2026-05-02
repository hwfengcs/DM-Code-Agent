"""Command-line interface for coding benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional

from .models import BenchmarkRunConfig
from .runner import (
    BENCH_VARIANTS,
    DEFAULT_BENCH_VARIANTS,
    run_benchmark_suite,
    write_json_report,
    write_markdown_report,
)
from .tasks import BENCHMARK_SUITES, get_benchmark_tasks

SWEBENCH_LITE_SUITE = "swebench_lite"
ALL_SUITES = sorted(set(BENCHMARK_SUITES.keys()) | {SWEBENCH_LITE_SUITE})


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
    parser.add_argument("--test-timeout", type=int, default=30, help="Hidden test timeout.")
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

    # SWE-bench Lite specific options.
    parser.add_argument(
        "--instance-id",
        action="append",
        help="(swebench_lite) instance id to run. Can be repeated. Defaults to the deterministic 50-instance subset.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        help="(swebench_lite) cap on the number of instances after subset/filter selection.",
    )
    parser.add_argument(
        "--use-docker",
        action="store_true",
        help="(swebench_lite) Tier-2 docker-based verification. Currently raises NotImplementedError.",
    )
    parser.add_argument(
        "--snapshot-path",
        help="(swebench_lite) override the JSONL snapshot path used to load instances offline.",
    )
    parser.add_argument(
        "--instance-test-timeout",
        type=int,
        default=300,
        help="(swebench_lite) per-pytest-node timeout, seconds.",
    )
    return parser.parse_args(argv)


def _list_swebench_lite(args: argparse.Namespace) -> int:
    """Print the deterministic 50-instance subset (or a provided slice) as JSON."""
    try:
        from .swebench_lite.loader import (
            DEFAULT_SPLIT,
            fixed_subset_50,
            load_instances,
            subset_signature,
        )
    except ImportError as exc:
        print(
            f"Failed to import the swebench_lite suite: {exc}\n"
            'Install with: pip install "dm-code-agent[swebench]"',
            file=sys.stderr,
        )
        return 2

    try:
        if args.instance_id:
            instances = load_instances(
                instance_ids=args.instance_id,
                snapshot_path=args.snapshot_path,
            )
        else:
            instances = fixed_subset_50()
    except RuntimeError as exc:
        # Friendly message when datasets library is not installed.
        print(str(exc), file=sys.stderr)
        return 2

    if args.max_instances is not None:
        instances = instances[: args.max_instances]

    payload = {
        "suite": SWEBENCH_LITE_SUITE,
        "split": DEFAULT_SPLIT,
        "subset_seed": 42,
        "subset_signature": subset_signature(instances),
        "count": len(instances),
        "instances": [inst.to_public_dict() for inst in instances],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _run_swebench_lite(args: argparse.Namespace) -> int:
    try:
        from .swebench_lite.loader import fixed_subset_50, load_instances
        from .swebench_lite.runner import (
            render_markdown_report,
            run_swebench_lite,
        )
        from .swebench_lite.analyzer import render_full_analysis
        from .swebench_lite.models import SWEBenchResult, SWEBenchVerification, SWEBenchRunConfig
    except ImportError as exc:
        print(
            f"Failed to import the swebench_lite suite: {exc}\n"
            'Install with: pip install "dm-code-agent[swebench]"',
            file=sys.stderr,
        )
        return 2

    try:
        if args.instance_id:
            instances = load_instances(
                instance_ids=args.instance_id,
                snapshot_path=args.snapshot_path,
            )
        else:
            instances = fixed_subset_50()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.max_instances is not None:
        instances = instances[: args.max_instances]
    if not instances:
        print("No instances selected.", file=sys.stderr)
        return 2

    config = SWEBenchRunConfig(
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        max_steps=args.max_steps or 60,
        temperature=args.temperature,
        test_timeout=args.instance_test_timeout,
        use_docker=args.use_docker,
        keep_workspaces=args.keep_workspaces,
        workspace_root=args.workspace_root,
        trace_dir=args.trace_dir,
        quiet=not args.show_agent_output,
    )

    try:
        report = run_swebench_lite(instances, config=config)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Reconstruct typed results for analyzer (results in the report dict are
    # already serialized; re-hydrate the minimal subset we need).
    analyzer_results: List[SWEBenchResult] = []
    for r in report.get("results", []):
        verif_dict = r["verification"]
        verif = SWEBenchVerification(
            patch_applied=verif_dict["patch_applied"],
            fail_to_pass_pass=verif_dict["fail_to_pass_pass"],
            fail_to_pass_total=verif_dict["fail_to_pass_total"],
            pass_to_pass_pass=verif_dict["pass_to_pass_pass"],
            pass_to_pass_total=verif_dict["pass_to_pass_total"],
            stdout_tail=verif_dict.get("stdout_tail", ""),
            stderr_tail=verif_dict.get("stderr_tail", ""),
            duration_seconds=verif_dict.get("duration_seconds", 0.0),
            error=verif_dict.get("error"),
        )
        analyzer_results.append(
            SWEBenchResult(
                instance_id=r["instance_id"],
                repo=r["repo"],
                success=r["success"],
                failure_reason=r.get("failure_reason", ""),
                final_answer=r.get("final_answer", ""),
                actions=r.get("actions", []),
                steps_count=r.get("steps_count", 0),
                tool_calls=r.get("tool_calls", 0),
                duration_seconds=r.get("duration_seconds", 0.0),
                prompt_chars=r.get("prompt_chars", 0),
                completion_chars=r.get("completion_chars", 0),
                estimated_tokens=r.get("estimated_tokens", 0),
                request_count=r.get("request_count", 0),
                metadata=r.get("metadata", {}),
                verification=verif,
                prediction=r.get("prediction", ""),
                workspace_path=r.get("workspace_path", ""),
                trial=r.get("trial", 1),
            )
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(render_markdown_report(report))
            handle.write("\n")
            handle.write(render_full_analysis(analyzer_results))

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


def main(argv: Any = None) -> int:
    args = parse_args(argv)

    if args.suite == SWEBENCH_LITE_SUITE:
        if args.list:
            return _list_swebench_lite(args)
        return _run_swebench_lite(args)

    if args.list:
        tasks = [task.to_public_dict() for task in get_benchmark_tasks(args.suite)]
        variants = [variant.__dict__ for variant in BENCH_VARIANTS]
        print(
            json.dumps(
                {"suite": args.suite, "tasks": tasks, "variants": variants},
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    variant_names = args.variant
    variants: Optional[List[Any]] = None
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


if __name__ == "__main__":
    raise SystemExit(main())
