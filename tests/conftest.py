"""Shared fixtures: build a highlight font once per test session."""

from __future__ import annotations

import pytest
from helpers import BASE_FONT

from syntaxfont.builder import build_highlight_font


@pytest.fixture(scope="session")
def languages():
    from syntaxfont.cli import load_languages

    return load_languages(["js", "css", "html"])


@pytest.fixture(scope="session")
def theme():
    from syntaxfont.cli import load_theme

    return load_theme("default")


@pytest.fixture(scope="session")
def base_font_path():
    return BASE_FONT


@pytest.fixture(scope="session")
def highlight_font(tmp_path_factory, languages, theme):
    """Build a TTF (not woff2) so uharfbuzz can read it."""
    out = tmp_path_factory.mktemp("font") / "highlight.ttf"
    build_highlight_font(BASE_FONT, languages, theme, str(out), flavor=None)
    return str(out)
