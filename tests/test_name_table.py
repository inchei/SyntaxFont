"""Name table synthesis is fully automatic: family is the base family with
" Syntax" appended, unique/full/PS names keep the base text with the same
suffix, and records the base lacks are never created."""

from __future__ import annotations

from fontTools.ttLib import TTFont
from helpers import BASE_FONT

from syntaxfont.builder import build_highlight_font

FAMILY = "JetBrains Mono Syntax"


def _build(path, tmp_path, languages, theme):
    out = tmp_path / "hl.ttf"
    build_highlight_font(path, languages, theme, str(out), flavor=None)
    return TTFont(str(out))


def test_derived_names(tmp_path, languages, theme):
    font = _build(BASE_FONT, tmp_path, languages, theme)
    nt = font["name"]
    assert nt.getDebugName(1) == FAMILY
    assert nt.getDebugName(2) == "Regular"
    assert nt.getDebugName(3) == "2.305;JB;JetBrainsMono-Regular Syntax"
    assert nt.getDebugName(4) == "JetBrains Mono Regular Syntax"
    assert nt.getDebugName(6) == "JetBrainsMono-RegularSyntax"
    assert nt.getDebugName(5) == "Version 1.000"
    assert "COLR" in font and "GSUB" in font


def test_missing_records_not_created(tmp_path, languages, theme):
    font = _build(BASE_FONT, tmp_path, languages, theme)
    ids = {rec.nameID for rec in font["name"].names}
    assert not (ids & {15, 16, 17, 18, 20, 21, 22, 25})


def test_existing_typo_wws_suffixed(tmp_path, languages, theme):
    from fontTools.ttLib.tables._n_a_m_e import NameRecord

    path = str(tmp_path / "typo.ttf")
    base = TTFont(BASE_FONT)
    for nid, text in (
        (16, "JetBrains Mono"),
        (17, "Regular"),
        (21, "JetBrains Mono"),
        (22, "Regular"),
    ):
        nr = NameRecord()
        nr.nameID, nr.platformID, nr.platEncID, nr.langID = nid, 3, 1, 0x409
        nr.string = text.encode("utf-16-be")
        base["name"].names.append(nr)
    base.save(path)
    nt = _build(path, tmp_path, languages, theme)["name"]
    assert nt.getDebugName(16) == "JetBrains Mono Syntax"
    assert nt.getDebugName(17) == "Regular"
    assert nt.getDebugName(21) == "JetBrains Mono Syntax"
    assert nt.getDebugName(22) == "Regular"


def test_attribution_single_newline(tmp_path, languages, theme):
    font = _build(BASE_FONT, tmp_path, languages, theme)
    nt = font["name"]
    for nid in (0, 13, 8):
        text = nt.getDebugName(nid)
        assert text.startswith("Synthesized with SyntaxFont ("), nid
        assert "\n\n" not in text
    assert "JetBrains" in nt.getDebugName(0)
    assert "SIL Open Font License" in nt.getDebugName(13)


def _mac_records(font, nid):
    return [
        rec
        for rec in font["name"].names
        if rec.nameID == nid and (rec.platformID, rec.platEncID, rec.langID) == (1, 0, 0)
    ]


def test_no_mac_in_base_means_no_mac_out(tmp_path, languages, theme):
    font = _build(BASE_FONT, tmp_path, languages, theme)
    assert _mac_records(font, 1) == []
    assert font["name"].getDebugName(1) == FAMILY


def _base_with_mac_record(tmp_path):
    from fontTools.ttLib.tables._n_a_m_e import NameRecord

    path = str(tmp_path / "macbase.ttf")
    font = TTFont(BASE_FONT)
    nr = NameRecord()
    nr.nameID, nr.platformID, nr.platEncID, nr.langID = 1, 1, 0, 0
    nr.string = "OldMac".encode("mac_roman")
    font["name"].names.append(nr)
    font.save(path)
    return path


def test_existing_mac_record_updated(tmp_path, languages, theme):
    font = _build(_base_with_mac_record(tmp_path), tmp_path, languages, theme)
    macs = _mac_records(font, 1)
    assert len(macs) == 1
    assert macs[0].toUnicode() == FAMILY


def test_cli_default_family():
    from syntaxfont.cli import default_family

    assert default_family(BASE_FONT) == FAMILY


def test_cff_topdict_only_existing_attrs(tmp_path, languages, theme):
    from test_cff import make_cff_font

    base = make_cff_font(str(tmp_path / "base.otf"))
    font = _build(base, tmp_path, languages, theme)
    assert font["name"].getDebugName(1) == "TestCFF Syntax"
    assert font["name"].getDebugName(4) is None
    top = font["CFF "].cff[font["CFF "].cff.fontNames[0]]
    assert top.FullName == "Test CFF Syntax"
    assert getattr(top, "FamilyName", None) is None
