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
    assert out == ["quotedbl.alt2", "a.alt2", "b.alt2", "quotedbl.alt2", "semicolon.alt10", "x"]


def test_string_space_inside(highlight_font):
    out = shape(highlight_font, '"a b"')
    assert "space.alt2" in out


def test_html_tag(highlight_font):
    out = shape(highlight_font, "<div>")
    assert out[1:4] == ["d.alt7", "i.alt7", "v.alt7"]


def test_css_selector(highlight_font):
    # like the original, a selector only colors when a terminator follows
    out = shape(highlight_font, ".foo {")
    assert out[0:4] == ["period.alt8", "f.alt8", "o.alt8", "o.alt8"]
    assert shape(highlight_font, ".foo") == ["period", "f", "o", "o"]


def test_number_and_symbol(highlight_font):
    # digits -> number palette, `=` -> value palette (as in the original)
    out = shape(highlight_font, "=1")
    assert out == ["equal.alt12", "one.alt11"]


def test_punctuation_uses_category_colors(highlight_font):
    # each punctuation char has a fixed category color: {} keyword, ()[]@
    # function, =+%~<>! value (operators share one slot), &|:;$"';/?*^ symbol
    keyword = ["{", "}"]
    function = ["(", ")", "[", "]", "@"]
    value = ["=", "+", "%", "~", "<", ">", "!", "-"]
    symbol = ["&", "|", ":", "$", ";", "/", "?", "*", "^"]
    for s in keyword:
        assert shape(highlight_font, s)[0].endswith(".alt3"), s
    for s in function:
        assert shape(highlight_font, s)[0].endswith(".alt6"), s
    for s in value:
        assert shape(highlight_font, s)[0].endswith(".alt12"), s
    for s in symbol:
        assert shape(highlight_font, s)[0].endswith(".alt10"), s
    for s in [".", ",", "#", "_", "`"]:
        assert ".alt" not in shape(highlight_font, s)[0], s


def test_decorators(highlight_font):
    # `@Name` decorator/annotation -> function color
    out = shape(highlight_font, "@Component")
    assert out[1] == "C.alt6" and out[-1] == "t.alt6"


def test_css_custom_property(highlight_font):
    # `--name` -> attr color
    out = shape(highlight_font, "--main")
    assert out[2] == "m.alt9" and out[-1] == "n.alt9"


def test_css_function_inside_value(highlight_font):
    # `var(--radius)` inside a declaration: function name and custom prop are
    # colored even though the value FSM covers the whole declaration
    out = shape(highlight_font, "color: var(--radius);")
    assert out[7:10] == ["v.alt3", "a.alt3", "r.alt3"]  # `var` (JS keyword here)
    assert out[10] == "parenleft.alt6"  # function call
    assert out[11:13] == ["hyphen.alt12", "hyphen.alt12"]  # `--` is an operator
    assert out[13] == "r.alt9" and out[-3] == "s.alt9"  # custom prop is attr


def test_css_hex_color(highlight_font):
    # `#rrggbb` -> number color, even inside a declaration
    out = shape(highlight_font, "color: #d73a49;")
    assert out[7] == "numbersign.alt12"
    assert all(n.endswith(".alt11") for n in out[8:14])
    # a bare id selector stays plain
    out = shape(highlight_font, "#id")
    assert not any(".alt" in n for n in out[1:])


def test_css_value_does_not_cross_paren(highlight_font):
    # the `:` value FSM ends at `)`, so an at-rule prelude `@media (…)` does not
    # bleed the value color onto `) {`
    text = "@media (prefers-color-scheme: dark) {"
    out = shape(highlight_font, text)
    # `dark` is the media-feature value (value color), but `)` and `{` are not
    assert out[text.index(")")] == "parenright.alt6"  # `)`
    assert out[text.index("{")] == "braceleft.alt3"  # `{`


def test_html_entity(highlight_font):
    # `&amp;` -> entity name gets string color
    out = shape(highlight_font, "&amp;")
    assert out[1] == "a.alt2" and out[-2] == "p.alt2"


def test_this_super_are_builtins(highlight_font):
    # like the original font, this/super take the builtin color, not keyword
    assert shape(highlight_font, "this") == ["t.alt4", "h.alt4", "i.alt4", "s.alt4"]
    assert shape(highlight_font, "super(")[:4] == ["s.alt4", "u.alt4", "p.alt4", "e.alt4"]


def test_css_line_comment(highlight_font):
    out = shape(highlight_font, "// hi")
    assert all(n.endswith(".alt1") for n in out)


def test_css_selectors(highlight_font):
    assert shape(highlight_font, "div{")[:3] == ["d.alt8", "i.alt8", "v.alt8"]
    out = shape(highlight_font, "div > p")
    assert out[:3] == ["d.alt8", "i.alt8", "v.alt8"]
    assert out[4] == "greater.alt12"


def test_css_values(highlight_font):
    out = shape(highlight_font, "color: red;")
    assert out[:5] == ["c.alt9", "o.alt9", "l.alt9", "o.alt9", "r.alt9"]
    assert out[5] == "colon.alt10"
    assert out[7:10] == ["r.alt12", "e.alt12", "d.alt12"]
    assert out[10] == "semicolon.alt10"


def test_apostrophe_does_not_start_string(highlight_font):
    out = shape(highlight_font, "don't")
    assert out == ["d", "o", "n", "quotesingle.alt10", "t"]


def test_escaped_quote_does_not_end_string(highlight_font):
    # `'test\'fdsf'` — the escaped quote and the rest stay string-colored
    out = shape(highlight_font, "'test\\'fdsf'")
    assert out[0] == "quotesingle.alt2"  # opening quote is string-colored
    assert out[5] == "backslash.alt13"  # escape introducer
    assert out[6] == "quotesingle.alt13"  # escaped quote is escape-colored
    assert out[7:11] == ["f.alt2", "d.alt2", "s.alt2", "f.alt2"]
    assert out[11] == "quotesingle.alt2"
    # `"a\"b"` likewise
    out = shape(highlight_font, '"a\\"b"')
    assert out[3] == "quotedbl.alt13" and out[4] == "b.alt2"


def test_escape_sequences(highlight_font):
    # `\n`, `\t`, ... are colored with the escape palette, distinct from the string
    out = shape(highlight_font, "'a\\nb'")
    assert out[2] == "backslash.alt13" and out[3] == "n.alt13"
    assert out[1] == "a.alt2" and out[4] == "b.alt2"
    # `\\` is an escaped backslash and must not escape the following char
    out = shape(highlight_font, "'a\\\\b'")
    assert out[2] == "backslash.alt13" and out[3] == "backslash.esc"
    assert out[4] == "b.alt2"


def test_format_specifiers(highlight_font):
    # printf-style `%...` inside a string gets the format palette
    out = shape(highlight_font, '"%s (%zu)"')
    assert out[1] == "percent.alt14" and out[2] == "s.alt14"
    assert out[5] == "percent.alt14"
    assert out[6] == "z.alt14" and out[7] == "u.alt14"
    # a bare `%` (not followed by a specifier) stays string-colored
    out = shape(highlight_font, '"100% sure"')
    assert out[4] == "percent.alt2"


def test_empty_string_does_not_leak(highlight_font):
    assert shape(highlight_font, "'';x") == [
        "quotesingle.alt2",
        "quotesingle.alt2",
        "semicolon.alt10",
        "x",
    ]


def test_template_literal(highlight_font):
    # literal text is string-colored; `${...}` is paused out as code and the
    # string resumes after the closing `}`
    out = shape(highlight_font, "`Hello, ${name}!`")
    # opening backtick, Hello, (string), ${ (symbol/keyword), name (plain),
    # } code, ! string, closing backtick string
    assert out[0] == "grave.alt2"
    assert all(n.endswith(".alt2") for n in out[1:8])  # "Hello, "
    assert out[8] == "dollar.alt10"
    assert out[9] == "braceleft.alt3"
    assert out[10:14] == ["n", "a", "m", "e"]  # code, not string
    assert out[14] == "braceright.alt3"
    assert out[15].endswith(".alt2")  # "!" string again
    assert out[16].endswith(".alt2")  # closing backtick string


def test_template_multiple_interpolations(highlight_font):
    out = shape(highlight_font, "`a ${x} b ${y.z} c`")
    # literal text stays string between interpolations
    assert out[1] == "a.alt2" and out[2] == "space.alt2"
    assert out[3] == "dollar.alt10" and out[4] == "braceleft.alt3"
    assert out[5] == "x"  # code
    assert out[6] == "braceright.alt3"
    assert out[7] == "space.alt2" and out[8] == "b.alt2"  # literal text again


def test_color_tables_present(highlight_font):
    from fontTools.ttLib import TTFont

    font = TTFont(highlight_font)
    assert "COLR" in font and "CPAL" in font
    assert font["CPAL"].numPaletteEntries == 15


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


def test_comment_inside_string_is_not_recolored(highlight_font):
    # `//` inside a JS string must stay string-colored (e.g. URLs)
    out = shape(highlight_font, '"http://x.com"')
    assert all(n.endswith(f".alt{STRING}") for n in out)


def test_string_inside_comment_is_not_recolored(highlight_font):
    out = shape(highlight_font, '// "quoted"')
    assert all(n.endswith(f".alt{COMMENT}") for n in out)


@pytest.fixture(scope="session")
def swift_font(tmp_path_factory, base_font_path, theme):
    from syntaxfont.builder import build_highlight_font
    from syntaxfont.cli import load_languages

    out = tmp_path_factory.mktemp("swift") / "swift.ttf"
    build_highlight_font(
        base_font_path, load_languages(["swift"]), theme, str(out), flavor=None
    )
    return str(out)


@pytest.fixture(scope="session")
def ruby_font(tmp_path_factory, base_font_path, theme):
    from syntaxfont.builder import build_highlight_font
    from syntaxfont.cli import load_languages

    out = tmp_path_factory.mktemp("ruby") / "ruby.ttf"
    build_highlight_font(
        base_font_path, load_languages(["ruby"]), theme, str(out), flavor=None
    )
    return str(out)


def test_swift_string_interpolation(swift_font):
    # `\(value)` pauses the string, `value` is code, the string resumes
    out = shape(swift_font, 'print("\\(value)")')
    assert out[6] == f"quotedbl.alt{STRING}"  # opening quote
    assert out[7] == "backslash"  # `\(` is not string-colored
    assert out[8] == f"parenleft.alt{FUNCTION}"
    assert out[9:14] == ["v", "a", "l", "u", "e"]  # code, not string
    assert out[14] == f"parenright.alt{FUNCTION}"
    assert out[15] == f"quotedbl.alt{STRING}"  # string resumes


def test_ruby_string_interpolation(ruby_font):
    # `#{name}` pauses the string, `name` is code, the string resumes
    out = shape(ruby_font, '"hi #{name}!"')
    assert out[0] == f"quotedbl.alt{STRING}"
    assert out[4] == "numbersign"  # `#{` is not string-colored
    assert out[5] == f"braceleft.alt{KEYWORD}"
    assert out[6:10] == ["n", "a", "m", "e"]  # code, not string
    assert out[10] == f"braceright.alt{KEYWORD}"
    assert out[11] == f"exclam.alt{STRING}"  # string resumes


def test_ruby_single_char_builtin_does_not_match_inside_word(ruby_font):
    # `p` is a builtin; it must be guarded by word boundaries so it does not
    # color part of `empty` (the `.method` rule colors `empty` as a function,
    # but never as the builtin `p`)
    out = shape(ruby_font, "empty")
    assert not any(n.endswith(f".alt{BUILTIN}") for n in out)
    # ...but a standalone `p` is still a builtin
    assert shape(ruby_font, "p") == [f"p.alt{BUILTIN}"]


def test_ruby_method_call_after_dot(ruby_font):
    # `.method` -> function (Shiki's entity.name.function)
    out = shape(ruby_font, "obj.method")
    assert all(n.endswith(f".alt{FUNCTION}") for n in out[4:])
    # a float is not a method call
    out = shape(ruby_font, "1.5")
    assert out[-1] == f"five.alt{NUMBER}"


@pytest.fixture(scope="session")
def sql_font(tmp_path_factory, base_font_path, theme):
    from syntaxfont.builder import build_highlight_font
    from syntaxfont.cli import load_languages

    out = tmp_path_factory.mktemp("sql") / "sql.ttf"
    build_highlight_font(
        base_font_path, load_languages(["sql"]), theme, str(out), flavor=None
    )
    return str(out)


def test_sql_is_case_insensitive(sql_font):
    # SQL keywords match in upper and lower case (the generator is
    # case-sensitive, so the language expands its word lists)
    for word in ("select", "SELECT"):
        assert all(n.endswith(f".alt{KEYWORD}") for n in shape(sql_font, word)), word
    # a new type name is recognized too
    assert all(n.endswith(f".alt{BUILTIN}") for n in shape(sql_font, "varchar2"))


@pytest.fixture(scope="session")
def yaml_font(tmp_path_factory, base_font_path, theme):
    from syntaxfont.builder import build_highlight_font
    from syntaxfont.cli import load_languages

    out = tmp_path_factory.mktemp("yaml") / "yaml.ttf"
    build_highlight_font(
        base_font_path, load_languages(["yaml"]), theme, str(out), flavor=None
    )
    return str(out)


def test_yaml_plain_scalar_and_list_values(yaml_font):
    VALUE = 12
    # a scalar after `key: `
    out = shape(yaml_font, "key: value")
    assert all(n.endswith(f".alt{VALUE}") for n in out[5:])
    # a list item after `- `
    out = shape(yaml_font, "- item")
    assert all(n.endswith(f".alt{VALUE}") for n in out[2:])
