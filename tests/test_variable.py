"""Base-font table preservation: GPOS/GDEF and variable-font tables.

Building replaces the font's ``GSUB`` (with the generated ``calt``) but must
keep everything else. Two regressions are guarded here:

* feaLib's ``addOpenTypeFeaturesFromString`` rebuilds GDEF/GPOS too and drops
  the base font's kerning/mark tables unless restricted to GSUB;
* adding alternate glyphs to a variable font must keep ``gvar`` consistent
  (one variation entry per glyph) or the table becomes invalid.
"""

from __future__ import annotations

import pytest
from helpers import BASE_FONT
from helpers import shape_font as _shape

from syntaxfont.builder import build_highlight_font


def test_static_font_preserves_gpos_gdef(tmp_path, languages, theme):
    from fontTools.ttLib import TTFont

    out = tmp_path / "hl.ttf"
    build_highlight_font(BASE_FONT, languages, theme, str(out), flavor=None)
    font = TTFont(str(out))
    assert "GPOS" in font and "GDEF" in font  # kerning / mark positioning kept
    assert "COLR" in font and "GSUB" in font
    assert _shape(str(out), "if") == ["i.alt3", "f.alt3"]


def make_variable_font(path: str) -> str:
    """A minimal TrueType variable font (fvar + empty gvar) from the base font."""
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
    from fontTools.ttLib.tables._n_a_m_e import NameRecord

    font = TTFont(BASE_FONT)
    fvar = newTable("fvar")
    axis = Axis()
    axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue = "wght", 100, 400, 900
    axis.axisNameID = 256
    fvar.axes = [axis]
    inst = NamedInstance()
    inst.coordinates, inst.subfamilyNameID, inst.postscriptNameID = {"wght": 400}, 2, 0xFFFF
    fvar.instances = [inst]
    font["fvar"] = fvar
    nr = NameRecord()
    nr.nameID, nr.platformID, nr.platEncID, nr.langID = 256, 3, 1, 0x409
    nr.string = "Weight".encode("utf-16-be")
    font["name"].names.append(nr)

    gvar = newTable("gvar")
    gvar.version, gvar.reserved, gvar.axisCount = 1, 0, 1
    gvar.sharedTupleCount, gvar.offsetToSharedTuples = 0, 0
    gvar.flags, gvar.offsetToGlyphVariationData = 0, 0
    gvar.glyphCount = len(font.getGlyphOrder())
    gvar.variations = {}
    font["gvar"] = gvar
    font.save(path)
    return path


@pytest.fixture(scope="module")
def variable_font(tmp_path_factory) -> str:
    return make_variable_font(str(tmp_path_factory.mktemp("var") / "base.ttf"))


def test_variable_font_keeps_axes_and_valid_gvar(variable_font, tmp_path, languages, theme):
    from fontTools.ttLib import TTFont

    out = tmp_path / "hl.ttf"
    build_highlight_font(variable_font, languages, theme, str(out), flavor=None)
    font = TTFont(str(out))

    # axes/instances and positioning survive
    assert "fvar" in font and "gvar" in font
    assert "GPOS" in font and "GDEF" in font
    # gvar must stay valid: one entry per glyph after the alternates were added
    assert font["gvar"].glyphCount == font["maxp"].numGlyphs
    # ...and the generated highlighting still applies
    assert _shape(str(out), "if") == ["i.alt3", "f.alt3"]
