"""Shared fixtures: build a highlight font once per test session."""

from __future__ import annotations

import os

import pytest

from syntaxfont.builder import build_highlight_font

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


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
