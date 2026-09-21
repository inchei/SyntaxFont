"""End-to-end shaping tests: assert the calt rules color the right glyphs.

Colored glyph alternates are named `<base>.alt<palette index>`; palette indices
come from syntaxfont.schema.PALETTES.
"""

from __future__ import annotations

import pytest
import uharfbuzz as hb

KEYWORD = 3
BUILTIN = 4
LITERAL = 5
FUNCTION = 6
TAG = 7
SELECTOR = 8
ATTR = 9
SYMBOL = 10
NUMBER = 11
COMMENT = 1
STRING = 2


def shape(font_path: str, text: str) -> list[str]:
    blob = hb.Blob.from_file_path(font_path)
    font = hb.Font(hb.Face(blob))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True})
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]


def alts(names: list[str], palette: int) -> bool:
    return all(n.endswith(f".alt{palette}") for n in names)


def test_keyword(highlight_font):
    assert shape(highlight_font, "if") == ["i.alt3", "f.alt3"]


def test_keyword_word_boundaries(highlight_font):
    assert shape(highlight_font, "gift") == ["g", "i", "f", "t"]
    assert shape(highlight_font, "ifx")[:2] == ["i", "f"]
    assert shape(highlight_font, "xif")[:2] == ["x", "i"]
    # before a paren is still a keyword, not a function
    assert shape(highlight_font, "if(")[:2] == ["i.alt3", "f.alt3"]


def test_literal_and_builtin(highlight_font):
    assert alts(shape(highlight_font, "true"), LITERAL)
    assert shape(highlight_font, "console")[:1] == ["c.alt4"]


def test_function_name(highlight_font):
    out = shape(highlight_font, "foo(")
    assert out[:3] == ["f.alt6", "o.alt6", "o.alt6"]
    # words not followed by a paren stay plain
    assert shape(highlight_font, "abc") == ["a", "b", "c"]


def test_line_comment(highlight_font):
    out = shape(highlight_font, "// hi")
    assert all(n.endswith(".alt1") for n in out)


def test_block_comment_stops(highlight_font):
    out = shape(highlight_font, "/* x */ y")
    assert out[-1] == "y" and out[-2] == "space"
    assert all(n.endswith(".alt1") for n in out[:-2])


def test_string_stops(highlight_font):
    out = shape(highlight_font, '"ab";x')
    assert out == ["quotedbl.alt10", "a.alt2", "b.alt2", "quotedbl.alt2", "semicolon.alt10", "x"]


def test_string_space_inside(highlight_font):
    out = shape(highlight_font, '"a b"')
    assert "space.alt2" in out


def test_html_tag(highlight_font):
    out = shape(highlight_font, "<div>")
    assert out[1:4] == ["d.alt7", "i.alt7", "v.alt7"]


def test_css_selector(highlight_font):
    out = shape(highlight_font, ".foo")
    assert out[1:4] == ["f.alt8", "o.alt8", "o.alt8"]


def test_number_and_symbol(highlight_font):
    out = shape(highlight_font, "=1")
    assert out == ["equal.alt10", "one.alt11"]


def test_color_tables_present(highlight_font):
    from fontTools.ttLib import TTFont

    font = TTFont(highlight_font)
    assert "COLR" in font and "CPAL" in font
    assert font["CPAL"].numPaletteEntries == 12


@pytest.fixture(scope="session")
def extra_font(tmp_path_factory, base_font_path, languages, theme):
    from syntaxfont.builder import build_highlight_font

    out = tmp_path_factory.mktemp("extra") / "extra.ttf"
    build_highlight_font(
        base_font_path, languages, theme, str(out), flavor=None, extra_chars="é→λ"
    )
    return str(out)


@pytest.fixture(scope="session")
def ascii_font(tmp_path_factory, base_font_path, languages, theme):
    from syntaxfont.builder import build_highlight_font

    out = tmp_path_factory.mktemp("ascii") / "ascii.ttf"
    build_highlight_font(
        base_font_path, languages, theme, str(out), flavor=None, color_all=False
    )
    return str(out)


def test_color_all_is_the_default(highlight_font):
    # every mapped char is colorable inside comments/strings by default
    out = shape(highlight_font, "// é→ x")
    assert all(n.endswith(".alt1") for n in out)


def test_ascii_only_mode(ascii_font):
    # with color_all=False the comment chain stops at the first non-ASCII char
    out = shape(ascii_font, "// é x")
    assert out[0].endswith(".alt1") and out[1].endswith(".alt1")
    assert out[2].endswith(".alt1")  # space is still colored
    assert out[3] == "eacute"  # ...but é is not, so the chain stops
    assert out[-1] == "x" and not out[-1].endswith(".alt1")


def test_extra_chars_colored_inside_comments(extra_font):
    out = shape(extra_font, "// é→λ x")
    assert all(n.endswith(".alt1") for n in out)
    # base chars (keywords) still work normally
    assert shape(extra_font, "if") == ["i.alt3", "f.alt3"]
