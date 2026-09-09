#!/usr/bin/env python3
"""Section headings as SVG - the only way to put your own typeface on a heading.

GitHub strips <style>, class and font attributes from README markdown, so the
choice for body text is its sans or its monospace and nothing else. Anything in
JetBrains Mono has to be an image.

Stated plainly: image headings have no anchor links, so the README outline in
GitHub's sidebar goes empty. The alt text carries the word for screen readers.
That is the trade being made here, deliberately.
"""

import base64
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"

LABELS = ["building", "activity"]

THEMES = {
    "light": dict(ink="#59636e", rule="#d1d9e0"),
    "dark": dict(ink="#9198a1", rule="#3d444d"),
}

W, H = 880, 26
SIZE = 12.0
TRACK = 2.2                       # letter-spacing; lowercase mono needs air


def font_face() -> str:
    b64 = base64.b64encode((ASSETS / "fonts" / "jbm-head.woff2").read_bytes()).decode()
    return ("@font-face{font-family:'JBMH';font-style:normal;font-weight:400;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")


def build(label: str, t: dict) -> str:
    # 0.600em advance, plus the tracking we add between characters
    text_w = len(label) * (SIZE * 0.600 + TRACK)
    rule_x = text_w + 14
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" aria-label="{label}">'
        f"<style>{font_face()}</style>"
        f'<text x="0" y="17" font-family="JBMH,ui-monospace,monospace" '
        f'font-size="{SIZE}" letter-spacing="{TRACK}" fill="{t["ink"]}">{label}</text>'
        f'<line x1="{rule_x:.1f}" y1="12.5" x2="{W}" y2="12.5" stroke="{t["rule"]}"/>'
        "</svg>"
    )


def main() -> None:
    for label in LABELS:
        for theme, pal in THEMES.items():
            dst = ASSETS / f"h-{label}-{theme}.svg"
            dst.write_text(build(label, pal))
    print(f"  {len(LABELS) * len(THEMES)} headings -> {ASSETS}")


if __name__ == "__main__":
    main()
