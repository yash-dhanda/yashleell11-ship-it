#!/usr/bin/env python3
"""Photo -> ASCII self-portrait -> animated SVG.

Run locally, once. The output SVG is committed; CI never runs this.

Stages, and why each one is here:
  rembg cut-out      everything outside the subject becomes white, which maps to
                     the blank end of the ramp. Without it the background fills
                     with '@' and drowns the face.
  bilateral filter   smooths skin while keeping edges.
  equalise (masked)  over subject pixels only. This photo is low-key - subject
                     median is 44/255 - so the guide's percentile stretch left
                     hair and skin at the same value once CLAHE was done with
                     them. Equalising the subject's own histogram is what
                     separates them again.
  CLAHE (clip 1.5)   local contrast per tile. Clip 3.0 over-equalises a face
                     this dark and flattens hair into the skin.
  (v/255)^1.2        tone curve. The guide uses 1.7 to rescue a washed-out
                     photo; this one needs far less, or the face fills with '@'.
  ramp map           leading space clears the background to nothing.
"""

import argparse
import base64
import pathlib
import sys

import cv2
import numpy as np

# 13 levels, lightest -> darkest. The leading space is load-bearing.
RAMP = " .,:;=+*xo%#@"

FONT_SIZE = 12.9
CHAR_W = FONT_SIZE * 0.600      # JetBrains Mono advance. Do not guess this.
CHAR_H = CHAR_W / 0.48          # keeps the picture square-ish on screen
ROW_FACTOR = 0.48               # monospace cells are ~2x taller than wide
STAGGER = 0.09                  # seconds between row starts
ROW_DUR = 0.55                  # wipe duration for one row

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def cutout(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Subject on white. Cached - the model download is ~176 MB, once."""
    if dst.exists():
        print(f"  cutout cached: {dst}")
        return
    from rembg import remove, new_session

    print("  running rembg (first run downloads the model)...")
    session = new_session("u2net")
    with open(src, "rb") as fh:
        out = remove(fh.read(), session=session)
    dst.write_bytes(out)
    print(f"  wrote {dst}")


def to_gray_on_white(png: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """RGBA cut-out -> (greyscale composited onto pure white, subject mask)."""
    img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if img is None:
        sys.exit(f"cannot read {png}")
    if img.shape[2] == 4:
        rgb = img[:, :, :3].astype(np.float32)
        a = (img[:, :, 3:4].astype(np.float32)) / 255.0
        comp = rgb * a + 255.0 * (1.0 - a)
        mask = img[:, :, 3] > 20
    else:
        comp = img.astype(np.float32)
        mask = np.ones(img.shape[:2], bool)
    gray = cv2.cvtColor(comp.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    return gray, mask


def enhance(gray: np.ndarray, mask: np.ndarray, clip: float, gamma: float) -> np.ndarray:
    g = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # equalise across the subject's own histogram, not the whole frame - the
    # white background would otherwise own most of the range
    hist, _ = np.histogram(g[mask], 256, (0, 256))
    cdf = hist.cumsum() / max(hist.sum(), 1)
    g = np.interp(g.astype(np.float32), np.arange(256), cdf * 255).astype(np.uint8)
    g[~mask] = 255

    g = cv2.createCLAHE(clipLimit=clip, tileGridSize=(6, 6)).apply(g)
    g = (np.power(g.astype(np.float32) / 255.0, gamma) * 255.0).astype(np.uint8)
    g[~mask] = 255          # background stays at the blank end of the ramp
    return g


def to_ascii(gray: np.ndarray, cols: int) -> list[str]:
    h, w = gray.shape
    rows = max(1, int(round(cols * (h / w) * ROW_FACTOR)))
    small = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA)
    n = len(RAMP) - 1
    idx = np.rint((255 - small.astype(np.float32)) / 255.0 * n).astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def font_face(woff2: pathlib.Path) -> str:
    b64 = base64.b64encode(woff2.read_bytes()).decode()
    return (
        "@font-face{font-family:'JBM';font-style:normal;font-weight:400;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
    )


def build_svg(lines: list[str], woff2: pathlib.Path, width_px: int, ink: str) -> str:
    cols = max(len(l) for l in lines)
    vb_w = cols * CHAR_W
    vb_h = len(lines) * CHAR_H
    height_px = round(width_px * vb_h / vb_w)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" '
        f'viewBox="0 0 {vb_w:.2f} {vb_h:.2f}" role="img" '
        f'aria-label="ASCII portrait of Yash">',
        "<style>",
        font_face(woff2),
        f"text{{font-family:'JBM',ui-monospace,monospace;font-size:{FONT_SIZE}px;"
        f"fill:{ink};white-space:pre;dominant-baseline:hanging}}",
        f".cur{{fill:{ink}}}",
        "</style>",
        "<defs>",
    ]

    for i, line in enumerate(lines):
        y = i * CHAR_H
        begin = f"{i * STAGGER:.2f}s"
        parts.append(
            f'<clipPath id="c{i}"><rect x="0" y="{y:.2f}" width="0" height="{CHAR_H:.2f}">'
            f'<animate attributeName="width" from="0" to="{vb_w:.2f}" '
            f'begin="{begin}" dur="{ROW_DUR}s" fill="freeze"/></rect></clipPath>'
        )
    parts.append("</defs>")

    for i, line in enumerate(lines):
        y = i * CHAR_H
        begin = f"{i * STAGGER:.2f}s"
        parts.append(
            f'<text x="0" y="{y:.2f}" clip-path="url(#c{i})">{esc(line)}</text>'
        )
        # a small block rides the wipe edge, then vanishes
        parts.append(
            f'<rect class="cur" x="0" y="{y:.2f}" width="{CHAR_W:.2f}" height="{CHAR_H:.2f}" opacity="0">'
            f'<set attributeName="opacity" to="0.85" begin="{begin}" />'
            f'<animate attributeName="x" from="0" to="{vb_w - CHAR_W:.2f}" '
            f'begin="{begin}" dur="{ROW_DUR}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0" begin="{i * STAGGER + ROW_DUR:.2f}s"/>'
            f"</rect>"
        )

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", default=str(ROOT / "build" / "yash.jpg"))
    ap.add_argument("--crop", default="215,25,700,845", help="x,y,w,h on the original image")
    ap.add_argument("--cols", type=int, default=90)
    ap.add_argument("--clip", type=float, default=1.5)
    ap.add_argument("--gamma", type=float, default=1.2)
    ap.add_argument("--width", type=int, default=460)

    ap.add_argument("--woff2", default=str(ROOT / "assets" / "fonts" / "jbm-ramp.woff2"))
    ap.add_argument("--out", default=str(ROOT / "assets" / "portrait"))
    ap.add_argument("--txt", default=str(ROOT / "build" / "portrait.txt"))
    args = ap.parse_args()

    photo = pathlib.Path(args.photo)
    cut = ROOT / "build" / "cutout.png"
    cutout(photo, cut)

    gray, mask = to_gray_on_white(cut)
    if args.crop:
        x, y, w, h = (int(v) for v in args.crop.split(","))
        gray = gray[y : y + h, x : x + w]
        mask = mask[y : y + h, x : x + w]
        print(f"  cropped to {gray.shape[1]}x{gray.shape[0]}")

    gray = enhance(gray, mask, args.clip, args.gamma)
    lines = to_ascii(gray, args.cols)

    pathlib.Path(args.txt).write_text("\n".join(lines) + "\n")
    print(f"  {len(lines)} rows x {args.cols} cols -> {args.txt}")
    print(f"  type-on completes at ~{(len(lines) - 1) * STAGGER + ROW_DUR:.1f}s")

    # two inks: GitHub picks between them with <picture>, which follows the
    # site theme rather than the OS setting a media query inside the SVG sees
    for suffix, ink in (("light", "#30363d"), ("dark", "#adbac7")):
        svg = build_svg(lines, pathlib.Path(args.woff2), args.width, ink)
        dst = pathlib.Path(f"{args.out}-{suffix}.svg")
        dst.write_text(svg)
        print(f"  {len(svg) / 1024:5.1f} KB -> {dst}")


if __name__ == "__main__":
    main()
