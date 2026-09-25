"""Unit tests for FEA generation, schema parsing and the palette helpers."""

from __future__ import annotations

import pytest

from syntaxfont.calt_gen import (
    _ALL,
    FeaBuilder,
    generate_features,
    generate_isolated_features,
)
from syntaxfont.palette import (
    build_palette,
    css_font_palette_values,
    css_language_features,
    hex_to_rgba,
    palette_ident,
)
from syntaxfont.schema import (
    ISOLATED_LANGUAGE_FEATURES,
    PALETTES,
    Language,
    Theme,
    isolated_language_features,
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
        symbols={"value": "=("},
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
    assert "lookup AlwaysSymbols12 {" in fea
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
    # the shared comment FSM must also ignore the block-comment terminator
    fsm = fea.split("lookup FsmRegion {")[1].split("}")[0]
    assert "ignore sub asterisk.alt1 slash.alt1 @All';" in fsm


def test_palette_index_coverage():
    theme = parse_theme({"name": "t", "colors": {"keyword": "#ff0000"}})
    palette = build_palette(theme)
    assert len(palette) == 15
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


def test_isolated_language_feature_mapping_is_readable():
    js = parse_language({"name": "JavaScript", "keywords": ["if"]}, "js")
    css = parse_language({"name": "CSS", "keywords": ["color"]}, "css")
    assert isolated_language_features(["js", "css"], [js, css]) == {
        "js": "js",
        "css": "css",
    }
    assert len(set(ISOLATED_LANGUAGE_FEATURES.values())) == 20
    for tag in ISOLATED_LANGUAGE_FEATURES.values():
        assert 1 <= len(tag) <= 4

    custom = parse_language({"name": "MyLang", "feature": "myL"}, None)
    assert isolated_language_features([None], [custom]) == {"mylang": "myL"}
    # a custom language needs an explicit feature tag
    with pytest.raises(ValueError, match="feature:"):
        isolated_language_features([None], [Language(name="NoFeature")])
    # feature tags are limited to 4 characters by OpenType
    with pytest.raises(ValueError, match="1-4"):
        isolated_language_features(
            [None], [Language(name="X", feature="toolong")]
        )
    # tags must be distinct across the selection
    a = parse_language({"name": "A", "feature": "dup"}, None)
    b = parse_language({"name": "B", "feature": "dup"}, None)
    with pytest.raises(ValueError, match="distinct"):
        isolated_language_features([None, None], [a, b])


def test_generate_isolated_features_namespaces_one_feature_per_language():
    js = parse_language(
        {"name": "JavaScript", "keywords": ["if"], "symbols": {"symbol": ";"}, "numbers": False},
        "js",
    )
    css = parse_language(
        {"name": "CSS", "keywords": ["else"], "symbols": {"symbol": ";"}, "numbers": False},
        "css",
    )
    fea, mapping = generate_isolated_features([js, css], ["js", "css"], fake_glyphs())

    assert mapping == {"js": "js", "css": "css"}
    assert "feature calt {" not in fea
    assert "feature js {" in fea
    assert "feature css {" in fea
    assert "lookup js_Words_Kw {" in fea
    assert "lookup css_Words_Kw {" in fea

    js_feature = fea.split("feature js {")[1].split("} js;")[0]
    css_feature = fea.split("feature css {")[1].split("} css;")[0]
    assert "lookup js_Words_Kw;" in js_feature
    assert "css_" not in js_feature
    assert "lookup css_Words_Kw;" in css_feature
    assert "js_" not in css_feature


def test_generate_isolated_features_rejects_mismatched_languages():
    lang = Language(name="JavaScript", keywords=["if"], id="js")
    with pytest.raises(ValueError, match="same length"):
        generate_isolated_features([lang], ["js", "css"], fake_glyphs())


def test_css_language_features_selects_one_feature():
    css = css_language_features({"js": "js", "python": "py"})
    assert '.language-js {\n  font-feature-settings: "js";' in css
    assert '.language-python {\n  font-feature-settings: "py";' in css
