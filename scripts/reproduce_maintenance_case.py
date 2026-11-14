"""Reproduce the archived repair in a new Git worktree, without calling a model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "docs" / "case-studies" / "failure-classification"
BASE_COMMIT = "bd35d253abb18cabdaedf1caa1d5dd91cd985f59"


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def check(workspace: Path, output: Path, name: str, test_path: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", test_path]
    result = subprocess.run(
        command,
        cwd=workspace,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        timeout=180,
    )
    log = output / f"{name}.txt"
    log.write_bytes(result.stdout + result.stderr)
    return {"returncode": result.returncode, "log": log.name, "test_path": test_path}


def reproduce(output: Path, *, full_suite: bool = False) -> dict[str, Any]:
    if output.is_symlink() or output.exists():
        raise ValueError(
            "Choose a new output directory; original worktrees and evidence are preserved."
        )
    output = output.resolve()
    regression = (ARTIFACTS / "regression_test.py.txt").read_bytes()
    patch = ARTIFACTS / "agent.patch"
    # 检查 Git 对象与输入之后才创建新目录，不修改当前 checkout。
    git("cat-file", "-e", f"{BASE_COMMIT}^{{commit}}")
    output.mkdir(parents=True)
    workspace = output / "workspace"
    git("worktree", "add", "--detach", str(workspace), BASE_COMMIT)
    (workspace / "tests" / "test_maintenance_case.py").write_bytes(regression)
    results = {
        "base_commit": BASE_COMMIT,
        "model_requests": 0,
        "applied_patch": "archived live-model output; not a new agent run",
        "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
        "regression_sha256": hashlib.sha256(regression).hexdigest(),
        "before": check(workspace, output, "before", "tests/test_maintenance_case.py"),
    }
    if full_suite:
        results["before_full_suite"] = check(workspace, output, "before-full-suite", "tests")
    git("-C", str(workspace), "apply", "--check", str(patch))
    git("-C", str(workspace), "apply", str(patch))
    results["after"] = check(workspace, output, "after", "tests/test_maintenance_case.py")
    if full_suite:
        results["after_full_suite"] = check(workspace, output, "after-full-suite", "tests")
    with (output / "reproduction.json").open("x", encoding="utf-8") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for worktree and logs"
    )
    parser.add_argument(
        "--full-suite", action="store_true", help="Also run the historical suite before/after"
    )
    args = parser.parse_args()
    results = reproduce(args.output, full_suite=args.full_suite)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    # 退出码表示是否复现已归档的局部测试结果，不声明补丁可合并或整个 suite 通过。
    return 0 if results["before"]["returncode"] == 1 and results["after"]["returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
