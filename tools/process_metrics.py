"""Windows single-process wall time and native peak working set measurement."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]


def peak_working_set(process: subprocess.Popen) -> int:
    if os.name != "nt":
        raise RuntimeError("Native peak working set collection requires Windows CPython.")
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    # CPython keeps its process handle alive while this Popen object is retained.
    handle = int(process._handle)
    if not query(handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    if counters.PeakWorkingSetSize <= 0:
        raise RuntimeError("The OS did not return a nonzero process peak working set.")
    return int(counters.PeakWorkingSetSize)


def measure_process(command: list[str], cwd: Path, stdout: Path, stderr: Path,
                    timeout: float = 120, env: dict | None = None) -> dict:
    timed_out = False
    command = list(command)
    environment = dict(os.environ if env is None else env)
    bypassed = False
    base = getattr(sys, "_base_executable", sys.executable)
    if (os.name == "nt" and Path(command[0]).resolve() == Path(sys.executable).resolve()
            and Path(base).resolve() != Path(sys.executable).resolve()):
        command[0] = base
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        bypassed = True
    with stdout.open("w", encoding="utf-8") as out, stderr.open("w", encoding="utf-8") as err:
        started = time.perf_counter_ns()
        process = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=err, env=environment)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            returncode = process.wait()
        stopped = time.perf_counter_ns()
        try:
            peak = peak_working_set(process)
            memory_error = None
        except (OSError, RuntimeError, AttributeError) as error:
            peak = None
            memory_error = type(error).__name__ + ": " + str(error)
    return {"wall_seconds": (stopped - started) / 1e9, "peak_working_set_bytes": peak,
            "returncode": returncode, "timed_out": timed_out, "memory_error": memory_error,
            "pid": process.pid, "python_redirector_bypassed": bypassed}
