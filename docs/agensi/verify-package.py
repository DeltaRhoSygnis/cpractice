#!/usr/bin/env python3
"""Verify a built skill ZIP against the marketplace's structural rules.

Usage:  python3 verify-package.py ../dist/deterministic-autograder.zip
Exit:   0 = every check passed, 1 = at least one check failed.

This file is a build-time tool. It is not shipped inside the archive.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

#: Anything that must not appear inside a published package.
#:
#: The product name is allowed - the package *is* the product. What must not
#: appear is the internal plumbing it was distilled from: repository paths,
#: repository URLs, provider names, and machine-specific paths.
FORBIDDEN_TEXT = re.compile(
    r"DeltaRhoSygnis|github\.com/|/data/data|bryllim|kenari|gemini|google_api|app/|ignore previous",
    re.IGNORECASE,
)

#: The only file types a listing may contain.
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".sh", ".py"}

#: The one listing this repository publishes.
SKILL_NAME = "cpractice"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify-package.py <zip>", file=sys.stderr)
        return 1

    zip_path = Path(sys.argv[1])
    problems: list[str] = []

    if not zip_path.is_file():
        print(f"FAIL: {zip_path} does not exist")
        return 1

    with zipfile.ZipFile(zip_path) as archive:
        names = [name for name in archive.namelist() if name.strip()]

        roots = {name.split("/")[0] for name in names}
        if len(roots) != 1:
            fail_line = f"expected exactly one top-level folder, found {sorted(roots)}"
            problems.append(fail_line)
        else:
            root = roots.pop()
            if root != SKILL_NAME:
                problems.append(f"top-level folder is {root!r}, expected {SKILL_NAME!r}")
            if f"{root}/SKILL.md" not in names:
                problems.append(f"{root}/SKILL.md is missing")

        for name in names:
            if name.startswith("__MACOSX/") or name.endswith((".DS_Store", "Thumbs.db")):
                problems.append(f"OS cruft in archive: {name}")
            suffix = Path(name).suffix.lower()
            if suffix and suffix not in TEXT_SUFFIXES:
                problems.append(f"non-text file in archive: {name}")

        for name in names:
            if not name.endswith("SKILL.md"):
                continue
            skill_text = archive.read(name).decode("utf-8")
            match = re.search(r"^name:\s*(.+)$", skill_text, re.MULTILINE)
            if match is None:
                problems.append("SKILL.md has no 'name:' frontmatter field")
            elif match.group(1).strip() != SKILL_NAME:
                problems.append(f"frontmatter name is {match.group(1).strip()!r}")
            if "description:" not in skill_text:
                problems.append("SKILL.md has no 'description:' frontmatter field")
            if "scripts/" in skill_text:
                problems.append("SKILL.md references a scripts/ directory")

        for name in names:
            body = archive.read(name).decode("utf-8", errors="replace")
            hit = FORBIDDEN_TEXT.search(body)
            if hit:
                problems.append(f"forbidden content {hit.group(0)!r} in {name}")

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    print(f"OK: {zip_path} satisfies every structural check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
