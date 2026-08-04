"""评测阶段：把 predictions.jsonl 交给**官方** SWE-bench harness。

这一层刻意做得很薄——判定 resolved 的必须是官方代码，我们一行判分逻辑都不写，
否则拿到的数字与公开 leaderboard 不可比，等于白跑。

本脚本跑在 .swebench-venv 里（那里装了 swebench 4.1.0），且需要
``PYTHONPATH=swebench/_winshim`` 以在 Windows 上补上 Unix-only 的 resource 模块。
README.md 有可直接复制的命令。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def summarize(report_path: Path) -> dict[str, object]:
    """把官方 harness 的报告压成一行结论。"""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    submitted = report.get("submitted_instances", 0)
    resolved = report.get("resolved_instances", 0)
    return {
        "submitted": submitted,
        "completed": report.get("completed_instances", 0),
        "resolved": resolved,
        "unresolved": report.get("unresolved_instances", 0),
        "empty_patch": report.get("empty_patch_instances", 0),
        "error": report.get("error_instances", 0),
        "resolve_rate": round(resolved / submitted, 4) if submitted else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score predictions with the official harness.")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--summarize-only",
        type=Path,
        default=None,
        help="Skip evaluation and just summarize an existing report json.",
    )
    args = parser.parse_args(argv)

    if args.summarize_only is not None:
        print(json.dumps(summarize(args.summarize_only), indent=2))
        return 0

    from swebench.harness.run_evaluation import main as run_evaluation

    run_evaluation(
        dataset_name="princeton-nlp/SWE-bench_Verified",
        split="test",
        instance_ids=[],
        predictions_path=str(args.predictions),
        max_workers=args.max_workers,
        force_rebuild=False,
        cache_level="env",
        clean=False,
        open_file_limit=4096,
        run_id=args.run_id,
        timeout=args.timeout,
        namespace="swebench",
        rewrite_reports=False,
        modal=False,
        instance_image_tag="latest",
        env_image_tag="latest",
        report_dir=".",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
