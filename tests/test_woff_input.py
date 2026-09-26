"""WOFF/WOFF2 base fonts are accepted as input."""

from __future__ import annotations

import io

from fontTools.ttLib import TTFont
from helpers import BASE_FONT, DEFAULT_YAML, JS_YAML

from syntaxfont.webapp import build_from_bytes, language_from_yaml, theme_from_yaml


def _reflavored(flavor: str) -> bytes:
    buf = io.BytesIO()
    font = TTFont(BASE_FONT)
    font.flavor = flavor
    font.save(buf)
    return buf.getvalue()


def _check(base: bytes, tmp_path):
    result = build_from_bytes(
        base,
        [language_from_yaml(JS_YAML)],
        theme_from_yaml(DEFAULT_YAML),
        flavor="woff2",
    )
    assert result["family"] == "JetBrains Mono Syntax"
    assert result["flavor"] == "woff2"
    font = TTFont(io.BytesIO(result["font"]))
    assert font["name"].getDebugName(1) == "JetBrains Mono Syntax"
    assert "COLR" in font and "GSUB" in font


def test_woff2_input(tmp_path):
    _check(_reflavored("woff2"), tmp_path)


def test_woff_input(tmp_path):
    _check(_reflavored("woff"), tmp_path)
