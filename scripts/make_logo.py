#!/usr/bin/env python3
"""Render the SyntaxFont logo (header mark, README mark, favicon + ICO).

The mark is a neobrutalist tile (thick border + hard offset shadow -- same look
as the web app) filled edge-to-edge with the literal text ``<F/>`` set in the
heaviest Iosevka.  The brackets share one highlight colour and ``F`` another, so
the logo itself demonstrates the syntax highlighting it generates.

The viewBox hugs the tile + shadow exactly like CJKonospace's mark, so the
``<img>``/favicon box is filled with no dead margin.

Writes:
  assets/logo.svg        README / light mark (static colours)
  assets/logo-dark.svg   README dark mark
  assets/logo.png        high-resolution README raster (light)
  assets/logo-dark.png   high-resolution README raster (dark)
  web/logo.svg           header mark (follows prefers-color-scheme)
  web/favicon.svg        favicon (follows prefers-color-scheme)
  web/favicon.ico        legacy multi-size icon (light)
"""

from __future__ import annotations

import os
import subprocess
import urllib.request

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, ".cache")

# Iosevka ships as huge release archives; the Fontsource webfont is the same
# upstream build, just packaged small.  We cache a converted TTF so later runs
# need neither network nor brotli.
FONT_URL = (
    "https://cdn.jsdelivr.net/npm/@fontsource/iosevka@5.3.0/files/iosevka-latin-900-normal.woff2"
)

# --- tile geometry (in the SVG's own units) --------------------------------
TILE = 220.0  # tile side
RING = 14.0  # border thickness (centred on the tile edge)
RADIUS = 20.0
OFFSET = 16.0  # hard shadow offset
PAD = 1.0  # hairline so antialiasing never clips

# --- text layout ------------------------------------------------------------
FILL = 0.96  # fraction of the tile's inner box the text block occupies
LINES: list[list[tuple[str, str]]] = [
    [("<", "punct"), ("F", "tag"), ("/", "punct"), (">", "punct")],
]

PALETTES = {
    "light": {
        "bg": "#ffffff",
        "border": "#000000",
        "punct": "#d73a49",  # keyword red
        "tag": "#005cc5",  # builtin blue
    },
    "dark": {
        "bg": "#000000",
        "border": "#ffffff",
        "punct": "#ff7b72",  # brighter red for a black tile
        "tag": "#79c0ff",  # brighter blue for a black tile
    },
}
# the hard shadow uses the border colour, so it reads as extra border depth
for _p in PALETTES.values():
    _p["shadow"] = _p["border"]


def ensure_font() -> str:
    ttf = os.path.join(CACHE, "Iosevka-Black.ttf")
    if os.path.exists(ttf):
        return ttf
    os.makedirs(CACHE, exist_ok=True)
    woff2 = os.path.join(CACHE, "Iosevka-Black.woff2")
    if not os.path.exists(woff2):
        print(f"downloading Iosevka from {FONT_URL}")
        urllib.request.urlretrieve(FONT_URL, woff2)
    try:
        font = TTFont(woff2)
    except ImportError as exc:  # woff2 needs brotli
        raise SystemExit(
            "reading the Iosevka woff2 needs brotli; run `uv sync --extra dev`"
        ) from exc
    font.flavor = None
    font.save(ttf)
    return ttf


def _glyph_reader(font: TTFont):
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    cache: dict[str, tuple[str, tuple | None, int]] = {}

    def read(ch: str):
        if ch not in cache:
            name = cmap[ord(ch)]
            pen = SVGPathPen(glyphs)
            glyphs[name].draw(pen)
            bounds = BoundsPen(glyphs)
            glyphs[name].draw(bounds)
            cache[ch] = (pen.getCommands(), bounds.bounds, font["hmtx"][name][0])
        return cache[ch]

    return read


def _layout(font: TTFont):
    """Return (pieces, bbox) in font units; y grows upward."""
    read = _glyph_reader(font)
    space = font["hmtx"][font.getBestCmap()[ord(" ")]][0]
    pieces = []  # (path, slot, dx, dy)
    x0 = y0 = 1e18
    x1 = y1 = -1e18
    for line in LINES:
        x = 0.0
        baseline = 0.0
        for ch, slot in line:
            if ch == " ":
                advance = space
            else:
                path, bounds, advance = read(ch)
                pieces.append((path, slot, x, baseline))
                if bounds:
                    bx0, by0, bx1, by1 = bounds
                    x0 = min(x0, x + bx0)
                    x1 = max(x1, x + bx1)
                    y0 = min(y0, baseline + by0)
                    y1 = max(y1, baseline + by1)
            x += advance
    return pieces, (x0, y0, x1, y1)


def _box():
    outer = RING / 2
    x0 = min(-outer, OFFSET) - PAD
    y0 = min(-outer, OFFSET) - PAD
    x1 = max(TILE + outer, OFFSET + TILE) + PAD
    y1 = max(TILE + outer, OFFSET + TILE) + PAD
    return x0, y0, x1 - x0, y1 - y0


def _style(mode: str) -> str:
    def rules(p):
        return (
            f".card{{fill:{p['bg']};stroke:{p['border']};stroke-width:{RING:g}}}"
            f".shadow{{fill:{p['shadow']}}}"
            f".punct{{fill:{p['punct']}}}"
            f".tag{{fill:{p['tag']}}}"
        )

    if mode == "auto":
        light, dark = PALETTES["light"], PALETTES["dark"]
        return f"<style>{rules(light)}@media (prefers-color-scheme:dark){{{rules(dark)}}}</style>"
    return f"<style>{rules(PALETTES[mode])}</style>"


def build(mode: str) -> str:
    font = TTFont(ensure_font())
    pieces, (fx0, fy0, fx1, fy1) = _layout(font)
    inner = TILE - RING
    scale = FILL * inner / max(fx1 - fx0, fy1 - fy0)
    tx = TILE / 2 - scale * (fx0 + fx1) / 2
    ty = TILE / 2 + scale * (fy0 + fy1) / 2

    bx, by, bw, bh = _box()
    paths = "".join(
        f'<path class="{slot}" d="{path}" transform="translate({dx:.1f} {dy:.1f})"/>'
        for path, slot, dx, dy in pieces
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{bw:.0f}" height="{bh:.0f}" '
        f'viewBox="{bx:.1f} {by:.1f} {bw:.1f} {bh:.1f}" '
        f'role="img" aria-label="SyntaxFont">'
        f"{_style(mode)}"
        f'<rect class="shadow" x="{OFFSET:g}" y="{OFFSET:g}" '
        f'width="{TILE:g}" height="{TILE:g}" rx="{RADIUS:g}"/>'
        f'<rect class="card" width="{TILE:g}" height="{TILE:g}" rx="{RADIUS:g}"/>'
        f'<g transform="translate({tx:.2f} {ty:.2f}) scale({scale:.6f} -{scale:.6f})">'
        f"{paths}</g></svg>\n"
    )


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)
    print(f"wrote {os.path.relpath(path, ROOT)}")


def _rasterize(svg: str, png: str, size: int) -> None:
    try:
        subprocess.run(
            ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", png, svg],
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit("rsvg-convert (librsvg) is required for the PNG/ICO output") from None


def make_ico(svg: str, ico: str, sizes: tuple[int, ...]) -> None:
    from PIL import Image

    tmp = os.path.join(CACHE, "logo-ico.png")
    os.makedirs(CACHE, exist_ok=True)
    frames = []
    for size in sizes:
        _rasterize(svg, tmp, size)
        frames.append(Image.open(tmp).convert("RGBA").copy())
    frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    print(f"wrote {os.path.relpath(ico, ROOT)}")


def main() -> int:
    assets = os.path.join(ROOT, "assets")
    web = os.path.join(ROOT, "web")

    _write(os.path.join(assets, "logo.svg"), build("light"))
    _write(os.path.join(assets, "logo-dark.svg"), build("dark"))
    _write(os.path.join(web, "logo.svg"), build("auto"))
    _write(os.path.join(web, "favicon.svg"), build("auto"))

    light_png = os.path.join(assets, "logo.png")
    _rasterize(os.path.join(assets, "logo.svg"), light_png, 1024)
    print(f"wrote {os.path.relpath(light_png, ROOT)}")
    dark_png = os.path.join(assets, "logo-dark.png")
    _rasterize(os.path.join(assets, "logo-dark.svg"), dark_png, 1024)
    print(f"wrote {os.path.relpath(dark_png, ROOT)}")

    make_ico(
        os.path.join(assets, "logo.svg"),
        os.path.join(web, "favicon.ico"),
        (16, 24, 32, 48, 64, 128, 256),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
