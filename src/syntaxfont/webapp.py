"""Browser-friendly entry point, used by the WASM (Pyodide) front-end.

Everything the web app needs is expressed as pure functions over bytes/strings
so the same code can be unit-tested without a browser.
"""

from __future__ import annotations

import io
import os
import re
import struct
import tempfile

import yaml
from fontTools.ttLib import TTFont

from .builder import build_highlight_font
from .conflicts import detect_conflicts
from .palette import css_font_palette_values, css_language_features
from .schema import (
    Language,
    Theme,
    isolated_language_features,
    parse_language,
    parse_theme,
)


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


def ttc_faces(base_font: bytes) -> list[dict]:
    if base_font[:4] != b"ttcf":
        font = TTFont(io.BytesIO(base_font), lazy=True)
        nt = font["name"]
        return [{"index": 0, "family": nt.getDebugName(1) or "", "style": nt.getDebugName(2) or ""}]
    (num,) = struct.unpack(">L", base_font[8:12])
    faces = []
    for index in range(num):
        try:
            nt = TTFont(io.BytesIO(base_font), fontNumber=index, lazy=True)["name"]
        except Exception:
            break
        faces.append({"index": index, "family": nt.getDebugName(1) or "", "style": nt.getDebugName(2) or ""})
    return faces


def _sfnt_extension(path: str, font_number: int = 0) -> str:
    font = TTFont(path, fontNumber=font_number, lazy=True)
    return "otf" if "CFF " in font or "CFF2" in font else "ttf"


def build_from_bytes(
    base_font: bytes,
    languages: list[Language],
    theme: Theme,
    extra_themes: list[Theme] | None = None,
    flavor: str | None = "woff2",
    ttc_index: int = 0,
    name_suffix: str = "-highlight",
    color_all: bool = True,
    extra_chars: str = "",
    keep_ligatures: bool = False,
    language_ids: list[str] | None = None,
    isolated_languages: bool = False,
) -> dict:
    """Build a highlight font from in-memory inputs.

    Returns a dict with ``font`` (bytes), ``filename``, ``css``, ``fea`` and
    the ``flavor`` actually produced (woff2 may fall back to ttf if the brotli
    module is     unavailable, as can happen in a browser)."""
    # align ids with languages (the client sends ids for bundled ones only)
    ids: list[str | None] = list(language_ids or [])
    ids += [None] * (len(languages) - len(ids))
    feature_by_id = (
        isolated_language_features(ids, languages) if isolated_languages else {}
    )
    with tempfile.TemporaryDirectory() as tmp:
        base_path = os.path.join(tmp, "base")
        with open(base_path, "wb") as fh:
            fh.write(base_font)
        sfnt_ext = _sfnt_extension(base_path, ttc_index)

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
                keep_ligatures=keep_ligatures,
                language_ids=ids,
                isolated_languages=isolated_languages,
                font_number=ttc_index,
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

    family = TTFont(io.BytesIO(font_bytes))["name"].getDebugName(1)
    ext = os.path.splitext(out_path)[1]
    safe_family = re.sub(r"[^A-Za-z0-9._-]", "", family) or "SyntaxFont"
    filename = f"{safe_family}{name_suffix}{ext}"
    fmt = "woff2" if produced_flavor == "woff2" else ("opentype" if sfnt_ext == "otf" else "truetype")
    themes = [theme, *(extra_themes or [])]
    css_parts = [
        "@font-face {",
        f"  font-family: '{family}';",
        f"  src: url('{filename}') format('{fmt}');",
        "}",
        "",
        "code, pre {",
        f"  font-family: '{family}', monospace !important;",
        "}",
        "",
    ]
    if feature_by_id:
        css_parts.append(css_language_features(feature_by_id))
    css_parts.append(css_font_palette_values(family, themes))
    css = "\n".join(css_parts)
    return {
        "font": font_bytes,
        "family": family,
        "filename": filename,
        "css": css,
        "fea": fea,
        # only woff2 is a real flavor; "ttf"/None both mean the raw sfnt
        "flavor": "woff2" if produced_flavor == "woff2" else sfnt_ext,
        "language_features": feature_by_id,
        "warnings": [] if isolated_languages else detect_conflicts(languages),
    }
