"""WOFF/WOFF2 base fonts are accepted as input."""

from __future__ import annotations

import io
import os

from fontTools.ttLib import TTFont

from syntaxfont.webapp import build_from_bytes, language_from_yaml, theme_from_yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_YAML = open(os.path.join(ROOT, "languages", "js.yaml")).read()
DEFAULT_YAML = open(os.path.join(ROOT, "themes", "default.yaml")).read()
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


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
