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
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "(swebench_lite) Reuse completed results from --output when it "
            "exists, and checkpoint reports after each instance."
        ),
    )
    parser.add_argument(
        "--resume-from-output",
        type=Path,
        help="(swebench_lite) JSON report to reuse completed instance results from.",
    )
    parser.add_argument("--provider", default="deepseek", help="Provider for live benchmark runs.")
    parser.add_argument("--model", help="Model name for live benchmark runs.")
    parser.add_argument("--base-url", help="Base URL for live benchmark runs.")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key.")
    parser.add_argument("--timeout", type=int, default=120, help="LLM request timeout.")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat count per task/variant.")
    parser.add_argument("--max-steps", type=int, help="Override task max steps.")
    parser.add_argument(
        "--enable-reflexion",
        action="store_true",
        help="Retry failed agent trials with Reflexion lessons. Default is off.",
    )
    parser.add_argument(
        "--max-trials",
        type=int,
        default=3,
        help="Maximum trials when --enable-reflexion is set.",
    )
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
        "--enable-repeated-failure-policy-experiment",
        action="store_true",
        help=(
            "Enable an experimental loop-breaking strategy for repeated adaptive "
            "replan failures. Default is off."
        ),
    )
    parser.add_argument(
        "--cost-per-1k-tokens",
        type=float,
        default=0.0,
        help="Estimated provider cost per 1K tokens for local economics reports.",
    )
    parser.add_argument(
        "--enable-rag",
        action="store_true",
        help="Enable local BM25 RAG context retrieval for benchmark agent runs. Default is off.",
    )
    parser.add_argument("--rag-top-k", type=int, default=5, help="Top-K retrieved snippets.")
    parser.add_argument(
        "--rag-granularity",
        choices=["symbol", "file", "both"],
        default="symbol",
        help="Retrieval index granularity.",
    )
    parser.add_argument(
        "--rag-max-files",
        type=int,
        default=200,
        help="Maximum Python files to index for RAG.",
    )
    parser.add_argument(
        "--enable-critic",
        action="store_true",
        help="Enable critic review gate for benchmark agent completions. Default is off.",
    )
    parser.add_argument(
        "--self-consistency-runs",
        type=int,
        default=1,
        help="Run N fresh-workspace candidates and select one. Default is 1/off.",
    )
    parser.add_argument(
        "--self-consistency-strategy",
        choices=["majority_vote", "critic_score", "test_pass"],
        default="majority_vote",
        help="Selection strategy when --self-consistency-runs is greater than 1.",
    )
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


def _swebench_results_from_report(report: dict[str, Any]) -> List[Any]:
    from .swebench_lite.models import SWEBenchResult

    return [SWEBenchResult.from_dict(result) for result in report.get("results", [])]


def _load_swebench_resume_results(path: Path) -> List[Any]:
    with open(path, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    if report.get("mode") != SWEBENCH_LITE_SUITE:
        raise ValueError(f"{path} is not a SWE-bench Lite report.")
    return _swebench_results_from_report(report)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    tmp_path.replace(path)


def _write_swebench_outputs(
    report: dict[str, Any],
    *,
    output: Optional[Path],
    markdown: Optional[Path],
) -> None:
    if output:
        _atomic_write_text(output, json.dumps(report, indent=2, ensure_ascii=False))
    if markdown:
        from .swebench_lite.analyzer import render_full_analysis
        from .swebench_lite.runner import render_markdown_report

        analyzer_results = _swebench_results_from_report(report)
        _atomic_write_text(
            markdown,
            render_markdown_report(report) + "\n" + render_full_analysis(analyzer_results),
        )


def _run_swebench_lite(args: argparse.Namespace) -> int:
    try:
        from .swebench_lite.loader import fixed_subset_50, load_instances
        from .swebench_lite.runner import (
            run_swebench_lite,
        )
        from .swebench_lite.models import SWEBenchRunConfig
    except ImportError as exc:
        print(
            f"Failed to import the swebench_lite suite: {exc}\n"
            'Install with: pip install "dm-code-agent[swebench]"',
            file=sys.stderr,
        )
        return 2

    if args.max_trials < 1:
        print("--max-trials must be at least 1.", file=sys.stderr)
        return 2
    if args.max_replans < -1:
        print("--max-replans must be -1 or greater.", file=sys.stderr)
        return 2
    if args.self_consistency_runs > 1:
        print(
            "SWE-bench Lite self-consistency is intentionally not wired while real "
            "SWE-bench evaluation is frozen. Use coding/maintenance suites for plumbing smoke.",
            file=sys.stderr,
        )
        return 2
    validation_error = _validate_feature_args(args)
    if validation_error:
        print(validation_error, file=sys.stderr)
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
        enable_reflexion=args.enable_reflexion,
        max_trials=args.max_trials,
        enable_adaptive_replanning=args.enable_adaptive_replanning,
        max_replans=args.max_replans,
        enable_repeated_failure_policy_experiment=(args.enable_repeated_failure_policy_experiment),
        cost_per_1k_tokens=args.cost_per_1k_tokens,
        enable_rag=args.enable_rag,
        rag_top_k=args.rag_top_k,
        rag_granularity=args.rag_granularity,
        rag_max_files=args.rag_max_files,
        enable_critic=args.enable_critic,
        self_consistency_runs=args.self_consistency_runs,
        self_consistency_strategy=args.self_consistency_strategy,
    )

    resume_results: List[Any] = []
    resume_path: Optional[Path] = args.resume_from_output
    if args.resume and resume_path is None:
        if not args.output:
            print("--resume requires --output or --resume-from-output.", file=sys.stderr)
            return 2
        resume_path = args.output
    if resume_path is not None:
        if resume_path.exists():
            try:
                resume_results = _load_swebench_resume_results(resume_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"Failed to load resume report {resume_path}: {exc}", file=sys.stderr)
                return 2
            selected_ids = {instance.instance_id for instance in instances}
            reusable = [r for r in resume_results if r.instance_id in selected_ids]
            ignored = len(resume_results) - len(reusable)
            resume_results = reusable
            print(
                f"Resume: reusing {len(resume_results)} completed result(s)"
                f"{f'; ignored {ignored} outside current selection' if ignored else ''}.",
                file=sys.stderr,
            )
        elif args.resume:
            print(f"Resume report {resume_path} does not exist; starting fresh.", file=sys.stderr)

    progress_callback = None
    if args.output or args.markdown:

        def progress_callback(report: dict[str, Any]) -> None:
            _write_swebench_outputs(report, output=args.output, markdown=args.markdown)

    try:
        report = run_swebench_lite(
            instances,
            config=config,
            resume_results=resume_results,
            progress_callback=progress_callback,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _write_swebench_outputs(report, output=args.output, markdown=args.markdown)

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    return 0


def main(argv: Any = None) -> int:
    args = parse_args(argv)
    if args.max_trials < 1:
        print("--max-trials must be at least 1.", file=sys.stderr)
        return 2
    if args.max_replans < -1:
        print("--max-replans must be -1 or greater.", file=sys.stderr)
        return 2
    validation_error = _validate_feature_args(args)
    if validation_error:
        print(validation_error, file=sys.stderr)
        return 2

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
                enable_reflexion=args.enable_reflexion,
                max_trials=args.max_trials,
                enable_adaptive_replanning=args.enable_adaptive_replanning,
                max_replans=args.max_replans,
                enable_repeated_failure_policy_experiment=(
                    args.enable_repeated_failure_policy_experiment
                ),
                cost_per_1k_tokens=args.cost_per_1k_tokens,
                enable_rag=args.enable_rag,
                rag_top_k=args.rag_top_k,
                rag_granularity=args.rag_granularity,
                rag_max_files=args.rag_max_files,
                enable_critic=args.enable_critic,
                self_consistency_runs=args.self_consistency_runs,
                self_consistency_strategy=args.self_consistency_strategy,
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
    if args.enable_repeated_failure_policy_experiment and not args.enable_adaptive_replanning:
        return (
            "--enable-repeated-failure-policy-experiment requires " "--enable-adaptive-replanning."
        )
    if args.rag_top_k < 1:
        return "--rag-top-k must be at least 1."
    if args.rag_max_files < 1:
        return "--rag-max-files must be at least 1."
    if args.self_consistency_runs < 1:
        return "--self-consistency-runs must be at least 1."
    if args.self_consistency_strategy == "critic_score" and not args.enable_critic:
        return "--self-consistency-strategy critic_score requires --enable-critic."
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
