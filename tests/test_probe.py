import shutil
import stat
from pathlib import Path

import pytest

from app.grading.probe import probe_grading


@pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc not installed")
def test_probe_reports_ready_with_real_compiler(tmp_path) -> None:
    result = probe_grading(compiler="gcc", standard="c11", workdir=tmp_path, use_cache=False)
    assert result.ready is True
    assert result.detail == ""


def test_probe_reports_failure_for_unusable_compiler(tmp_path) -> None:
    fake = tmp_path / "fake-cc"
    fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    result = probe_grading(compiler=str(fake), standard="c11", workdir=tmp_path, use_cache=False)
    assert result.ready is False
    assert result.detail
