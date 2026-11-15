"""Own a child process tree independently of the lifetime of its root process."""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess
import sys
import threading
from ctypes import wintypes
from typing import Any

if sys.platform == "win32":

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IOCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_uint64)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IOCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _WindowsJob:
        """A non-inheritable, kill-on-close Windows Job Object."""

        def __init__(self) -> None:
            self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self._kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            self._kernel.CreateJobObjectW.restype = wintypes.HANDLE
            self._kernel.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            self._kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            self._kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self._handle = self._kernel.CreateJobObjectW(None, None)
            if not self._handle:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self._kernel.SetInformationJobObject(
                self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                error = ctypes.WinError(ctypes.get_last_error())
                self.close()
                raise error

        def assign_and_resume(self, process: subprocess.Popen[bytes]) -> None:
            # Popen closes the primary thread handle. NtResumeProcess resumes the suspended
            # process using its still-owned process handle after assignment, eliminating the
            # race where it creates children before it belongs to the job.
            handle = vars(process)["_handle"]
            if not self._kernel.AssignProcessToJobObject(self._handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
            resume = ctypes.WinDLL("ntdll").NtResumeProcess
            resume.argtypes = [wintypes.HANDLE]
            resume.restype = wintypes.LONG
            if resume(handle) != 0:
                raise OSError("Unable to resume the child process assigned to its Windows job.")

        def close(self) -> None:
            if self._handle:
                self._kernel.CloseHandle(self._handle)
                self._handle = None


class ProcessTree:
    """Launch, stop, and reap a tree. Call ``close`` even after its root exits.

    POSIX descendants remain in a dedicated process group. Windows descendants inherit
    job membership; closing the job also handles a root that has already exited. A
    failed job assignment is a launch failure, never a silently uncontained process.
    """

    def __init__(self, command: list[str] | str, **kwargs: Any) -> None:
        self._lock = threading.Lock()
        self._closed = False
        self._job: Any = None
        if sys.platform == "win32":
            self._job = _WindowsJob()
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004  # CREATE_SUSPENDED
            )
        else:
            kwargs["start_new_session"] = True
        try:
            self.process: subprocess.Popen[bytes] = subprocess.Popen(command, **kwargs)
            if self._job is not None:
                try:
                    self._job.assign_and_resume(self.process)
                except BaseException:
                    self.process.kill()
                    self.process.wait(timeout=5)
                    raise
        except BaseException:
            if self._job is not None:
                self._job.close()
            raise

    def stop(self, *, grace_seconds: float = 0.0) -> bool:
        """Terminate all owned descendants, including those whose root has exited."""
        with self._lock:
            if self._closed:
                return False
            if self.process.poll() is None and grace_seconds > 0:
                with contextlib.suppress(OSError, ValueError):
                    if sys.platform == "win32":
                        self.process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        os.killpg(self.process.pid, signal.SIGTERM)
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self.process.wait(timeout=grace_seconds)
            self._closed = True
            if sys.platform == "win32":
                if self._job is not None:
                    self._job.close()
            else:
                # The group id is the original child's pid, even after that child exits.
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=5)
            return True

    def close(self) -> None:
        self.stop()
