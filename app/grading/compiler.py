"""C compilation wrapper.

Compilation uses a **fixed, controlled** flag set. The learner can never
influence compiler flags or the compiler binary (security rule: no arbitrary
commands or flags from the browser).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.schemas.grading import CompilationResult

# Fixed flags. The compiler binary and standard come from configuration.
#
# Notes for portability:
#   - ``-pipe`` avoids temporary files (works on clang and gcc).
#   - ``-O2`` keeps runtime behaviour representative without heavy build cost.
#   - ``-Werror=implicit-function-declaration`` fails fast on the most common
#     "forgot to #include <stdio.h>" mistake without being overly strict.
#   - Sanitizers and -march=native are deliberately excluded: they are not
#     reliably available in constrained environments (e.g. Termux on Android).
_BASE_FLAGS = [
    "-O2",
    "-pipe",
    "-Wall",
    "-Wextra",
    "-Werror=implicit-function-declaration",
]

_MAX_DIAGNOSTIC_BYTES = 16_384
_COMPILE_TIMEOUT_SECONDS = 30


class CompilerError(RuntimeError):
    """Raised when the compiler itself cannot be invoked (infrastructure)."""


def compile_source(
    source_path: Path,
    output_path: Path,
    *,
    compiler: str = "gcc",
    standard: str = "c11",
    timeout_seconds: int = _COMPILE_TIMEOUT_SECONDS,
) -> CompilationResult:
    """Compile ``source_path`` into ``output_path``.

    Returns a :class:`CompilationResult`. A failed *compilation* is a normal
    result (the learner's code is at fault). A missing or unusable *compiler*
    raises :class:`CompilerError` (infrastructure fault).
    """
    command = [compiler, f"-std={standard}", *_BASE_FLAGS, str(source_path), "-o", str(output_path)]

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            # Never run through a shell; pass argv directly.
            shell=False,
        )
    except FileNotFoundError as exc:
        raise CompilerError(f"C compiler '{compiler}' not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise CompilerError(
            f"compilation timed out after {timeout_seconds}s"
        ) from exc
    except OSError as exc:
        raise CompilerError(f"could not invoke compiler: {exc}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    diagnostics = _decode_diagnostics(completed.stderr) + _decode_diagnostics(completed.stdout)

    return CompilationResult(
        success=completed.returncode == 0 and output_path.exists(),
        diagnostics=diagnostics.strip(),
        duration_ms=duration_ms,
    )


def _decode_diagnostics(raw: bytes) -> str:
    """Decode and truncate compiler diagnostics safely."""
    if not raw:
        return ""
    if len(raw) > _MAX_DIAGNOSTIC_BYTES:
        raw = raw[:_MAX_DIAGNOSTIC_BYTES] + b"\n... (diagnostics truncated)"
    return raw.decode("utf-8", errors="replace")
