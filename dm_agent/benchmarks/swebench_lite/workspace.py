"""Per-instance git workspace management for SWE-bench Lite.

A :class:`SWEBenchWorkspace` is a disposable directory that contains a checkout
of the target repository at the instance's ``base_commit`` plus the instance's
``test_patch`` applied. The agent edits files inside it; the verifier then
extracts the agent's diff via ``git diff`` and applies+tests it.

We deliberately do not use GitPython. Plain ``subprocess`` keeps the dependency
surface tiny and matches how the rest of the project shells out to git.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .models import SWEBenchInstance

GIT_TIMEOUT_SECONDS = 600
GIT_AUTHOR_ENV = {
    "GIT_AUTHOR_NAME": "DM-Code-Agent",
    "GIT_AUTHOR_EMAIL": "dm-agent@example.invalid",
    "GIT_COMMITTER_NAME": "DM-Code-Agent",
    "GIT_COMMITTER_EMAIL": "dm-agent@example.invalid",
    "GIT_TERMINAL_PROMPT": "0",
}


class WorkspaceError(RuntimeError):
    """Raised when workspace setup or teardown fails."""


@dataclass
class GitCommandResult:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str


def _run_git(
    args: List[str],
    cwd: Path,
    *,
    timeout: int = GIT_TIMEOUT_SECONDS,
    check: bool = True,
    input_text: Optional[str] = None,
) -> GitCommandResult:
    env = os.environ.copy()
    env.update(GIT_AUTHOR_ENV)
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
    )
    result = GitCommandResult(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and completed.returncode != 0:
        raise WorkspaceError(
            f"git {' '.join(args)} failed (exit={completed.returncode}):\n"
            f"stdout: {completed.stdout[-500:]}\n"
            f"stderr: {completed.stderr[-500:]}"
        )
    return result


class SWEBenchWorkspace:
    """A short-lived git workspace for one SWE-bench Lite instance.

    Use as a context manager so that the temporary directory is cleaned up::

        with SWEBenchWorkspace(instance, root_dir=root) as ws:
            ws.setup()
            ...
            prediction = ws.compute_prediction_diff()

    Notes:
        - We use ``git clone --filter=blob:none`` plus ``--no-checkout`` to keep
          clone size manageable on large repositories like ``django/django``.
        - The ``base_commit`` is fetched explicitly because the default branch
          may have moved past it.
        - ``test_patch`` is applied via ``git apply`` so that the agent's later
          changes can be diffed against ``base_commit`` cleanly.
        - The repository cache directory holds a single bare clone per repo;
          per-instance workspaces are cheap copies.
    """

    def __init__(
        self,
        instance: SWEBenchInstance,
        *,
        root_dir: str | Path,
        cache_root: Optional[str | Path] = None,
    ) -> None:
        self.instance = instance
        self.root_dir = Path(root_dir)
        self.cache_root = Path(cache_root) if cache_root else self._default_cache_root()
        self._workspace_path: Optional[Path] = None
        self._cleanup = False

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _default_cache_root() -> Path:
        env = os.environ.get("DM_AGENT_CACHE_DIR")
        if env:
            return Path(env) / "swebench_lite" / "repos"
        return Path.home() / ".cache" / "dm-agent" / "swebench_lite" / "repos"

    def _safe_repo_dir_name(self) -> str:
        return self.instance.repo.replace("/", "__")

    @property
    def path(self) -> Path:
        if self._workspace_path is None:
            raise WorkspaceError("Workspace not yet set up. Call setup() first.")
        return self._workspace_path

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.instance.repo}.git"

    @property
    def cached_repo_dir(self) -> Path:
        return self.cache_root / self._safe_repo_dir_name()

    # ------------------------------------------------------------------ context manager

    def __enter__(self) -> "SWEBenchWorkspace":
        return self

    def __exit__(self, *exc) -> None:
        if self._cleanup and self._workspace_path is not None:
            shutil.rmtree(self._workspace_path, ignore_errors=True)
            self._workspace_path = None

    # ------------------------------------------------------------------ setup

    def ensure_repo_cache(self) -> Path:
        """Ensure a bare git cache exists for the instance's repository.

        Subsequent instances of the same repo reuse this cache, avoiding a
        full re-clone per task.

        Note: we deliberately use a *full* bare clone (no ``--filter=blob:none``)
        because partial clones force later instance clones into lazy-fetch mode
        through a "promisor remote", which fails when the workspace clone is
        offline or when the partial cache lacks specific blobs. A full clone
        costs more disk space the first time (a few hundred MB per repo) but
        produces an offline-friendly self-contained cache.
        """
        self.cache_root.mkdir(parents=True, exist_ok=True)
        repo_dir = self.cached_repo_dir
        if repo_dir.exists():
            # Update only if we are missing the commit we need.
            try:
                self._fetch_commit_into_cache(repo_dir, self.instance.base_commit)
            except WorkspaceError:
                pass
            return repo_dir
        _run_git(
            ["clone", "--bare", self.repo_url, str(repo_dir)],
            cwd=self.cache_root,
        )
        return repo_dir

    @staticmethod
    def _fetch_commit_into_cache(cache_dir: Path, commit: str) -> None:
        # cheap probe; if cat-file succeeds the commit is already cached
        result = _run_git(
            ["cat-file", "-e", commit],
            cwd=cache_dir,
            check=False,
        )
        if result.returncode == 0:
            return
        _run_git(
            ["fetch", "origin", commit],
            cwd=cache_dir,
        )

    def setup(self) -> Path:
        """Create the working directory and prepare it at base_commit + test_patch."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        workspace_path = Path(
            tempfile.mkdtemp(prefix=f"{self.instance.instance_id}__", dir=str(self.root_dir))
        )
        self._workspace_path = workspace_path

        cache = self.ensure_repo_cache()
        # Default `git clone <local-cache>` uses --local, which hard-links the
        # objects directory. This is fast and offline-safe. We avoid --no-local
        # because it forces network protocol semantics and breaks for caches
        # that originated as partial clones.
        _run_git(
            ["clone", str(cache), str(workspace_path)],
            cwd=self.root_dir,
        )
        _run_git(["checkout", self.instance.base_commit], cwd=workspace_path)
        # Drop the upstream remote so the agent cannot inadvertently push.
        _run_git(["remote", "remove", "origin"], cwd=workspace_path, check=False)

        # Mark the pristine state for later diffing.
        _run_git(
            ["commit", "--allow-empty", "-m", "dm-agent: base"],
            cwd=workspace_path,
            check=False,
        )

        if self.instance.test_patch.strip():
            self.apply_patch(self.instance.test_patch, label="test_patch")
            _run_git(["add", "-A"], cwd=workspace_path)
            _run_git(
                ["commit", "-m", "dm-agent: apply test_patch", "--allow-empty"],
                cwd=workspace_path,
                check=False,
            )

        self._cleanup = True
        return workspace_path

    # ------------------------------------------------------------------ patch I/O

    def apply_patch(self, patch_text: str, *, label: str = "patch") -> None:
        """Apply a unified diff to the workspace via ``git apply``."""
        if not patch_text.endswith("\n"):
            patch_text = patch_text + "\n"
        result = _run_git(
            ["apply", "--whitespace=nowarn", "-"],
            cwd=self.path,
            input_text=patch_text,
            check=False,
        )
        if result.returncode != 0:
            # Try a more forgiving apply: 3-way merge, then reject hunks that miss.
            fallback = _run_git(
                ["apply", "--3way", "--whitespace=nowarn", "-"],
                cwd=self.path,
                input_text=patch_text,
                check=False,
            )
            if fallback.returncode != 0:
                raise WorkspaceError(textwrap.dedent(f"""
                        Failed to apply {label}.
                        First attempt stderr: {result.stderr[-400:]}
                        3-way attempt stderr: {fallback.stderr[-400:]}
                        """).strip())

    def compute_prediction_diff(self) -> str:
        """Return the patch the agent introduced on top of the test_patch commit.

        We diff against ``HEAD`` (= the commit holding test_patch). Untracked
        files are added via ``git add -N`` so they appear in the diff as new
        files. Empty diffs return an empty string.
        """
        _run_git(["add", "-N", "."], cwd=self.path, check=False)
        result = _run_git(
            ["diff", "--no-color", "--patch", "HEAD"],
            cwd=self.path,
        )
        return result.stdout

    # ------------------------------------------------------------------ teardown

    def discard(self) -> None:
        """Forget the workspace so __exit__ does not attempt cleanup."""
        self._cleanup = False
