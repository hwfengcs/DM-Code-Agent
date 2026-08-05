"""预测阶段：在真实仓库工作区里跑 ReactAgent，产出 SWE-bench 格式的 predictions.jsonl。

与评测阶段严格分离——这正是 SWE-bench 官方的标准流程，也是"数字可比"的前提：
我们只负责产出 patch，判定 resolved 的永远是官方 harness。

工作区不从 GitHub clone，而是从官方评测镜像里 ``docker cp`` 出 ``/testbed``：
镜像里的仓库已停在 ``base_commit``，与评测时的环境逐字一致，既省掉几百 MB 的
clone 流量，也排除了"预测环境 != 评测环境"这一类假阳性/假阴性。

本模块只用标准库 + 主项目已有的依赖，subprocess 调 docker CLI，
主项目因此不需要 docker SDK。
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from dm_agent.clients.llm_factory import PROVIDER_DEFAULTS, create_llm_client
from dm_agent.core import ReactAgent
from dm_agent.evals.real_runner import PROVIDER_API_KEY_ENV, UsageTrackingClient
from dm_agent.paths import load_env_files
from dm_agent.tools import default_tools
from dm_agent.tracing import TraceWriter

from .dataset import image_name

# 喂给 agent 的题面。SWE-bench 的约定是 agent 只看 problem_statement，
# 看不到 test_patch，也不知道 FAIL_TO_PASS 具体是哪些用例。
PROMPT_TEMPLATE = """\
You are working inside a checkout of the `{repo}` repository at commit {base_commit}.

Resolve the following issue by editing the repository's source code:

--- ISSUE ---
{problem_statement}
--- END ISSUE ---

Rules:
- Work only inside the current working directory. Do not read, list or execute
  anything outside it, and always use relative paths.
- Edit only the library's source files. Do NOT add, edit or delete any test files;
  the graders run their own tests against your change.
- Make the smallest change that actually fixes the issue described above.
- Do not revert or reformat unrelated code.
- Budget your steps: locate the relevant source file first, then edit it. When the
  fix is in place, call finish -- do not keep exploring.
"""


@contextmanager
def chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs
    )


def ensure_image(instance_id: str, *, quiet: bool = False, attempts: int = 3) -> str:
    """镜像不在本地就拉一次；返回镜像名。

    每个镜像约 3.9 GB，实测拉到一半被 registry 断开是常态
    （``httpReadSeeker: failed open``）。docker 自己会复用已下载的层，所以重试很便宜。
    """
    image = image_name(instance_id)
    exists = _run(["docker", "image", "inspect", image])
    if exists.returncode == 0:
        return image

    last_error = ""
    for attempt in range(1, attempts + 1):
        if not quiet:
            suffix = f" (retry {attempt - 1})" if attempt > 1 else ""
            print(f"    pulling {image}{suffix} ...", flush=True)
        pulled = _run(["docker", "pull", image])
        if pulled.returncode == 0:
            return image
        last_error = pulled.stderr.strip()[:300]
        if attempt < attempts:
            time.sleep(5 * attempt)
    raise RuntimeError(f"拉取镜像失败 {image}（{attempts} 次尝试）: {last_error}")


def _force_rmtree(path: Path) -> None:
    """删掉整棵目录，包括 git 在 Windows 上标成只读的对象文件。

    ``shutil.rmtree(..., ignore_errors=True)`` 在这里是个陷阱：.git/objects 下的
    文件是只读的，删除失败会被静默吞掉，留下一个**残缺的 .git**。之后 git 命令在
    该目录里找不到有效仓库就会一路向上查找，最终作用到本项目自己的仓库上。
    """

    def _clear_readonly(func: Any, target: str, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly)
    else:
        shutil.rmtree(path, onerror=_clear_readonly)


def materialize_workspace(instance_id: str, destination: Path) -> Path:
    """把镜像里的 /testbed 取出来当工作区（含 .git，后面要靠它出 diff）。"""
    image = ensure_image(instance_id)
    _force_rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    container = f"dmagent-prep-{instance_id.replace('__', '-')}"
    _run(["docker", "rm", "-f", container])
    created = _run(["docker", "create", "--name", container, image, "true"])
    if created.returncode != 0:
        raise RuntimeError(f"创建容器失败 {instance_id}: {created.stderr.strip()[:300]}")
    try:
        copied = _run(["docker", "cp", f"{container}:/testbed", str(destination)])
        if copied.returncode != 0:
            raise RuntimeError(f"复制 /testbed 失败 {instance_id}: {copied.stderr.strip()[:300]}")
    finally:
        _run(["docker", "rm", "-f", container])

    # docker cp 在目标已存在时会把源**作为子目录**放进去。上面已强制清过目录，
    # 这里再确认一次：嵌套出 <dest>/testbed 就说明清理没生效，必须早失败。
    if (destination / "testbed").is_dir() and not (destination / ".git").is_dir():
        raise RuntimeError(f"工作区嵌套异常 {instance_id}：{destination / 'testbed'}")
    _assert_git_root(destination, instance_id)
    _neutralize_windows_git_noise(destination)
    return destination


def _assert_git_root(workspace: Path, instance_id: str) -> None:
    """确认工作区自己就是 git 仓库根。

    这是一道安全闸：只要它不成立，后续的 ``git add -A`` 就会作用到父目录的仓库上
    （实测踩过——差点把本项目的改动 staged 进去）。
    """
    if not (workspace / ".git").is_dir():
        raise RuntimeError(f"工作区缺少 .git，拒绝在此执行 git 命令：{workspace} ({instance_id})")
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd=str(workspace))
    resolved = Path(top.stdout.strip()).resolve() if top.returncode == 0 else None
    if resolved != workspace.resolve():
        raise RuntimeError(
            f"工作区不是 git 仓库根（实际根：{resolved}），拒绝执行 git 命令：{workspace}"
        )


def _neutralize_windows_git_noise(workspace: Path) -> None:
    """关掉两个会把 Windows 平台差异写进 patch 的 git 行为。

    镜像里的 /testbed 是在 Linux 上构建的，``docker cp`` 到 Windows 后：

    - **执行位丢失**：15 个文件从 100755 变成 100644（astropy 的实测数字），
      于是一个还没被 agent 碰过的工作区，``git diff`` 就已经非空。
    - **行尾翻转**：全局 ``core.autocrlf=true`` 会在 git 下次触碰文件时把 LF 换成
      CRLF，agent 改一行就可能产出整文件级别的 diff。

    两者都会让 patch 里混进与题目无关的噪声，官方 harness 上 ``git apply`` 会失败
    或引入无关改动。仓库级配置只影响这个一次性工作区，不动用户的全局 git 设置。
    """
    for key, value in (("core.fileMode", "false"), ("core.autocrlf", "false")):
        _run(["git", "config", key, value], cwd=str(workspace))
    # autocrlf 是在配置生效后才重新判定的，把索引刷新一遍，抹掉 copy 阶段留下的假改动。
    _run(["git", "checkout", "--", "."], cwd=str(workspace))


def extract_patch(workspace: Path) -> str:
    """工作区相对 base_commit 的改动。

    先 ``git add -A`` 再取 ``--cached``，这样 agent 新建的源文件也进 patch；
    ``__pycache__`` 之类的产物由仓库自带的 .gitignore 挡掉。

    调用前必须过 :func:`_assert_git_root`——``git add -A`` 在错误的目录里执行会
    污染父仓库的索引。
    """
    _assert_git_root(workspace, workspace.name)
    staged = _run(["git", "add", "-A"], cwd=str(workspace))
    if staged.returncode != 0:
        raise RuntimeError(f"git add 失败：{staged.stderr.strip()[:300]}")
    diff = _run(["git", "diff", "--cached"], cwd=str(workspace))
    if diff.returncode != 0:
        raise RuntimeError(f"git diff 失败：{diff.stderr.strip()[:300]}")
    return diff.stdout


def reset_workspace(workspace: Path) -> None:
    _run(["git", "checkout", "--", "."], cwd=str(workspace))


def build_client(provider: str, model: str | None, timeout: int) -> UsageTrackingClient:
    load_env_files()
    key_env = PROVIDER_API_KEY_ENV.get(provider)
    api_key = os.environ.get(key_env or "", "")
    if not api_key:
        raise RuntimeError(f"环境变量 {key_env} 未设置；预测阶段需要真实 API key。")
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    client = create_llm_client(
        provider=provider,
        api_key=api_key,
        model=model or defaults.get("model"),
        base_url=defaults.get("base_url"),
        timeout=timeout,
    )
    return UsageTrackingClient(client)


def predict_one(
    instance: dict[str, Any],
    *,
    workspace_root: Path,
    provider: str,
    model: str | None,
    max_steps: int,
    temperature: float,
    timeout: int,
    trace_dir: Path | None,
    keep_workspace: bool,
) -> dict[str, Any]:
    """跑完一道题，返回一条预测记录（含足够的诊断字段）。"""
    instance_id = instance["instance_id"]
    workspace = workspace_root / instance_id
    started = time.perf_counter()

    materialize_workspace(instance_id, workspace)

    trace_writer = None
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_writer = TraceWriter(trace_dir / f"{instance_id}.jsonl")
        trace_writer.record(
            "runtime",
            {
                "mode": "swebench_verified",
                "instance_id": instance_id,
                "repo": instance["repo"],
                "base_commit": instance["base_commit"],
                "provider": provider,
                "model": model or PROVIDER_DEFAULTS.get(provider, {}).get("model"),
            },
        )

    client = build_client(provider, model, timeout)
    agent = ReactAgent(
        client,
        default_tools(include_mcp=False),
        max_steps=max_steps,
        temperature=temperature,
        trace_writer=trace_writer,
    )
    prompt = PROMPT_TEMPLATE.format(
        repo=instance["repo"],
        base_commit=instance["base_commit"],
        problem_statement=instance["problem_statement"],
    )

    status = "ok"
    failure = ""
    metadata: dict[str, Any] = {}
    step_count = 0
    with chdir(workspace):
        try:
            with redirect_stdout(StringIO()):
                result = agent.run(prompt)
            metadata = dict(result.get("metadata", {}))
            status = str(metadata.get("status", "unknown"))
            step_count = len(result.get("steps", []))
        except Exception as exc:  # 单题崩溃不该让整批预测终止
            status = "agent_exception"
            failure = f"{type(exc).__name__}: {exc}"

    patch = extract_patch(workspace)
    record = {
        "instance_id": instance_id,
        "model_name_or_path": f"dm-agent-{provider}",
        "model_patch": patch,
        # 下面是诊断字段，官方 harness 会忽略，但我们自己要看
        "dm_status": status,
        "dm_failure": failure,
        "dm_steps": step_count,
        "dm_replans": metadata.get("replan_count", 0),
        "dm_parse_repairs": metadata.get("parse_repair_count", 0),
        "dm_truncations": metadata.get("truncation_count", 0),
        "dm_patch_chars": len(patch),
        "dm_duration_seconds": round(time.perf_counter() - started, 2),
        "dm_difficulty": instance.get("difficulty", ""),
    }

    if not keep_workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    return record
