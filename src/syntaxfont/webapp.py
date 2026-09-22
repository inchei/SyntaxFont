"""Browser-friendly entry point, used by the WASM (Pyodide) front-end.

Everything the web app needs is expressed as pure functions over bytes/strings
so the same code can be unit-tested without a browser.
"""

from __future__ import annotations

import io
import os
import re
import tempfile

import yaml
from fontTools.ttLib import TTFont

from .builder import build_highlight_font
from .palette import css_font_palette_values
from .schema import Language, Theme, parse_language, parse_theme


def family_name(base_font: bytes) -> str:
    """Best name-ID-1 (family) string for a font, via fontTools."""
    try:
        font = TTFont(io.BytesIO(base_font), lazy=True)
        return (font["name"].getDebugName(1) or "").strip()
    except Exception:  # no name table / unparseable
        return ""


def language_from_yaml(text: str) -> Language:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("language YAML must be a mapping")
    return parse_language(data)


def theme_from_yaml(text: str) -> Theme:
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("theme YAML must be a mapping")
    return parse_theme(data)


def _sfnt_extension(path: str) -> str:
    font = TTFont(path, lazy=True)
    return "otf" if "CFF " in font or "CFF2" in font else "ttf"


def build_from_bytes(
    base_font: bytes,
    languages: list[Language],
    theme: Theme,
    extra_themes: list[Theme] | None = None,
    flavor: str | None = "woff2",
    family: str = "SyntaxFont",
    name_suffix: str = "-highlight",
    color_all: bool = True,
    extra_chars: str = "",
) -> dict:
    """Build a highlight font from in-memory inputs.

    Returns a dict with ``font`` (bytes), ``filename``, ``css``, ``fea`` and
    the ``flavor`` actually produced (woff2 may fall back to ttf if the brotli
    module is unavailable, as can happen in a browser)."""
    with tempfile.TemporaryDirectory() as tmp:
        base_path = os.path.join(tmp, "base")
        with open(base_path, "wb") as fh:
            fh.write(base_font)
        sfnt_ext = _sfnt_extension(base_path)

        def produce(flav: str | None) -> str:
            ext = "woff2" if flav == "woff2" else sfnt_ext
            out = os.path.join(tmp, f"out.{ext}")
            build_highlight_font(
                base_path,
                languages,
                theme,
                out,
                flavor=flav,
                emit_fea=os.path.join(tmp, "features.fea"),
                color_all=color_all,
                extra_chars=extra_chars,
            )
            return out

        produced_flavor = flavor
        try:
            out_path = produce(flavor)
        except Exception:
            if flavor != "woff2":
                raise
            # brotli missing (browser) -> fall back to a raw sfnt
            produced_flavor = None
            out_path = produce(None)

        with open(out_path, "rb") as fh:
            font_bytes = fh.read()
        with open(os.path.join(tmp, "features.fea")) as fh:
            fea = fh.read()

    ext = os.path.splitext(out_path)[1]
    safe_family = re.sub(r"[^A-Za-z0-9._-]", "", family) or "SyntaxFont"
    filename = f"{safe_family}{name_suffix}{ext}"
    fmt = "woff2" if produced_flavor == "woff2" else ("opentype" if sfnt_ext == "otf" else "truetype")
    themes = [theme, *(extra_themes or [])]
    css = "\n".join(
        [
            "@font-face {",
            f"  font-family: '{family}';",
            f"  src: url('{filename}') format('{fmt}');",
            "}",
            "",
            "code, pre {",
            f"  font-family: '{family}', monospace !important;",
            "}",
            "",
            css_font_palette_values(family, themes),
        ]
    )
    return {
        "font": font_bytes,
        "filename": filename,
        "css": css,
        "fea": fea,
        # only woff2 is a real flavor; "ttf"/None both mean the raw sfnt
        "flavor": "woff2" if produced_flavor == "woff2" else sfnt_ext,
    }
