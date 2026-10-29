"""Opt-in gate proving the built wheel ships the runtime assets.

Building a wheel takes several seconds and needs network access for build
isolation, so this module skips unless ``CPRACTICE_BUILD_WHEEL=1``. CI runs it
on the Python 3.12 leg only, after the regular test suite.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    os.environ.get("CPRACTICE_BUILD_WHEEL") != "1",
    reason="set CPRACTICE_BUILD_WHEEL=1",
)
def test_wheel_contains_runtime_assets(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp_path), str(ROOT)],
        check=True,
        capture_output=True,
    )

    # A failed or interrupted build must not leave a stale/partial archive that
    # silently satisfies the assertions below.
    wheels = sorted(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one wheel, got {[w.name for w in wheels]}"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()

    assert "app/web/index.html" in names
    assert "app/web/app.js" in names
    assert any(name.startswith("app/seed_problems/c-sum-two-integers/") for name in names)
    assert any(name.startswith("app/seed_problems/pset-vote-tally/") for name in names)
