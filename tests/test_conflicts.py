"""Cross-language rule conflict detection."""

from __future__ import annotations

from syntaxfont.cli import load_languages
from syntaxfont.conflicts import detect_conflicts


def test_no_conflict_within_one_language():
    assert detect_conflicts(load_languages(["js"])) == []


def test_hash_comment_vs_preprocessor():
    # python uses `#` for comments, C for preprocessor directives
    warnings = detect_conflicts(load_languages(["python", "c"]))
    assert any("#" in w for w in warnings)


def test_word_category_conflict():
    from syntaxfont.schema import Language

    a = Language(name="A", keywords=["foo"])
    b = Language(name="B", builtins=["foo"])
    warnings = detect_conflicts([a, b])
    assert any("foo" in w for w in warnings)


def test_symbol_category_conflict():
    from syntaxfont.schema import Language

    a = Language(name="A", symbols={"symbol": "="})
    b = Language(name="B", symbols={"value": "="})
    warnings = detect_conflicts([a, b])
    assert any("=" in w for w in warnings)
