#!/usr/bin/env python3
"""Generate flat 512x512 marketplace logos for the Agensi listings.

Geometric marks only, no text (font rendering differs per machine and the
marks have to read at 64px on a card). Two colours on a dark ground.

Usage:  python3 make-logos.py
Output: logos/<skill>.png
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
BG = (17, 21, 28)        # near-black ground
ACCENT = (94, 234, 212)  # teal
WARM = (251, 146, 60)    # orange, for the "wrong" / warning element
LIGHT = (226, 232, 240)  # off-white, for code lines
MUTED = (71, 85, 105)

OUT = Path(__file__).parent / "logos"


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE, SIZE), BG)
    return img, ImageDraw.Draw(img)


def rounded_card(d: ImageDraw.ImageDraw, inset: int = 56, radius: int = 64) -> None:
    d.rounded_rectangle(
        [inset, inset, SIZE - inset, SIZE - inset],
        radius=radius,
        outline=(35, 42, 55),
        width=6,
    )


def save(img: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    img.save(path, "PNG", optimize=True)
    print(f"wrote {path}")


def logo_code_review() -> None:
    img, d = base()
    rounded_card(d)
    # code lines behind the lens
    for i, y in enumerate((190, 250, 310)):
        d.rounded_rectangle([150, y, 150 + [150, 110, 190][i], y + 22], radius=11, fill=MUTED)
    # magnifier
    d.ellipse([120, 140, 320, 340], outline=ACCENT, width=18)
    d.line([300, 320, 400, 420], fill=ACCENT, width=26)
    # severity dot
    d.ellipse([276, 296, 316, 336], fill=WARM)
    save(img, "code-review")


def logo_debugging() -> None:
    img, d = base()
    rounded_card(d)
    # breakpoint crosshair
    d.ellipse([140, 140, 372, 372], outline=ACCENT, width=16)
    d.line([256, 150, 256, 362], fill=MUTED, width=8)
    d.line([160, 256, 352, 256], fill=MUTED, width=8)
    d.ellipse([222, 222, 290, 290], fill=WARM)
    # small "step" dots
    for x in (410, 446):
        d.ellipse([x, 300, x + 18, 318], fill=ACCENT)
    save(img, "debugging")


def logo_examination() -> None:
    img, d = base()
    rounded_card(d)
    # answer sheet: three rows, one ticked
    d.rounded_rectangle([130, 120, 382, 392], radius=28, outline=(35, 42, 55), width=6)
    for i, y in enumerate((180, 256, 332)):
        d.ellipse([164, y - 16, 196, y + 16], outline=MUTED, width=8)
        d.rounded_rectangle([220, y - 11, 348 - i * 30, y + 11], radius=11, fill=MUTED)
    # tick
    d.line([160, 336, 196, 372], fill=ACCENT, width=20)
    d.line([196, 372, 250, 300], fill=ACCENT, width=20)
    save(img, "examination")


def logo_retrieval() -> None:
    img, d = base()
    rounded_card(d)
    # circular arrow
    box = [136, 136, 376, 376]
    d.arc(box, start=40, end=320, fill=ACCENT, width=22)
    # arrow head at the 320-degree end
    head = (376, 376)
    ang = math.radians(320)
    tip = (head[0] + 42 * math.cos(ang), head[1] + 42 * math.sin(ang))
    d.polygon([tip, (tip[0] - 44, tip[1] - 16), (tip[0] - 10, tip[1] + 44)], fill=ACCENT)
    # stacked cards in the middle
    for i, y in enumerate((206, 254, 302)):
        d.rounded_rectangle([196, y, 316 - i * 22, y + 26], radius=13, fill=LIGHT if i == 2 else MUTED)
    save(img, "retrieval")


def logo_grader() -> None:
    img, d = base()
    rounded_card(d)
    # two verdict columns: pass and fail
    d.rounded_rectangle([122, 150, 250, 362], radius=22, outline=(35, 42, 55), width=6)
    d.rounded_rectangle([262, 150, 390, 362], radius=22, outline=(35, 42, 55), width=6)
    # tick
    d.line([156, 254, 182, 288], fill=ACCENT, width=20)
    d.line([182, 288, 222, 206], fill=ACCENT, width=20)
    # cross
    d.line([300, 216, 352, 288], fill=WARM, width=20)
    d.line([352, 216, 300, 288], fill=WARM, width=20)
    # base line
    d.rounded_rectangle([150, 396, 362, 412], radius=8, fill=MUTED)
    save(img, "deterministic-code-grader")


def logo_authoring() -> None:
    img, d = base()
    rounded_card(d)
    # page
    d.rounded_rectangle([132, 116, 320, 396], radius=22, outline=(35, 42, 55), width=6)
    for i, y in enumerate((176, 222, 268)):
        d.rounded_rectangle([164, y, 292 - i * 34, y + 18], radius=9, fill=MUTED)
    # tick column
    for i, y in enumerate((170, 232, 294)):
        col = ACCENT if i < 2 else WARM
        d.line([330, y + 14, 344, y + 28], fill=col, width=14)
        d.line([344, y + 28, 376, y - 8], fill=col, width=14)
    save(img, "exercise-authoring")


def logo_autograder() -> None:
    """A decided verdict above a split result: one verdict, many test outcomes."""
    img, d = base()
    rounded_card(d)
    # The verdict: one solid, unambiguous bar.
    d.rounded_rectangle([136, 160, 376, 224], radius=32, fill=LIGHT)
    # The per-test results underneath it: one passed, one failed.
    d.rounded_rectangle([136, 288, 246, 352], radius=32, fill=ACCENT)
    d.rounded_rectangle([266, 288, 376, 352], radius=32, fill=WARM)
    # The boundary between them: software decides, in the middle.
    d.rectangle([251, 288, 261, 352], fill=MUTED)
    save(img, "deterministic-autograder")


if __name__ == "__main__":
    logo_code_review()
    logo_debugging()
    logo_examination()
    logo_retrieval()
    logo_grader()
    logo_authoring()
    logo_autograder()
