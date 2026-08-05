"""SWE-bench Verified 预测 CLI。

    python -m swebench_verified.run --limit 10 --output preds.jsonl

产出的 JSONL 直接喂给官方 harness（见 evaluate.py 与 README.md）。
本脚本跑在**主 venv**里（需要 dm_agent）；评测跑在 .swebench-venv 里。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .dataset import fetch_instances
from .predict import docker_preflight, predict_one

DEFAULT_CACHE = Path("swebench_work/instances.jsonl")

# 工作区**刻意放在系统临时目录**，不放在项目目录下。
#
# 实测踩过：工作区放 swebench_work/workspaces/<id> 时，agent 用 run_shell 爬到
# 父目录读走了 swebench_work/instances.jsonl——那里面有 FAIL_TO_PASS，等于把隐藏
# 测试名喂给了被测对象，分数直接作废。放到 tempdir 后，工作区的父目录只有其他
# 实例的 checkout，没有任何题目元数据。
DEFAULT_WORKSPACES = Path(tempfile.gettempdir()) / "dm-agent-swebench"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run DM-Code-Agent over SWE-bench Verified.")
    parser.add_argument("--limit", type=int, default=10, help="How many instances (dataset order).")
    parser.add_argument("--output", type=Path, required=True, help="predictions.jsonl path.")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--trace-dir", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACES)
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep each checkout after predicting (a few hundred MB per instance).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip instances already present in --output.",
    )
    args = parser.parse_args(argv)

    docker_error = docker_preflight()
    if docker_error:
        print(f"docker 不可用：{docker_error}", file=sys.stderr)
        print("请确认 Docker Desktop 正在运行（docker info 能返回版本号）后重试。", file=sys.stderr)
        return 2

    instances = fetch_instances(args.limit, cache_path=args.cache)
    print(f"loaded {len(instances)} instances from SWE-bench Verified")

    done: set[str] = set()
    kept: list[str] = []
    if args.resume and args.output.exists():
        retryable = 0
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            # 只跳过真正跑过 agent 的题。harness_error 是环境问题（daemon 挂了、
            # 镜像拉不下来），把它当"已完成"会让重跑静默跳过全部失败题——
            # 实测踩过：daemon 中途退出，10 题全记成 harness_error。
            if record.get("dm_status") == "harness_error":
                retryable += 1
                continue
            done.add(record["instance_id"])
            kept.append(line)
        print(f"resume: {len(done)} already predicted, {retryable} will be retried")
        # 把可重试的记录从文件里清掉，避免同一 instance_id 出现两条。
        if retryable:
            args.output.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.output.open("a" if args.resume else "w", encoding="utf-8") as handle:
        for index, instance in enumerate(instances, start=1):
            instance_id = instance["instance_id"]
            if instance_id in done:
                continue
            print(
                f"[{index}/{len(instances)}] {instance_id} ({instance.get('difficulty', '?')})",
                flush=True,
            )
            try:
                record = predict_one(
                    instance,
                    workspace_root=args.workspace_root,
                    provider=args.provider,
                    model=args.model,
                    max_steps=args.max_steps,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    trace_dir=args.trace_dir,
                    keep_workspace=args.keep_workspace,
                )
            except Exception as exc:  # 拉镜像/磁盘等环境问题：记下来继续下一题
                record = {
                    "instance_id": instance_id,
                    "model_name_or_path": f"dm-agent-{args.provider}",
                    "model_patch": "",
                    "dm_status": "harness_error",
                    "dm_failure": f"{type(exc).__name__}: {exc}",
                }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            written += 1
            print(
                f"    status={record['dm_status']} patch={record.get('dm_patch_chars', 0)}B "
                f"steps={record.get('dm_steps', 0)} {record.get('dm_duration_seconds', 0)}s",
                flush=True,
            )

    print(f"\nwrote {written} predictions -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
