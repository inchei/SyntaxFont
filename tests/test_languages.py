"""Every bundled language/theme must parse, and all languages must build."""

from __future__ import annotations

import os

import pytest
import uharfbuzz as hb
import yaml

from syntaxfont.builder import build_highlight_font
from syntaxfont.schema import parse_language, parse_theme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGUAGES = os.path.join(ROOT, "languages")
THEMES = os.path.join(ROOT, "themes")
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


def _names(directory: str) -> list[str]:
    return sorted(f[:-5] for f in os.listdir(directory) if f.endswith(".yaml"))


@pytest.mark.parametrize("name", _names(LANGUAGES))
def test_language_parses(name):
    lang = parse_language(yaml.safe_load(open(os.path.join(LANGUAGES, f"{name}.yaml"))))
    # the file name is the id; `name` is the formal display name
    assert lang.name and lang.name != name  # e.g. js.yaml -> JavaScript


@pytest.mark.parametrize("name", _names(THEMES))
def test_theme_parses(name):
    theme = parse_theme(yaml.safe_load(open(os.path.join(THEMES, f"{name}.yaml"))))
    assert theme.name == name


@pytest.fixture(scope="module")
def all_languages_font(tmp_path_factory):
    from syntaxfont.cli import load_languages, load_theme

    langs = load_languages(_names(LANGUAGES))
    out = tmp_path_factory.mktemp("all") / "all.ttf"
    build_highlight_font(
        BASE_FONT, langs, load_theme("default"), str(out), flavor=None, color_all=False
    )
    return str(out)


def _shape(path: str, text: str) -> list[str]:
    font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"calt": True})
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]


def test_all_languages_shape(all_languages_font):
    # a keyword from a few of the newly added languages
    assert _shape(all_languages_font, "fn") == ["f.alt3", "n.alt3"]  # rust
    assert _shape(all_languages_font, "SELECT")[:3] == ["S.alt3", "E.alt3", "L.alt3"]  # sql
    assert _shape(all_languages_font, "func")[:2] == ["f.alt3", "u.alt3"]  # go
    # prefix overlaps across languages: longer words win, shorter stay guarded
    assert _shape(all_languages_font, "fun") == ["f.alt3", "u.alt3", "n.alt3"]  # kotlin
    assert _shape(all_languages_font, "function")[:3] == ["f.alt3", "u.alt3", "n.alt3"]  # js
    assert _shape(all_languages_font, "gift") == ["g", "i", "f", "t"]
    # a hash comment
    assert all(n.endswith(".alt1") for n in _shape(all_languages_font, "# hi"))


AFTER_PROBES = {
    "function": "X",
    "tag": "X",
    "attr": "X",
    "keyword": "x",
    "builtin": "x",
    "number": "ff",
    "selector": "x",
    "symbol": "x",
    "string": "x",
}


@pytest.fixture(scope="module")
def single_language_fonts(tmp_path_factory):
    """Build one font per language (session-wide cache)."""
    from syntaxfont.cli import load_languages, load_theme

    theme = load_theme("default")
    out = {}
    for name in _names(LANGUAGES):
        path = tmp_path_factory.mktemp("single") / f"{name}.ttf"
        build_highlight_font(
            BASE_FONT, load_languages([name]), theme, str(path), flavor=None
        )
        out[name] = str(path)
    return out


@pytest.mark.parametrize("name", _names(LANGUAGES))
def test_no_dead_rules_within_a_language(name, single_language_fonts):
    """Every declared keyword/builtin/literal must actually color, and every
    after-rule trigger must fire, when the language is built on its own."""
    from syntaxfont.schema import PALETTES

    path = single_language_fonts[name]
    lang = parse_language(yaml.safe_load(open(os.path.join(LANGUAGES, f"{name}.yaml"))))

    def has(text: str, palette: int) -> bool:
        return any(n.endswith(f".alt{palette}") for n in _shape(path, text))

    for word in lang.keywords:
        assert has(word, PALETTES["keyword"]), f"{name}: keyword {word!r} not colored"
    for word in lang.builtins:
        assert has(word, PALETTES["builtin"]), f"{name}: builtin {word!r} not colored"
    for word in lang.literals:
        assert has(word, PALETTES["literal"]), f"{name}: literal {word!r} not colored"
    for rule in lang.after_rules:
        # pick a probe char that is actually in the rule's char class
        if "a" in rule.chars and "z" in rule.chars:
            probe = AFTER_PROBES.get(rule.palette, "X")
        else:
            probe = next((c for c in rule.chars if c.isalpha()), None) or (
                rule.chars[0] if rule.chars else "X"
            )
        for seq in rule.after:
            text = "".join(seq) + probe
            assert has(text, PALETTES[rule.palette]), (
                f"{name}: after-rule {text!r} ({rule.palette}) not colored"
            )
    for rule in lang.word_rules:
        # a word before the first terminator must be colored
        text = "name" + rule.terminators[0]
        assert has(text, PALETTES[rule.palette]), (
            f"{name}: word-rule {text!r} ({rule.palette}) not colored"
        )
