"""评测阶段：把 predictions.jsonl 交给**官方** SWE-bench harness。

这一层刻意做得很薄——判定 resolved 的必须是官方代码，我们一行判分逻辑都不写，
否则拿到的数字与公开 leaderboard 不可比，等于白跑。

本脚本跑在 .swebench-venv 里（那里装了 swebench 4.1.0），且需要
``PYTHONPATH=swebench/_winshim`` 以在 Windows 上补上 Unix-only 的 resource 模块。
README.md 有可直接复制的命令。
"""

from __future__ import annotations

import argparse
import builtins
import json
import os
import sys
from pathlib import Path


def force_lf_writes() -> None:
    """让 Windows harness 的文本产物统一使用 UTF-8，shell 脚本使用 LF。

    ``run_evaluation.py:199`` 用 ``eval_file.write_text(test_spec.eval_script)``
    生成 ``/eval.sh``，再 copy 进 Linux 容器执行。``write_text`` 默认的
    ``newline=None`` 在 Windows 上会把 ``\\n`` 写成 ``\\r\\n``，于是容器里的 bash 把
    ``\\r`` 当成命令的一部分：

        + cd $'/testbed\\r'
        /eval.sh: line 7: cd: $'/testbed\\r': No such file or directory
        + git $'status\\r'
        git: 'status' is not a git command.

    **每一条命令都失败，测试一个都没跑**，而报告里表现为 PASS_TO_PASS 全 0——
    看着像 agent 把整个模块改坏了。实测 10 题全中，resolved 0/10 完全是这个 bug 的
    产物，不是能力信号。

    官方 harness 还用未指定 encoding 的 ``open(test_output_path, "w")`` 写容器测试输出。
    Windows 中文区域设置会默认使用 GBK，输出里出现 ``ë`` 或孟加拉数字等字符时，测试已经
    跑完却会在落盘阶段抛 ``UnicodeEncodeError``，最终被误记为 harness error。
    当前官方 harness 使用线程池，因此进程内 monkeypatch 会覆盖 worker；仍在入口设置
    ``PYTHONUTF8=1``，为 harness 未来改回子进程或其依赖启动 Python 子进程时提供一致环境。

    这与主项目 ``tools/file_tools.py`` 修的是同一类宿主平台 I/O 缺陷，只是发生在上游包里，
    所以在评测进程内就地修补。该进程只运行 harness，全局改写文本写入默认值的影响面可控。
    """
    original_write_text = Path.write_text
    original_open = builtins.open
    os.environ["PYTHONUTF8"] = "1"

    def write_text(  # type: ignore[no-untyped-def]
        self, data, encoding=None, errors=None, newline=None
    ):
        if isinstance(data, str):
            data = data.replace("\r\n", "\n")
        if encoding is None:
            encoding = "utf-8"
        return original_write_text(self, data, encoding=encoding, errors=errors, newline="")

    def open_utf8(  # type: ignore[no-untyped-def]
        file,
        mode="r",
        buffering=-1,
        encoding=None,
        errors=None,
        newline=None,
        closefd=True,
        opener=None,
    ):
        if encoding is None and "b" not in mode:
            encoding = "utf-8"
        return original_open(
            file,
            mode,
            buffering,
            encoding,
            errors,
            newline,
            closefd,
            opener,
        )

    Path.write_text = write_text  # type: ignore[method-assign]
    builtins.open = open_utf8


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

    force_lf_writes()

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
