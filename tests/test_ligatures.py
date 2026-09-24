"""The base font's GSUB is replaced, so its ligature/alternate features are gone.

Programming-ligature fonts (Fira Code, JetBrains Mono, ...) keep their
ligatures in GSUB (`liga`/`clig`/`dlig`/`rlig`/`calt`). SyntaxFont replaces the
whole GSUB with its generated `calt`, so those features are intentionally
dropped: the component characters are shown individually and colored per
character.
"""

from __future__ import annotations

import os

from syntaxfont.builder import build_highlight_font

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")


def _add_ligature_feature(path: str) -> str:
    """Copy the base font with a `liga` feature added.

    The stock JetBrains Mono build has no ligatures, so add a trivial `liga`
    substitution to stand in for a programming-ligature font.
    """
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.ttLib import TTFont

    font = TTFont(BASE_FONT)
    addOpenTypeFeaturesFromString(font, "feature liga { sub f by i; } liga;", tables=["GSUB"])
    font.save(path)
    return path


def _gsub_features(path: str) -> set[str]:
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    if "GSUB" not in font:
        return set()
    return {fr.FeatureTag for fr in font["GSUB"].table.FeatureList.FeatureRecord}


def test_ligature_font_builds_but_original_gsub_is_replaced(tmp_path, languages, theme):
    base = _add_ligature_feature(str(tmp_path / "liga.ttf"))
    assert "liga" in _gsub_features(base)

    out = tmp_path / "hl.ttf"
    build_highlight_font(base, languages, theme, str(out), flavor=None)

    features = _gsub_features(str(out))
    assert "liga" not in features  # original ligatures dropped
    assert features == {"calt"}  # only the generated highlighting remains
