"""Ligature handling.

By default the base font's GSUB is replaced, so its ligatures are dropped.
With ``keep_ligatures`` the base GSUB is kept and our lookups are merged in:
region (comment/string) lookups run first (so a `//` delimiter is colored
rather than ligated), the base's ligature lookups next, and the rest last.
"""

from __future__ import annotations

import os

import pytest
import uharfbuzz as hb

from syntaxfont.builder import build_highlight_font

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


def _shape(path: str, text: str) -> list[str]:
    font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True, "liga": True})
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]


def _gsub_features(path: str) -> set[str]:
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    if "GSUB" not in font:
        return set()
    return {fr.FeatureTag for fr in font["GSUB"].table.FeatureList.FeatureRecord}


@pytest.fixture(scope="module")
def ligature_font(tmp_path_factory) -> str:
    """The base font with a `liga` (`fi`->`j`) and a `calt` (`->`->`j`) ligature
    added, standing in for a programming-ligature font."""
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.ttLib import TTFont

    font = TTFont(BASE_FONT)
    fea = (
        "feature liga { sub f i by j; } liga;\n"
        "feature calt { sub hyphen greater by j; } calt;"
    )
    addOpenTypeFeaturesFromString(font, fea, tables=["GSUB"])
    path = str(tmp_path_factory.mktemp("liga") / "base.ttf")
    font.save(path)
    return path


def test_ligatures_dropped_by_default(ligature_font, tmp_path, languages, theme):
    assert {"liga", "calt"} <= _gsub_features(ligature_font)

    out = tmp_path / "hl.ttf"
    build_highlight_font(ligature_font, languages, theme, str(out), flavor=None)

    assert _gsub_features(str(out)) == {"calt"}  # base ligatures dropped
    assert _shape(str(out), "fi") == ["f", "i"]  # no ligature
    assert _shape(str(out), "->") != ["j"]  # no ligature


def test_keep_ligatures_preserves_them_but_highlights(
    ligature_font, tmp_path, languages, theme
):
    out = tmp_path / "hl.ttf"
    build_highlight_font(
        ligature_font, languages, theme, str(out), flavor=None, keep_ligatures=True
    )

    # ligatures survive (liga and calt)
    assert _shape(str(out), "fi") == ["j"]
    assert _shape(str(out), "->") == ["j"]
    # ...and highlighting still works
    assert _shape(str(out), "if") == ["i.alt3", "f.alt3"]
    assert _shape(str(out), "{") == ["braceleft.alt3"]
    # a comment delimiter is colored, not swallowed by a possible ligature
    assert all(n.endswith(".alt1") for n in _shape(str(out), "// x"))
    assert all(n.endswith(".alt2") for n in _shape(str(out), '"s"'))


def test_webapp_forwards_keep_ligatures(ligature_font, tmp_path):
    """The browser entry point exposes the same option."""
    from syntaxfont.webapp import (
        build_from_bytes,
        language_from_yaml,
        theme_from_yaml,
    )

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js_yaml = open(os.path.join(root, "languages", "js.yaml")).read()
    default_yaml = open(os.path.join(root, "themes", "default.yaml")).read()
    base = open(ligature_font, "rb").read()

    result = build_from_bytes(
        base,
        [language_from_yaml(js_yaml)],
        theme_from_yaml(default_yaml),
        flavor=None,
        keep_ligatures=True,
    )
    out = tmp_path / result["filename"]
    out.write_bytes(result["font"])
    assert _shape(str(out), "fi") == ["j"]
    assert _shape(str(out), "if") == ["i.alt3", "f.alt3"]


def test_kept_ligature_glyphs_are_colored(tmp_path, languages, theme):
    # the base font has `=>` -> `equal_greater.liga` in calt
    from fontTools.ttLib import TTFont

    from syntaxfont.schema import PALETTES

    out = tmp_path / "hl.ttf"
    build_highlight_font(
        BASE_FONT, languages, theme, str(out), flavor=None, keep_ligatures=True
    )
    assert _shape(str(out), "=>")[-1] == "equal_greater.liga"

    font = TTFont(str(out))
    layers = font["COLR"].ColorLayers
    # the ligature glyph is painted with the colour of its components, so
    # `=>` matches `=` (`value`); `&&` would stay `symbol`
    assert layers["equal_greater.liga"][0].colorID == PALETTES["value"]
