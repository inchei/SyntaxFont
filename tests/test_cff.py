"""OTF/CFF base fonts: build, shape, and produce an .otf fallback."""

from __future__ import annotations

import os

import pytest
import uharfbuzz as hb

from syntaxfont.builder import build_highlight_font
from syntaxfont.calt_gen import _ALL
from syntaxfont.webapp import build_from_bytes, language_from_yaml, theme_from_yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_YAML = open(os.path.join(ROOT, "languages", "js.yaml")).read()
DEFAULT_YAML = open(os.path.join(ROOT, "themes", "default.yaml")).read()

WIDTH = 600


def _glyph_name(ch: str) -> str:
    if ch == " ":
        return "space"
    if ch.isalpha():
        return ch
    return "uni%04X" % ord(ch)


def make_cff_font(path: str) -> str:
    """Build a minimal monospace CFF (OTF) font covering every colorable char."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    chars = list(dict.fromkeys(_ALL))
    glyph_order = [".notdef"] + [_glyph_name(c) for c in chars]
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({ord(c): _glyph_name(c) for c in chars})
    charstrings = {}
    for name in glyph_order:
        pen = T2CharStringPen(WIDTH, None)
        if name != ".notdef":
            pen.moveTo((50, 0))
            pen.lineTo((50, 700))
            pen.lineTo((550, 700))
            pen.lineTo((550, 0))
            pen.closePath()
        charstrings[name] = pen.getCharString()
    fb.setupCFF("TestCFF", {"FullName": "Test CFF"}, charstrings, {})
    fb.setupHorizontalMetrics({n: (WIDTH, 50) for n in glyph_order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "TestCFF", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(path)
    return path


@pytest.fixture(scope="module")
def cff_font(tmp_path_factory) -> str:
    return make_cff_font(str(tmp_path_factory.mktemp("cff") / "base.otf"))


def _shape(path: str, text: str) -> list[str]:
    font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True})
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]


def test_cff_font_builds_and_shapes(cff_font, tmp_path, languages, theme):
    from fontTools.ttLib import TTFont

    out = tmp_path / "hl.otf"
    build_highlight_font(cff_font, languages, theme, str(out), flavor=None)

    font = TTFont(str(out))
    assert "CFF " in font and "COLR" in font and "CPAL" in font
    assert "glyf" not in font  # outlines stay CFF

    assert _shape(str(out), "if") == ["i.alt3", "f.alt3"]
    assert all(n.endswith(".alt1") for n in _shape(str(out), "// hi"))


def test_webapp_cff_falls_back_to_otf(cff_font):
    with open(cff_font, "rb") as fh:
        base = fh.read()
    result = build_from_bytes(
        base,
        [language_from_yaml(JS_YAML)],
        theme_from_yaml(DEFAULT_YAML),
        flavor=None,
    )
    assert result["flavor"] == "otf"
    assert result["filename"].endswith(".otf")
    assert "format('opentype')" in result["css"]
