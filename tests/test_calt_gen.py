"""Unit tests for FEA generation, schema parsing and the palette helpers."""

from __future__ import annotations

import pytest

from syntaxfont.calt_gen import _ALL, FeaBuilder, generate_features
from syntaxfont.palette import (
    build_palette,
    css_font_palette_values,
    hex_to_rgba,
    palette_ident,
)
from syntaxfont.schema import (
    PALETTES,
    Language,
    Theme,
    parse_language,
    parse_theme,
    resolve_chars,
)


def fake_glyphs() -> dict[str, str]:
    # AGL-ish names, digits like JetBrains Mono
    from syntaxfont.schema import glyph_name

    names = {c: glyph_name(c) for c in _ALL}
    for i, d in enumerate("0123456789"):
        names[d] = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"][i]
    return names


def test_resolve_chars_presets_and_literal():
    assert set(resolve_chars("letters")) == set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert resolve_chars("ab-") == ["a", "b", "-"]
    assert resolve_chars(None) == resolve_chars("ident")


def test_parse_language_defaults():
    lang = parse_language({"name": "x", "keywords": ["if"]})
    assert lang.name == "x" and lang.keywords == ["if"] and lang.numbers is True


def test_parse_theme_unknown_slot():
    with pytest.raises(ValueError):
        parse_theme({"name": "t", "colors": {"nope": "#fff"}})


def test_generate_features_contains_expected_constructs():
    lang = Language(
        name="js",
        keywords=["if"],
        literals=["true"],
        symbols="=(",
        numbers=True,
    )
    lang.fsm_tokens = parse_language(
        {"name": "js", "fsm_tokens": [{"start": "//", "palette": "comment"},
                                      {"start": '"', "end": '"', "palette": "string"}]}
    ).fsm_tokens
    fea = generate_features([lang], fake_glyphs())

    assert "@All = [" in fea
    assert "@AllAlt2 = [" in fea
    assert "lookup ALT_SUBS_3 {" in fea
    assert "sub i' lookup ALT_SUBS_3 f' lookup ALT_SUBS_3;" in fea
    assert "ignore sub" in fea
    assert "lookup AlwaysSymbols {" in fea
    assert "lookup AlwaysNumbers {" in fea
    assert "feature calt {" in fea


def test_fsm_stops_are_shared_per_palette():
    """Every comment FSM must ignore every other comment terminator."""
    lang = Language(name="js")
    lang.fsm_tokens = parse_language(
        {
            "name": "js",
            "fsm_tokens": [
                {"start": "//", "palette": "comment"},
                {"start": "/*", "end": "*/", "palette": "comment"},
            ],
        }
    ).fsm_tokens
    fea = generate_features([lang], fake_glyphs())
    # the line-comment FSM must also ignore the block-comment terminator
    line_fsm = fea.split("lookup Fsm_jsFsm0 {")[1].split("}")[0]
    assert "ignore sub asterisk.alt1 slash.alt1 @All';" in line_fsm


def test_palette_index_coverage():
    theme = parse_theme({"name": "t", "colors": {"keyword": "#ff0000"}})
    palette = build_palette(theme)
    assert len(palette) == 12
    # keyword slot maps to the requested color (BGRA namedtuple -> hex)
    kw = palette[PALETTES["keyword"]]
    assert (kw.red, kw.green, kw.blue) == (255, 0, 0)
    # unspecified slots fall back to gray
    assert palette[PALETTES["string"]] == hex_to_rgba("#808080")


def test_css_font_palette_values():
    theme = Theme(name="night", colors={"keyword": "#abcdef"})
    css = css_font_palette_values("MyFont", [theme])
    # @font-palette-values names must be dashed-idents
    assert "@font-palette-values --night {" in css
    assert "font-family: 'MyFont';" in css
    assert f"{PALETTES['keyword']} #abcdef" in css
    assert "font-palette: --night;" in css
    assert palette_ident("Default Theme!") == "--Default-Theme"
