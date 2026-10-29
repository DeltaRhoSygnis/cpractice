"""Truthful grading readiness probe.

A compiler on ``PATH`` is not proof that grading works. Reports green must
mean: a tiny C program compiled here *and* the produced binary actually ran
and printed the expected output. Storage mounted ``noexec`` (Termux shared
storage) or a compiler wrapper that exits non-zero both fail the probe
instead of looking healthy.

The probe is infrastructure reporting only. It never grades anything and its
result is never consulted when deciding whether a submission passed.

``app.grading.runner`` imports :mod:`resource`, which is Unix-only, so the
runner is imported lazily inside the probe function. That keeps this module
importable on native Windows, where ``cpractice doctor`` can then report why
grading is unavailable.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

#: How long a probe result stays valid, in seconds.
_CACHE_TTL_SECONDS = 60.0

#: The compiled probe binary must finish within this budget.
_RUN_TIMEOUT_MS = 2000

#: The smallest C program that proves compile *and* execute both work.
#: ``<stdio.h>`` is included explicitly: the fixed compiler flags include
#: ``-Werror=implicit-function-declaration``, so a missing include would fail
#: the compile and make every probe look broken.
_PROBE_SOURCE = """\
#include <stdio.h>

int main(void) {
    puts("ok");
    return 0;
}
"""

#: Shortest useful detail length. Details reach the client, so they are
#: truncated and never contain absolute paths or command lines.
_MAX_DETAIL_LENGTH = 200

@dataclass(frozen=True)
class GradingProbe:
    """Outcome of one compile-and-run readiness check."""

    ready: bool
    compiler: str
    standard: str
    detail: str


#: ``(compiler, standard)`` -> ``(monotonic timestamp, result)``.
_CACHE: dict[tuple[str, str], tuple[float, GradingProbe]] = {}


def probe_grading(
    *,
    compiler: str,
    standard: str,
    workdir: Path | None = None,
    timeout_ms: int = 3000,
    use_cache: bool = True,
) -> GradingProbe:
    """Compile and run a tiny program to prove grading actually works.

    ``workdir`` is where the throwaway source, binary, and run directory are
    created; when omitted a system temporary directory is used. The
    directory is always removed afterwards. ``timeout_ms`` is the compile
    budget - the probe binary itself gets a fixed 2 second run budget.

    Results are cached for 60 seconds per ``(compiler, standard)`` when
    ``use_cache`` is true. ``use_cache=False`` always performs a fresh probe.
    """
    key = (compiler, standard)
    if use_cache:
        cached = _CACHE.get(key)
        if cached is not None:
            cached_at, cached_result = cached
            if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
                return cached_result

    result = _probe_uncached(
        compiler=compiler,
        standard=standard,
        workdir=workdir,
        timeout_ms=timeout_ms,
    )

    if use_cache:
        _store(key, result)
    return result


def _probe_uncached(
    *,
    compiler: str,
    standard: str,
    workdir: Path | None,
    timeout_ms: int,
) -> GradingProbe:
    """Perform one fresh probe, cleaning up even when it fails."""
    try:
        if workdir is not None:
            Path(workdir).mkdir(parents=True, exist_ok=True)
        root = Path(
            tempfile.mkdtemp(
                prefix="cpractice-probe-",
                dir=str(workdir) if workdir is not None else None,
            )
        )
    except OSError as exc:
        return _failure(compiler, standard, f"no usable workspace: {exc}")

    try:
        return _compile_and_run(
            compiler=compiler,
            standard=standard,
            root=root,
            timeout_ms=timeout_ms,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _compile_and_run(
    *,
    compiler: str,
    standard: str,
    root: Path,
    timeout_ms: int,
) -> GradingProbe:
    """Compile the probe program and run it inside ``root``."""
    # Imported lazily: compiler is portable, but the runner is not (see the
    # module docstring).
    from app.grading.compiler import CompilerError, compile_source
    from app.grading.runner import RunnerError, run_binary

    source = root / "probe.c"
    binary = root / "probe"
    try:
        source.write_text(_PROBE_SOURCE, encoding="utf-8")
    except OSError as exc:
        return _failure(compiler, standard, f"could not write probe source: {exc}")

    try:
        compiled = compile_source(
            source,
            binary,
            compiler=compiler,
            standard=standard,
            timeout_seconds=max(1, timeout_ms // 1000),
        )
    except CompilerError as exc:
        return _failure(compiler, standard, str(exc))

    if not compiled.success:
        diagnostics = _first_line(compiled.diagnostics) or "unknown error"
        return _failure(compiler, standard, f"compilation failed: {diagnostics}")

    try:
        outcome = run_binary(binary, workspace=root, timeout_ms=_RUN_TIMEOUT_MS)
    except RunnerError as exc:
        return _failure(compiler, standard, str(exc))
    except OSError as exc:
        return _failure(compiler, standard, f"could not execute compiled binary: {exc}")

    if outcome.spawn_error:
        # The classic noexec case: compilation worked, execution cannot start.
        return _failure(
            compiler,
            standard,
            f"could not execute compiled binary: {outcome.spawn_error}",
        )
    if outcome.timed_out:
        return _failure(
            compiler,
            standard,
            f"compiled binary did not finish within {_RUN_TIMEOUT_MS} ms",
        )
    if outcome.stdout.strip() != "ok":
        return _failure(compiler, standard, "compiled binary produced unexpected output")

    return GradingProbe(ready=True, compiler=compiler, standard=standard, detail="")


def _failure(compiler: str, standard: str, detail: str) -> GradingProbe:
    """Build a not-ready result with a short, client-safe detail."""
    return GradingProbe(
        ready=False,
        compiler=compiler,
        standard=standard,
        detail=_shorten(detail),
    )


def _store(key: tuple[str, str], result: GradingProbe) -> None:
    """Cache ``result`` and drop entries that have already expired."""
    now = time.monotonic()
    for stale in [k for k, (at, _) in _CACHE.items() if now - at >= _CACHE_TTL_SECONDS]:
        del _CACHE[stale]
    _CACHE[key] = (now, result)


def _first_line(text: str) -> str:
    """Return the first non-empty line of compiler diagnostics."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _shorten(text: str) -> str:
    """Collapse whitespace and truncate so a detail stays one short line."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= _MAX_DETAIL_LENGTH:
        return cleaned
    return cleaned[: _MAX_DETAIL_LENGTH - 3].rstrip() + "..."
