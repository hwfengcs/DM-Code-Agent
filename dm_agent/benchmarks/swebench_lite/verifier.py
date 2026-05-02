"""Verifier for SWE-bench Lite predictions.

Given an instance and a unified diff produced by an agent, the verifier:

  1. Resets the workspace to a clean state at ``base_commit + test_patch``.
  2. Applies the agent's prediction with ``git apply``.
  3. Runs the FAIL_TO_PASS and PASS_TO_PASS test node IDs with ``pytest``.
  4. Reports SWE-bench-style ``resolved`` status.

This is the *Tier-1* verifier: it runs everything in the host Python
environment. It will fail for instances that need a specific Python version,
heavyweight system dependencies, or repository-specific test runners. Those
cases are reserved for the optional ``use_docker=True`` Tier-2 verifier (TODO,
tracked in docs/research-log/01-swebench-baseline.md).

Tests are intentionally invoked one node at a time so that we can credit
partial passes: an instance that flips 3-of-5 FAIL_TO_PASS still produces
useful telemetry, even though the official ``resolved`` flag requires all-or-nothing.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .models import SWEBenchInstance, SWEBenchVerification
from .workspace import SWEBenchWorkspace, WorkspaceError, _run_git


@dataclass
class TestRunOutcome:
    node_id: str
    passed: bool
    returncode: int
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str


def _python_executable() -> str:
    """Return the Python interpreter the verifier should drive pytest with."""
    return sys.executable or "python"


def _run_pytest_node(
    node_id: str,
    cwd: Path,
    *,
    timeout: int,
) -> TestRunOutcome:
    cmd = [_python_executable(), "-m", "pytest", "-q", "--no-header", "--tb=short", node_id]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - started
        return TestRunOutcome(
            node_id=node_id,
            passed=completed.returncode == 0,
            returncode=completed.returncode,
            duration_seconds=elapsed,
            stdout_tail=completed.stdout[-1500:],
            stderr_tail=completed.stderr[-500:],
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        return TestRunOutcome(
            node_id=node_id,
            passed=False,
            returncode=-1,
            duration_seconds=elapsed,
            stdout_tail=(exc.stdout or "")[-1500:] if isinstance(exc.stdout, str) else "",
            stderr_tail=f"TIMEOUT after {timeout}s while running {shlex.join(cmd)}",
        )


def _run_pytest_nodes(
    node_ids: Sequence[str],
    cwd: Path,
    *,
    timeout: int,
) -> List[TestRunOutcome]:
    return [_run_pytest_node(node, cwd, timeout=timeout) for node in node_ids]


def _reset_workspace_to_post_test_patch(workspace: SWEBenchWorkspace) -> None:
    """Hard-reset the workspace tree back to the test_patch commit (= HEAD).

    The agent may have left dirty files; we drop them, then ensure no untracked
    files remain.
    """
    _run_git(["reset", "--hard", "HEAD"], cwd=workspace.path, check=False)
    _run_git(["clean", "-fdx"], cwd=workspace.path, check=False)


def verify_prediction(
    instance: SWEBenchInstance,
    workspace: SWEBenchWorkspace,
    prediction: str,
    *,
    test_timeout: int = 300,
    use_docker: bool = False,
) -> SWEBenchVerification:
    """Apply ``prediction`` and run the instance's hidden tests.

    Args:
        instance: The task instance whose hidden tests we will run.
        workspace: A *prepared* workspace at ``base_commit + test_patch`` (HEAD).
        prediction: Unified-diff text the agent produced. May be empty.
        test_timeout: Seconds allowed for each individual pytest node.
        use_docker: Reserved for Tier-2 verification. Currently raises if True.

    Returns:
        A :class:`SWEBenchVerification` with per-bucket pass counts and the
        SWE-bench-official ``resolved`` flag.
    """
    if use_docker:
        raise NotImplementedError(
            "Tier-2 docker-based verification is not yet implemented. "
            "Run with use_docker=False (the default)."
        )

    started = time.perf_counter()
    if not prediction or not prediction.strip():
        return SWEBenchVerification(
            patch_applied=False,
            fail_to_pass_pass=0,
            fail_to_pass_total=len(instance.fail_to_pass),
            pass_to_pass_pass=0,
            pass_to_pass_total=len(instance.pass_to_pass),
            stdout_tail="",
            stderr_tail="",
            duration_seconds=time.perf_counter() - started,
            error="empty_prediction",
        )

    _reset_workspace_to_post_test_patch(workspace)

    try:
        workspace.apply_patch(prediction, label="agent_prediction")
    except WorkspaceError as exc:
        return SWEBenchVerification(
            patch_applied=False,
            fail_to_pass_pass=0,
            fail_to_pass_total=len(instance.fail_to_pass),
            pass_to_pass_pass=0,
            pass_to_pass_total=len(instance.pass_to_pass),
            stdout_tail="",
            stderr_tail=str(exc)[-1500:],
            duration_seconds=time.perf_counter() - started,
            error="patch_apply_failed",
        )

    fail_to_pass_outcomes = _run_pytest_nodes(
        instance.fail_to_pass, workspace.path, timeout=test_timeout
    )
    pass_to_pass_outcomes = _run_pytest_nodes(
        instance.pass_to_pass, workspace.path, timeout=test_timeout
    )

    fail_to_pass_pass = sum(1 for o in fail_to_pass_outcomes if o.passed)
    pass_to_pass_pass = sum(1 for o in pass_to_pass_outcomes if o.passed)

    stdout_tail_chunks = []
    stderr_tail_chunks = []
    for outcome in fail_to_pass_outcomes + pass_to_pass_outcomes:
        if not outcome.passed:
            stdout_tail_chunks.append(f"# {outcome.node_id}\n{outcome.stdout_tail}")
            stderr_tail_chunks.append(f"# {outcome.node_id}\n{outcome.stderr_tail}")

    return SWEBenchVerification(
        patch_applied=True,
        fail_to_pass_pass=fail_to_pass_pass,
        fail_to_pass_total=len(instance.fail_to_pass),
        pass_to_pass_pass=pass_to_pass_pass,
        pass_to_pass_total=len(instance.pass_to_pass),
        stdout_tail="\n\n".join(stdout_tail_chunks)[-4000:],
        stderr_tail="\n\n".join(stderr_tail_chunks)[-2000:],
        duration_seconds=time.perf_counter() - started,
        error=None,
    )


def empty_verification(
    instance: SWEBenchInstance, *, error: Optional[str] = None
) -> SWEBenchVerification:
    """Build a "verification did not run" record. Used when the agent timed out
    or the workspace failed to set up."""
    return SWEBenchVerification(
        patch_applied=False,
        fail_to_pass_pass=0,
        fail_to_pass_total=len(instance.fail_to_pass),
        pass_to_pass_pass=0,
        pass_to_pass_total=len(instance.pass_to_pass),
        stdout_tail="",
        stderr_tail="",
        duration_seconds=0.0,
        error=error or "verification_skipped",
    )
