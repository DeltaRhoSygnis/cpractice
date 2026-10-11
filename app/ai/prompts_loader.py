"""Versioned prompt assets.

Prompts live as Markdown files rather than inline Python strings so they can be
reviewed, diffed, and versioned independently of application logic.

The ``PROMPT_VERSION`` is recorded with each generated problem, so a package can
be traced back to the prompt that produced it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

#: Bump when any prompt asset changes materially. Recorded on generated
#: problems so a package's provenance is traceable.
PROMPT_VERSION = "2.2.0"

#: Logical name -> asset filename.
ASSETS = {
    "calibration": "calibration.md",
    "system_role": "system_role.md",
    "build_blueprint": "build_blueprint.md",
    "write_specification": "write_specification.md",
    "design_tests": "design_tests.md",
    "create_reference_solution": "create_reference_solution.md",
    "review_pedagogical_quality": "review_pedagogical_quality.md",
    "create_progressive_hints": "create_progressive_hints.md",
    "repair_invalid_package": "repair_invalid_package.md",
}


class PromptAssetError(RuntimeError):
    """Raised when a prompt asset is missing or empty."""


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt asset by logical name.

    Cached because prompts are read on every generation request and never
    change while the process runs.
    """
    filename = ASSETS.get(name)
    if filename is None:
        raise PromptAssetError(
            f"unknown prompt asset {name!r}; known: {sorted(ASSETS)}"
        )

    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise PromptAssetError(f"prompt asset missing: {path}")

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PromptAssetError(f"prompt asset is empty: {path}")

    return text


def available_prompts() -> list[str]:
    """Logical names of every declared asset."""
    return sorted(ASSETS)


def missing_assets() -> list[str]:
    """Assets declared but absent or empty on disk."""
    missing: list[str] = []
    for name in ASSETS:
        try:
            load_prompt(name)
        except PromptAssetError:
            missing.append(name)
    return missing
