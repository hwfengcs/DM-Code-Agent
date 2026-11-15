"""Bounded command execution with retained local output and process-tree ownership."""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

from dm_agent.processes import ProcessTree


def _preview(path: Path) -> str:
    with path.open("rb") as handle:
        head = handle.read(32768)
        if path.stat().st_size > 65536:
            handle.seek(-32768, 2)
            data = (
                head
                + b"\n[output preview; full captured output in files below]\n"
                + handle.read(32768)
            )
        else:
            data = head + handle.read(32768)
    return data.decode("utf-8", errors="replace")


def execute(
    command: list[str] | str,
    arguments: dict[str, Any],
    *,
    env: dict[str, str],
    shell: bool = False,
    default_timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    timeout = arguments.get("timeout", default_timeout)
    limit = arguments.get("max_output_bytes", 8 * 1024 * 1024)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    if type(limit) is not int or limit < 1:
        raise ValueError("max_output_bytes must be a positive integer (per stream)")
    directory = Path(tempfile.gettempdir()) / "dm-agent-tool-output"
    directory.mkdir(parents=True, exist_ok=True)
    prefix = Path(tempfile.mkdtemp(prefix="exec-", dir=directory)).resolve()
    paths = [prefix / "output.stdout", prefix / "output.stderr"]
    exceeded = threading.Event()
    reader_errors: list[OSError] = []

    def drain(stream: BinaryIO, path: Path) -> None:
        size = 0
        try:
            with path.open("xb") as output:
                os.chmod(path, 0o600)
                while chunk := os.read(stream.fileno(), 8192):
                    # Keep the last read intact; overshoot is at most one chunk.
                    output.write(chunk)
                    size += len(chunk)
                    if size > limit:
                        exceeded.set()
                        break
        except OSError as exc:
            reader_errors.append(exc)
            exceeded.set()
        finally:
            stream.close()

    tree = ProcessTree(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
        env=env,
    )
    process = tree.process
    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(target=drain, args=(stream, path), daemon=True)
        for stream, path in zip((process.stdout, process.stderr), paths, strict=True)
    ]
    reason = ""
    try:
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if exceeded.wait(min(0.05, max(0, deadline - time.monotonic()))):
                reason = "output limit exceeded"
                break
            if time.monotonic() >= deadline:
                reason = f"timeout after {timeout:g} seconds"
                break
    finally:
        tree.close()
        for reader in readers:
            reader.join(timeout=5)
    if reader_errors:
        raise reader_errors[0]
    if exceeded.is_set() and not reason:
        reason = "output limit exceeded"
    stdout, stderr = (_preview(path) for path in paths)
    if reason:
        stderr += f"\nExecution failed: {reason}"
    # Paths are evidence, not full LLM I/O; no command or environment is persisted.
    if reason or any(path.stat().st_size > 65536 for path in paths):
        stderr += f"\nCaptured output: {paths[0]} ; {paths[1]}"
    return subprocess.CompletedProcess(
        command, 124 if reason else process.returncode, stdout, stderr
    )
