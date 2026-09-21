"""Tests for the browser entry point (used by the Pyodide web app)."""

from __future__ import annotations

import os

from fontTools.ttLib import TTFont

from syntaxfont.webapp import (
    build_from_bytes,
    family_name,
    language_from_yaml,
    theme_from_yaml,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


def _read(path: str) -> str:
    with open(path) as fh:
        return fh.read()


JS_YAML = _read(os.path.join(ROOT, "languages", "js.yaml"))
DEFAULT_YAML = _read(os.path.join(ROOT, "themes", "default.yaml"))
NIGHT_YAML = _read(os.path.join(ROOT, "themes", "night.yaml"))


def test_build_from_bytes_woff2(tmp_path):
    with open(BASE_FONT, "rb") as fh:
        base = fh.read()
    result = build_from_bytes(
        base,
        [language_from_yaml(JS_YAML)],
        theme_from_yaml(DEFAULT_YAML),
        extra_themes=[theme_from_yaml(NIGHT_YAML)],
        family="Demo",
    )
    assert result["flavor"] == "woff2"
    assert result["filename"] == "Demo-highlight.woff2"

    out = tmp_path / result["filename"]
    out.write_bytes(result["font"])
    font = TTFont(str(out))
    assert "COLR" in font and "CPAL" in font
    assert any(fr.FeatureTag == "calt" for fr in font["GSUB"].table.FeatureList.FeatureRecord)

    assert "@font-face" in result["css"]
    assert "monospace !important" in result["css"]
    assert "@font-palette-values --night" in result["css"]
    assert "sub i' lookup ALT_SUBS_3 f' lookup ALT_SUBS_3;" in result["fea"]


def test_build_from_bytes_ttf_fallback():
    with open(BASE_FONT, "rb") as fh:
        base = fh.read()
    result = build_from_bytes(
        base,
        [language_from_yaml(JS_YAML)],
        theme_from_yaml(DEFAULT_YAML),
        flavor=None,
    )
    assert result["flavor"] == "ttf"
    assert result["filename"].endswith(".ttf")
    assert "format('truetype')" in result["css"]


def test_family_name_from_font():
    with open(BASE_FONT, "rb") as fh:
        base = fh.read()
    assert family_name(base) == "JetBrains Mono"


def test_filename_is_sanitized_but_family_kept():
    with open(BASE_FONT, "rb") as fh:
        base = fh.read()
    result = build_from_bytes(
        base,
        [language_from_yaml(JS_YAML)],
        theme_from_yaml(DEFAULT_YAML),
        flavor=None,
        family="JetBrains Mono-Syntax",
    )
    assert result["filename"] == "JetBrainsMono-Syntax-highlight.ttf"
    assert "font-family: 'JetBrains Mono-Syntax';" in result["css"]
