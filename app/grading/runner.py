"""Isolated execution runner.

Runs a compiled binary in a dedicated workspace with:

* a wall-clock timeout enforced by killing the whole process group,
* a CPU-time limit via ``RLIMIT_CPU`` (best effort),
* a hard cap on captured output size.

These measures reduce ordinary risks (hangs, runaway output). They are **not**
a complete security boundary against deliberately malicious code - that is a
hosted-deployment concern (see ``docs/PLAN.md``).

Platform notes (Android / Termux, verified by experiment):

* ``RLIMIT_AS`` is **not** applied there. The bionic dynamic linker maps shadow
  memory at process start and aborts with
  ``linker_cfi.cpp: MapShadow CHECK 'p != MAP_FAILED' failed`` whenever an
  address-space cap is in force. The failure is intermittent at every value,
  so the limit is skipped rather than tuned.
* ``RLIMIT_NPROC`` is **not** applied there either: setting it in the child
  makes signal deaths report as ``exit code 1`` instead of a negative signal
  number, which would silently turn crashes into wrong answers.

Both limits remain in force on platforms that support them correctly.
"""

from __future__ import annotations

import os
import platform
import resource
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


def _is_android() -> bool:
    """Return True when running under Android's bionic libc (e.g. Termux)."""
    return sys.platform == "android" or "android" in platform.platform().lower()


@dataclass(frozen=True)
class RunOutcome:
    """Raw outcome of executing a binary once."""

    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    timed_out: bool
    output_limit_exceeded: bool
    spawn_error: str = ""

    @property
    def killed_by_signal(self) -> bool:
        """True when the process died from a signal (segfault, abort, ...)."""
        return self.exit_code is not None and self.exit_code < 0

    @property
    def signal_number(self) -> int | None:
        """The terminating signal number, if any."""
        return -self.exit_code if self.killed_by_signal else None


class RunnerError(RuntimeError):
    """Raised when the runner cannot execute the binary at all."""


def run_binary(
    binary_path: Path,
    *,
    stdin_text: str = "",
    workspace: Path,
    timeout_ms: int = 3000,
    max_output_bytes: int = 65536,
    memory_limit_mb: int | None = 128,
) -> RunOutcome:
    """Execute ``binary_path`` with the given stdin and resource limits."""
    if not binary_path.exists():
        raise RunnerError(f"binary not found: {binary_path}")

    cpu_seconds = max(1, int(timeout_ms / 1000))
    preexec = _build_preexec(memory_limit_mb=memory_limit_mb, cpu_seconds=cpu_seconds)

    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [str(binary_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(workspace),
            shell=False,
            preexec_fn=preexec,
            # Own process group so a timeout can kill descendants too.
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise RunnerError(f"could not execute binary: {exc}") from exc
    except OSError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunOutcome(
            stdout="",
            stderr="",
            exit_code=None,
            duration_ms=duration_ms,
            timed_out=False,
            output_limit_exceeded=False,
            spawn_error=str(exc),
        )

    timeout_seconds = timeout_ms / 1000
    timed_out = False

    try:
        stdout_raw, stderr_raw = process.communicate(
            input=stdin_text.encode("utf-8") if stdin_text else None,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_group(process)
        stdout_raw, stderr_raw = process.communicate()

    duration_ms = int((time.monotonic() - started) * 1000)

    stdout_raw = stdout_raw or b""
    stderr_raw = stderr_raw or b""
    limit_exceeded = len(stdout_raw) > max_output_bytes or len(stderr_raw) > max_output_bytes

    return RunOutcome(
        stdout=_decode(stdout_raw, max_output_bytes),
        stderr=_decode(stderr_raw, max_output_bytes),
        exit_code=None if timed_out else process.returncode,
        duration_ms=duration_ms,
        timed_out=timed_out,
        output_limit_exceeded=limit_exceeded,
    )


def _kill_process_group(process: subprocess.Popen) -> None:
    """Terminate the child's whole process group, falling back to the child."""
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def _build_preexec(memory_limit_mb: int | None, cpu_seconds: int):
    """Build a ``preexec_fn`` applying best-effort resource limits.

    Each limit is attempted independently; a limit the platform does not
    support must never prevent execution. See the module docstring for why
    ``RLIMIT_AS`` and ``RLIMIT_NPROC`` are skipped on Android.
    """
    android = _is_android()
    apply_memory_limit = memory_limit_mb if (memory_limit_mb and not android) else None
    apply_process_limit = not android

    def _apply() -> None:  # pragma: no cover - runs in the child process
        if cpu_seconds > 0:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            except (ValueError, OSError):
                pass
        if apply_memory_limit:
            limit = apply_memory_limit * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            except (ValueError, OSError):
                pass
        if apply_process_limit:
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except (ValueError, OSError):
                pass

    return _apply


def _decode(raw: bytes | None, max_bytes: int) -> str:
    """Decode captured bytes, truncating beyond ``max_bytes``."""
    if not raw:
        return ""
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += "\n... (output truncated)"
    return text
