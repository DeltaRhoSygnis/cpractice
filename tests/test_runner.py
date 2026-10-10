"""Tests for the execution runner's limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.grading.compiler import compile_source
from app.grading.runner import RunnerError, run_binary

ECHO_PROGRAM = """\
#include <stdio.h>
int main(void) {
    char buf[256];
    if (fgets(buf, sizeof buf, stdin)) fputs(buf, stdout);
    return 0;
}
"""

CRASH_PROGRAM = """\
int main(void) { return *(volatile int *)0; }
"""

EXIT_PROGRAM = """\
int main(void) { return 7; }
"""


def _build(tmp_path: Path, source: str, name: str = "program") -> Path:
    src = tmp_path / "main.c"
    src.write_text(source)
    binary = tmp_path / name
    result = compile_source(src, binary)
    assert result.success, result.diagnostics
    return binary


def test_runs_program_and_captures_stdout(tmp_path: Path) -> None:
    binary = _build(tmp_path, ECHO_PROGRAM)

    outcome = run_binary(binary, stdin_text="ping\n", workspace=tmp_path)

    assert outcome.stdout.strip() == "ping"
    assert outcome.exit_code == 0
    assert not outcome.timed_out


def test_infinite_loop_hits_timeout(tmp_path: Path) -> None:
    binary = _build(tmp_path, "int main(void){for(;;);}")

    outcome = run_binary(binary, workspace=tmp_path, timeout_ms=800)

    assert outcome.timed_out is True
    assert outcome.exit_code is None


def test_runaway_output_is_capped(tmp_path: Path) -> None:
    program = """\
#include <stdio.h>
int main(void){ for (long i=0;i<500000;i++) putchar('A'); return 0; }
"""
    binary = _build(tmp_path, program)

    outcome = run_binary(binary, workspace=tmp_path, max_output_bytes=4096)

    assert outcome.output_limit_exceeded is True
    assert len(outcome.stdout) < 8192


def test_nonzero_exit_code_is_captured(tmp_path: Path) -> None:
    binary = _build(tmp_path, EXIT_PROGRAM)

    outcome = run_binary(binary, workspace=tmp_path)

    assert outcome.exit_code == 7


def test_segfault_is_reported_not_crashed_runner(tmp_path: Path) -> None:
    binary = _build(tmp_path, CRASH_PROGRAM)

    outcome = run_binary(binary, workspace=tmp_path)

    # The runner survives; the program's failure shows as a signal exit.
    assert outcome.exit_code is not None
    assert outcome.exit_code != 0


def test_missing_binary_raises_runner_error(tmp_path: Path) -> None:
    with pytest.raises(RunnerError):
        run_binary(tmp_path / "does-not-exist", workspace=tmp_path)


def test_program_runs_in_its_workspace(tmp_path: Path) -> None:
    # A program that reads a sibling file proves the cwd is the workspace.
    (tmp_path / "data.txt").write_text("sibling-content")
    program = """\
#include <stdio.h>
int main(void){
    FILE *f = fopen("data.txt","r");
    if (!f) return 1;
    char buf[64]; fgets(buf, sizeof buf, f); fputs(buf, stdout); return 0;
}
"""
    binary = _build(tmp_path, program)

    outcome = run_binary(binary, workspace=tmp_path)

    assert outcome.exit_code == 0
    assert outcome.stdout.strip() == "sibling-content"


def test_memory_limit_does_not_prevent_execution(tmp_path: Path) -> None:
    """A memory limit must never stop the program from starting.

    On Android the runner skips ``RLIMIT_AS`` entirely because bionic aborts
    at load time when an address-space cap is applied; on other platforms the
    limit is applied normally. Either way the program must run successfully.
    """
    binary = _build(tmp_path, ECHO_PROGRAM)

    outcomes = [
        run_binary(
            binary,
            stdin_text="ping\n",
            workspace=tmp_path,
            memory_limit_mb=64,
        )
        for _ in range(5)
    ]

    assert all(o.exit_code == 0 for o in outcomes), [o.spawn_error for o in outcomes]
    assert all(o.stdout.strip() == "ping" for o in outcomes)


def test_repeated_execution_is_deterministic(tmp_path: Path) -> None:
    """Repeated runs of the same binary give identical results."""
    binary = _build(tmp_path, ECHO_PROGRAM)

    results = {
        (o.stdout, o.exit_code)
        for o in (run_binary(binary, stdin_text="same\n", workspace=tmp_path) for _ in range(5))
    }

    assert results == {("same\n", 0)}


def test_crash_is_reported_as_signal_not_plain_exit(tmp_path: Path) -> None:
    """A segfault must surface as a signal death, not exit code 1.

    This guards the Android regression where applying RLIMIT_NPROC made
    signal deaths report as exit code 1, silently converting crashes into
    wrong answers.
    """
    binary = _build(tmp_path, CRASH_PROGRAM)

    outcome = run_binary(binary, workspace=tmp_path)

    assert outcome.killed_by_signal is True
    assert outcome.signal_number is not None
    assert outcome.signal_number > 0


def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    """A timed-out program is killed and reported, not left running."""
    binary = _build(tmp_path, "int main(void){for(;;);}")

    outcome = run_binary(binary, workspace=tmp_path, timeout_ms=600)

    assert outcome.timed_out is True
    assert outcome.exit_code is None
