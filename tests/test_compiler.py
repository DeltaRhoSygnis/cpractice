"""Tests for the C compiler wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.grading.compiler import CompilerError, compile_source

OK_PROGRAM = """\
#include <stdio.h>
int main(void) { printf("hello\\n"); return 0; }
"""

BROKEN_PROGRAM = """\
#include <stdio.h>
int main(void) { printf("oops" return 0; }
"""


def test_compiles_valid_program(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    source.write_text(OK_PROGRAM)
    binary = tmp_path / "program"

    result = compile_source(source, binary)

    assert result.success is True
    assert binary.exists()
    assert result.duration_ms >= 0


def test_reports_failure_for_invalid_program(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    source.write_text(BROKEN_PROGRAM)
    binary = tmp_path / "program"

    result = compile_source(source, binary)

    assert result.success is False
    assert result.diagnostics != ""
    assert not binary.exists() or not result.success


def test_missing_header_is_a_compilation_failure(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    source.write_text("int main(void) { printf(\"x\"); return 0; }\n")
    binary = tmp_path / "program"

    result = compile_source(source, binary)

    # -Werror=implicit-function-declaration makes this fail fast.
    assert result.success is False


def test_unknown_compiler_raises_compiler_error(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    source.write_text(OK_PROGRAM)

    with pytest.raises(CompilerError):
        compile_source(source, tmp_path / "program", compiler="definitely-not-a-compiler")


def test_diagnostics_are_truncated(tmp_path: Path) -> None:
    source = tmp_path / "main.c"
    # Generate a large volume of genuine errors: use of undeclared identifiers.
    body = "\n".join(f"    undefined_symbol_{i}();" for i in range(5000))
    source.write_text(f"int main(void){{\n{body}\n    return 0;\n}}\n")
    binary = tmp_path / "program"

    result = compile_source(source, binary)

    assert result.success is False
    assert result.diagnostics != ""
    assert len(result.diagnostics) < 20_000
