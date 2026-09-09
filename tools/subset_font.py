#!/usr/bin/env python3
"""Subset JetBrains Mono per role and write woff2.

An external font URL cannot work here: these SVGs load through an <img> tag and
browsers refuse subresource fetches for image documents. A @font-face with a
base64 data URI does work - but every SVG carries its own copy, so subset hard
or the page gets heavy. Inlining a full TTF into each file would be ~4.5 MB.

JetBrains Mono is SIL OFL 1.1, so it can live in a public repo. Ship OFL.txt
next to it.
"""

import pathlib

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = ROOT / "build"
OUT = ROOT / "assets" / "fonts"

RAMP = " .,:;=+*xo%#@"
HEADINGS = "abcdefghijklmnopqrstuvwxyz"          # any lowercase label, cheaply
DATA = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " .,:;-–—/%()·→+"
    + RAMP          # year.svg draws the calendar with the portrait's ramp
)

JOBS = [
    ("jbm-ramp.woff2", "JetBrainsMono-Regular.ttf", RAMP),
    ("jbm-head.woff2", "JetBrainsMono-Regular.ttf", HEADINGS + " "),
    ("jbm-data.woff2", "JetBrainsMono-Regular.ttf", DATA),
]


def build(name: str, src: str, chars: str) -> None:
    font = TTFont(BUILD / src)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    opts.layout_features = []          # no kerning/ligatures needed for a grid
    opts.name_IDs = []
    opts.notdef_outline = False
    opts.recalc_bounds = True
    sub = subset.Subsetter(options=opts)
    sub.populate(text="".join(sorted(set(chars))))
    sub.subset(font)
    dst = OUT / name
    font.save(dst)
    font.close()
    print(f"  {name:22s} {len(set(chars)):3d} glyphs  {dst.stat().st_size / 1024:5.1f} KB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lic = BUILD / "OFL.txt"
    if lic.exists():
        (OUT / "OFL.txt").write_text(lic.read_text())
    for name, src, chars in JOBS:
        build(name, src, chars)
    total = sum(p.stat().st_size for p in OUT.glob("*.woff2"))
    print(f"  total {total / 1024:.1f} KB of font across the page")


if __name__ == "__main__":
    main()
