"""Theme -> CPAL palette + @font-palette-values CSS."""

from __future__ import annotations

import re

from fontTools.ttLib.tables.C_P_A_L_ import Color

from .schema import NUM_PALETTES, PALETTES, Theme

# neutral fallback for theme slots that are not specified
_FALLBACK = "#808080"


def palette_ident(name: str) -> str:
    """`@font-palette-values` names are <dashed-ident>s: they must start with
    `--`. Sanitize a theme name into one."""
    ident = re.sub(r"[^A-Za-z0-9_-]", "-", name).strip("-")
    return f"--{ident or 'theme'}"


def hex_to_rgba(color: str) -> Color:
    """Parse '#rgb' / '#rrggbb' into a CPAL Color (0-255 channels)."""
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    if len(color) != 6:
        raise ValueError(f"invalid color: {color!r}")
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return Color.fromRGBA(red=r, green=g, blue=b, alpha=255)


def build_palette(theme: Theme) -> list[Color]:
    """Return a CPAL color list indexed by palette index.

    Slot 0 is a filler (base glyphs are not painted through COLR)."""
    palette = [hex_to_rgba(_FALLBACK)] * NUM_PALETTES
    for slot, index in PALETTES.items():
        if slot in theme.colors:
            palette[index] = hex_to_rgba(theme.colors[slot])
    return palette


def css_font_palette_values(family: str, themes: list[Theme]) -> str:
    """Emit an @font-palette-values block per theme so users can switch themes
    from CSS without rebuilding the font."""
    lines = []
    for theme in themes:
        lines.append(f"@font-palette-values {palette_ident(theme.name)} {{")
        lines.append(f"  font-family: '{family}';")
        overrides = [
            f"{PALETTES[slot]} {color}"
            for slot, color in theme.colors.items()
        ]
        lines.append("  override-colors: " + ", ".join(overrides) + ";")
        lines.append("}")
        lines.append("")
    if themes:
        lines.append(f"code {{ font-palette: {palette_ident(themes[0].name)}; }}")
    return "\n".join(lines) + "\n"
