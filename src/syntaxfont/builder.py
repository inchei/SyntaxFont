"""Build the highlight font: duplicate glyphs as colored alternates, write
COLR/CPAL tables, and inject generated calt rules via feaLib."""

from __future__ import annotations

import re

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.otTables import LayerRecord
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.t2CharStringPen import T2CharStringPen

from .calt_gen import _ALL, FSM_PALETTES, generate_features
from .palette import build_palette
from .schema import NUM_PALETTES, Language, Theme

# Glyph names must be plain tokens in a feature file: `#` starts a comment,
# and `@ $ % & = ? |` etc. are not allowed. Anything else can't be referenced.
_FEA_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _fea_safe(name: str) -> bool:
    return bool(_FEA_SAFE.match(name))


def colorable_characters(
    font: TTFont, color_all: bool = False, extra_chars: str = ""
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (base, extra) char -> glyph-name maps.

    ``base`` chars are colorable in every palette; ``extra`` chars (e.g. CJK)
    are only colorable inside comments/strings, so they only get alternates for
    the FSM palettes. ``color_all`` pulls in every character the font maps;
    ``extra_chars`` adds specific characters. Characters whose glyph name cannot
    appear in a feature file (e.g. `periodcentered#1`) are skipped."""
    cmap = font.getBestCmap()
    base = {
        ch: cmap[ord(ch)]
        for ch in _ALL
        if ord(ch) in cmap and _fea_safe(cmap[ord(ch)])
    }
    candidates = "".join(chr(cp) for cp in cmap) if color_all else extra_chars
    extra = {}
    for ch in dict.fromkeys(candidates):
        name = cmap.get(ord(ch))
        if name is not None and ch not in base and _fea_safe(name):
            extra[ch] = name
    return base, extra


def _glyf_adder(font: TTFont):
    glyf = font["glyf"]
    hmtx = font["hmtx"]

    def add(name: str, width: int, lsb: int) -> None:
        if name in glyf.glyphs:
            return
        glyph = Glyph()
        glyph.numberOfContours = 0
        glyf[name] = glyph
        hmtx[name] = (width, lsb)

    return add


def _cff_adder(font: TTFont):
    """Return a function that appends an empty glyph to a CFF/CFF2 font."""
    is_cff2 = "CFF2" in font
    cff = font["CFF2"].cff if is_cff2 else font["CFF "].cff
    top = cff.topDictIndex[0] if is_cff2 else cff[cff.fontNames[0]]
    charstrings = top.CharStrings
    private = None if is_cff2 else getattr(top, "Private", None)
    charset = getattr(top, "charset", None)
    hmtx = font["hmtx"]
    order = font.getGlyphOrder()

    # turn the indexed mapping (name -> index) into a plain name -> charstring
    # mapping so new entries can be appended
    if getattr(charstrings, "charStringsAreIndexed", 0):
        charstrings.charStrings = {
            name: charstrings.charStringsIndex[idx]
            for name, idx in charstrings.charStrings.items()
        }
        charstrings.charStringsAreIndexed = 0

    def add(name: str, width: int, lsb: int) -> None:
        pen = T2CharStringPen(width, None, CFF2=is_cff2)
        charstrings.charStrings[name] = pen.getCharString(
            private=private, globalSubrs=charstrings.globalSubrs
        )
        if charset is not None:
            charset.append(name)  # for CFF the charset *is* the glyph order
        if name not in order:
            order.append(name)
        hmtx[name] = (width, lsb)

    return add


def duplicate_alternates(
    font: TTFont, base: dict[str, str], extra: dict[str, str] | None = None
) -> None:
    """Create empty `.altN` glyphs for every colorable character.

    Alternates carry no outline: the painted shape comes from the COLR layer
    pointing at the base glyph, which keeps the file small. ``base`` chars get
    an alternate in every palette; ``extra`` chars (CJK, ...) only get the FSM
    palettes, since they are only colored inside comments/strings. Works for
    TrueType (glyf), CFF and CFF2 outlines."""
    if "glyf" in font:
        add = _glyf_adder(font)
    elif "CFF " in font or "CFF2" in font:
        add = _cff_adder(font)
    else:
        raise ValueError(
            "unsupported base font: no glyf, CFF or CFF2 outline table"
        )

    hmtx = font["hmtx"]

    def emit(chars: dict[str, str], palettes) -> None:
        # several codepoints can share one glyph, so dedupe by glyph name
        for base_name in dict.fromkeys(chars.values()):
            width, lsb = hmtx[base_name]
            for p in palettes:
                add(f"{base_name}.alt{p}", width, lsb)

    emit(base, range(1, NUM_PALETTES))
    emit(extra or {}, sorted(FSM_PALETTES))


def write_color_tables(
    font: TTFont,
    base: dict[str, str],
    theme: Theme,
    extra: dict[str, str] | None = None,
) -> None:
    palette = build_palette(theme)
    cpal = newTable("CPAL")
    cpal.version = 0
    cpal.numPaletteEntries = NUM_PALETTES
    cpal.palettes = [palette]
    cpal.colorRecordIndices = [0]
    font["CPAL"] = cpal

    color_layers = {}

    def emit(chars: dict[str, str], palettes) -> None:
        for base_name in dict.fromkeys(chars.values()):
            for p in palettes:
                layer = LayerRecord()
                layer.name = base_name
                layer.colorID = p
                color_layers[f"{base_name}.alt{p}"] = [layer]

    emit(base, range(1, NUM_PALETTES))
    emit(extra or {}, sorted(FSM_PALETTES))

    colr = newTable("COLR")
    colr.version = 0
    colr.ColorLayers = color_layers
    font["COLR"] = colr


def build_highlight_font(
    base_font_path: str,
    languages: list[Language],
    theme: Theme,
    out_path: str,
    flavor: str | None = "woff2",
    emit_fea: str | None = None,
    color_all: bool = True,
    extra_chars: str = "",
) -> TTFont:
    font = TTFont(base_font_path)
    base, extra = colorable_characters(font, color_all, extra_chars)
    glyphs = {**base, **extra}

    duplicate_alternates(font, base, extra)
    write_color_tables(font, base, theme, extra)

    fea = generate_features(languages, glyphs, base)
    if emit_fea:
        with open(emit_fea, "w") as f:
            f.write(fea)

    if "GSUB" in font:
        del font["GSUB"]
    addOpenTypeFeaturesFromString(font, fea)

    # set unconditionally: a woff2 input would otherwise keep its flavor.
    # only woff/woff2 are real flavors; "ttf"/"otf"/None all mean raw sfnt.
    font.flavor = flavor if flavor in ("woff", "woff2") else None
    font.save(out_path)
    return font
