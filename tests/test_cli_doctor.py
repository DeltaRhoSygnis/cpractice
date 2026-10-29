"""Tests for the ``cpractice`` command skeleton and ``doctor``.

``doctor`` is the answer to "why doesn't this work on my machine?", so its
failures must be actionable and its import graph must stay light enough to run
on native Windows, where the Unix-only grading runner cannot be imported.
"""

from __future__ import annotations

from app import cli
from app.grading.probe import GradingProbe


def test_parser_exposes_commands() -> None:
    for command in ("start", "doctor", "problems", "open", "version"):
        assert cli.build_parser().parse_args([command]).command == command


def test_doctor_fails_with_remediation_when_compiler_missing(
    monkeypatch, capsys, tmp_path
) -> None:
    monkeypatch.setenv("CPRACTICE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "is_windows", lambda: False)
    monkeypatch.setattr(cli, "is_termux", lambda: False)
    monkeypatch.setattr(
        cli,
        "probe_grading",
        lambda **kwargs: GradingProbe(False, "gcc", "c11", "compiler failed"),
    )
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "build-essential" in out or "xcode-select" in out or "gcc" in out


def test_doctor_explains_native_windows(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "is_windows", lambda: True)
    assert cli.main(["doctor"]) == 1
    assert "WSL2" in capsys.readouterr().out
