#!/usr/bin/env python3
"""Derive the CPractice brand logo at every size the project needs.

The master artwork lives in the repository at ``docs/images/cpractice-logo.png``
so the brand never depends on a file outside version control. This script
emits the derived sizes:

    docs/images/cpractice-logo.png      1024x1024  master (source of truth)
    docs/images/cpractice-icon.png       512x512   the mark alone, for tight spaces
    docs/agensi/logos/cpractice.png      512x512   marketplace listing logo
    docs/images/cpractice-logo-256.png   256x256   small card / app header size

Usage:  python3 docs/agensi/make-brand-logo.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MASTER = REPO_ROOT / "docs" / "images" / "cpractice-logo.png"
ICON = REPO_ROOT / "docs" / "images" / "cpractice-icon.png"
MARKETPLACE_LOGO = REPO_ROOT / "docs" / "agensi" / "logos" / "cpractice.png"
SMALL = REPO_ROOT / "docs" / "images" / "cpractice-logo-256.png"

MASTER_SIZE = 1024
MARKETPLACE_SIZE = 512
SMALL_SIZE = 256

#: The C + terminal mark, isolated from the wordmark below it.
#: Measured on the 1024px master: the mark spans x 309-794, y 187-562.
ICON_BOX = (309, 100, 794, 585)


def save(img: Image.Image, path: Path) -> None:
    """Write a PNG with a palette, which keeps a flat brand mark small."""
    path.parent.mkdir(parents=True, exist_ok=True)
    quantized = img.quantize(
        colors=128, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG
    )
    quantized.save(path, "PNG", optimize=True)
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


def main() -> None:
    if not MASTER.is_file():
        raise SystemExit(f"missing master artwork: {MASTER}")

    master = Image.open(MASTER).convert("RGB")
    if master.size != (MASTER_SIZE, MASTER_SIZE):
        master = master.resize((MASTER_SIZE, MASTER_SIZE), Image.LANCZOS)
    save(master, MASTER)

    save(
        master.resize((MARKETPLACE_SIZE, MARKETPLACE_SIZE), Image.LANCZOS),
        MARKETPLACE_LOGO,
    )
    save(master.resize((SMALL_SIZE, SMALL_SIZE), Image.LANCZOS), SMALL)
    save(master.crop(ICON_BOX).resize((512, 512), Image.LANCZOS), ICON)


if __name__ == "__main__":
    main()
