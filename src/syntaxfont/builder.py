"""Build the highlight font: duplicate glyphs as colored alternates, write
COLR/CPAL tables, and inject generated calt rules via feaLib."""

from __future__ import annotations

import copy
import logging
import re

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables.otTables import LayerRecord, SubstLookupRecord
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.t2CharStringPen import T2CharStringPen

from .calt_gen import (
    _ALL,
    FSM_PALETTES,
    REGION_FEATURE_TAG,
    generate_features,
    generate_isolated_features,
)
from .palette import build_palette
from .schema import NUM_PALETTES, Language, Theme, palette_index

# Glyph names must be plain tokens in a feature file: `#` starts a comment,
# and `@ $ % & = ? |` etc. are not allowed. Anything else can't be referenced.
_FEA_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

TOOL_NAME = "SyntaxFont"
TOOL_URL = "https://github.com/inchei/SyntaxFont"

_MANAGED_NAME_IDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 21, 22)
_CARRIED_NAME_IDS = (7, 8, 9, 10, 11, 12, 14)
_DROPPED_NAME_IDS = {15, 18, 20}
_SYNTH_VERSION = "Version 1.000"


def _sanitize_family(name: str) -> str:
    """Family name safe for the name table: no path/FS-forbidden chars."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "SyntaxFont"


def synthesize_name_table(font: TTFont) -> TTFont:
    """Rewrite the name table for the derived highlight font.

    Family is the base family with ``" Syntax"`` appended, style follows the
    base subfamily; unique ID, full and PostScript names keep the base text
    with ``" Syntax"`` appended, version is reset; copyright/license keep the
    base notices prefixed with a synthesis statement, other attribution
    records are carried over. Records the base font lacks are never created.
    """
    if "name" not in font:
        font["name"] = newTable("name")
    nt = font["name"]

    def original_texts(name_id: int) -> list[str]:
        for rec in nt.names:
            if rec.nameID == name_id and (rec.platformID, rec.platEncID, rec.langID) == (3, 1, 0x409):
                try:
                    text = rec.toUnicode()
                except Exception:
                    break
                return [text] if text else []
        text = nt.getDebugName(name_id)
        return [text] if text else []

    def original_notices(name_id: int) -> str:
        return "\n".join([synth, *original_texts(name_id)])

    base_fam = (original_texts(1) + ["SyntaxFont"])[0].strip() or "SyntaxFont"
    fam = _sanitize_family(f"{base_fam} Syntax")
    style = (original_texts(2) + ["Regular"])[0].strip() or "Regular"
    derived_full = f"{fam} {style}"
    derived_ps = (
        re.sub(r"[^A-Za-z0-9_-]", "", derived_full.replace(" ", ""))
        or "SyntaxFont-Regular"
    )
    synth = f"Synthesized with {TOOL_NAME} ({TOOL_URL})"

    cff_tops: list = []
    cff_font_name: str | None = None
    for _tag in ("CFF ", "CFF2"):
        if _tag not in font:
            continue
        _cff = font[_tag].cff
        if _tag == "CFF2":
            cff_tops.extend(_cff.topDictIndex)
        else:
            cff_tops.extend(_cff[name] for name in _cff.fontNames)
            if _cff.fontNames:
                cff_font_name = _cff.fontNames[0]

    def _cff_attr(attr: str) -> str | None:
        for _top in cff_tops:
            val = getattr(_top, attr, None)
            if val:
                return val
        return None

    had = {nid: bool(original_texts(nid)) for nid in _MANAGED_NAME_IDS}
    copyright_notice = original_notices(0)
    license_notice = original_notices(13)
    carried = [
        (nid, original_notices(nid))
        for nid in _CARRIED_NAME_IDS
        if had[nid]
    ]
    orig_full = original_texts(4) or (
        [_cff_attr("FullName")] if _cff_attr("FullName") else []
    )
    full = orig_full[0] + " Syntax" if orig_full else derived_full
    orig_unique = original_texts(3)
    unique = orig_unique[0] + " Syntax" if orig_unique else derived_full
    orig_ps = original_texts(6) or ([cff_font_name] if cff_font_name else [])
    if orig_ps:
        ps = re.sub(r"[^A-Za-z0-9_-]", "", orig_ps[0] + "Syntax") or derived_ps
    else:
        ps = derived_ps
    subfam_full = original_texts(16)
    subfam_wws = original_texts(21)
    entries = [
        (0, copyright_notice),
        (1, fam),
        (2, style),
        (3, unique),
        (4, full),
        (5, _SYNTH_VERSION),
        (6, ps),
        *carried,
        (13, license_notice),
    ]
    if subfam_full:
        entries.append((16, subfam_full[0] + " Syntax"))
    if had[17]:
        entries.append((17, style))
    if subfam_wws:
        entries.append((21, subfam_wws[0] + " Syntax"))
    if had[22]:
        entries.append((22, style))
    for nid, val in entries:
        if nid not in (1, 2) and not had[nid]:
            continue
        nt.setName(val, nid, 3, 1, 0x409)
        if any(
            rec.nameID == nid
            and (rec.platformID, rec.platEncID, rec.langID) == (1, 0, 0)
            for rec in nt.names
        ):
            try:
                val.encode("mac_roman")
            except UnicodeEncodeError:
                nt.names = [
                    rec
                    for rec in nt.names
                    if not (
                        rec.nameID == nid
                        and (rec.platformID, rec.platEncID, rec.langID) == (1, 0, 0)
                    )
                ]
            else:
                nt.setName(val, nid, 1, 0, 0)
    drop_ids = set(_DROPPED_NAME_IDS)
    if "fvar" not in font:
        drop_ids.add(25)
    nt.names = [
        rec
        for rec in nt.names
        if rec.nameID not in drop_ids
        and (
            rec.nameID not in _MANAGED_NAME_IDS
            or (rec.platformID, rec.platEncID, rec.langID) in ((3, 1, 0x409), (1, 0, 0))
        )
    ]

    for top in cff_tops:
        for attr, val in (("FamilyName", fam), ("FullName", full), ("Weight", style)):
            if getattr(top, attr, None) is not None:
                setattr(top, attr, val)
    return font


class _AmbiguousIgnoreFilter(logging.Filter):
    """Drop feaLib's 'Ambiguous "ignore sub"' messages.

    Our hex-color after-rule deliberately emits `ignore sub` rules with no
    marked glyph as lookahead guards; feaLib accepts them but warns."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "Ambiguous" not in record.getMessage()


_AMBIGUOUS_IGNORE = _AmbiguousIgnoreFilter()


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


def ensure_tab_glyph(font: TTFont) -> None:
    """Make U+0009 colorable by aliasing it to the space glyph.

    Monospace fonts often do not map tab at all, so HarfBuzz would emit
    ``.notdef`` and the comment/string FSM chain would break at a tab. Adding a
    cmap entry that reuses the space glyph keeps tabs colorable (and one cell
    wide, the usual rendering for a code font). No-op if tab is already mapped
    or the font has no space glyph."""
    cmap = font.getBestCmap()
    if 0x09 in cmap:
        return
    space_name = cmap.get(0x20)
    if space_name is None:
        return
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[0x09] = space_name


def duplicate_alternates(
    font: TTFont, base: dict[str, str], extra: dict[str, str] | None = None
) -> list[str]:
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
    created: list[str] = []

    def emit(chars: dict[str, str], palettes) -> None:
        # several codepoints can share one glyph, so dedupe by glyph name
        for base_name in dict.fromkeys(chars.values()):
            width, lsb = hmtx[base_name]
            for p in palettes:
                name = f"{base_name}.alt{p}"
                add(name, width, lsb)
                created.append(name)

    emit(base, range(1, NUM_PALETTES))
    emit(extra or {}, sorted(FSM_PALETTES))

    # extra glyph for an escaped backslash (`\\`): escape-colored but distinct
    # from the escape *introducer*, so the char after it isn't mistaken for
    # another escape sequence
    if "\\" in base:
        width, lsb = hmtx[base["\\"]]
        add(f"{base['\\']}.esc", width, lsb)
        created.append(f"{base['\\']}.esc")

    return created


def extend_variation_tables(font: TTFont, new_glyphs: list[str]) -> None:
    """Keep variable-font tables consistent after adding alternate glyphs.

    ``gvar`` stores one variation entry per glyph; a variable font whose glyph
    count grew needs empty entries for the new (outline-less) alternates, or the
    table becomes invalid. ``MVAR``/``HVAR``/``VVAR`` are metrics variation
    stores keyed independently of the glyph order, so they need no change."""
    if "gvar" not in font:
        return
    gvar = font["gvar"]
    for name in new_glyphs:
        gvar.variations.setdefault(name, [])
    gvar.glyphCount = len(font.getGlyphOrder())


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

    if "\\" in base:
        layer = LayerRecord()
        layer.name = base["\\"]
        layer.colorID = palette_index("escape")
        color_layers[f"{base['\\']}.esc"] = [layer]

    colr = newTable("COLR")
    colr.version = 0
    colr.ColorLayers = color_layers
    font["COLR"] = colr


def _lookup_outputs(lookup, outputs: set) -> None:
    """Collect the glyphs a substitution lookup can produce."""
    subtables = lookup.SubTable
    if not isinstance(subtables, list):
        subtables = [subtables]
    for sub in subtables:
        mapping = getattr(sub, "mapping", None)
        if mapping:
            outputs.update(v for v in mapping.values() if isinstance(v, str))
        alternates = getattr(sub, "alternates", None)
        if alternates:
            for glyphs in alternates.values():
                outputs.update(glyphs)
        ligatures = getattr(sub, "ligatures", None)
        if ligatures:
            for ligs in ligatures.values():
                for lig in ligs:
                    outputs.add(lig.LigGlyph)


def _referenced_lookups(subtable) -> set:
    """Lookup indices a contextual/chained subtable calls into."""
    refs = set()
    for record in getattr(subtable, "SubstLookupRecord", None) or []:
        refs.add(record.LookupListIndex)
    for attr in ("SubRulSet", "SubRuleSet", "SubClassSet", "ChainSubRuleSet",
                 "ChainSubClassSet"):
        for rule_set in getattr(subtable, attr, None) or []:
            rules = getattr(rule_set, "SubRule", None) or getattr(
                rule_set, "ChainSubRule", None
            ) or []
            for rule in rules:
                for record in getattr(rule, "SubstLookupRecord", None) or []:
                    refs.add(record.LookupListIndex)
    return refs


def _ligature_outputs(gsub, tags=("calt", "liga", "clig", "rlig")) -> set:
    """Every glyph produced (transitively) by the font's ligature features."""
    table = gsub.table
    stack = []
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag in tags:
            stack.extend(record.Feature.LookupListIndex)
    seen, outputs = set(), set()
    while stack:
        index = stack.pop()
        if index in seen:
            continue
        seen.add(index)
        lookup = table.LookupList.Lookup[index]
        _lookup_outputs(lookup, outputs)
        subtables = lookup.SubTable
        if not isinstance(subtables, list):
            subtables = [subtables]
        for sub in subtables:
            stack.extend(_referenced_lookups(sub))
    return outputs


def color_ligature_glyphs(
    font: TTFont, char_slot: dict, default_slot: str = "value"
) -> None:
    """Paint the base font's ligature glyphs with one palette color.

    A ligature is a single glyph, so it cannot be colored per component; when
    ligatures are kept this gives the ligature (and its spacing/sequence
    companions) a syntax colour instead of leaving it plain. The colour is
    derived from the ligature's component characters (their names encode them,
    e.g. ``exclam_equal.liga``) so `!=` matches `=`; when the components do not
    agree (or cannot be read) it falls back to ``default_slot``. Only glyphs
    synthesized by `calt`/`liga` that carry an outline are colored, so invisible
    intermediates are skipped."""
    if "COLR" not in font or "GSUB" not in font:
        return
    cmap = set(font.getBestCmap().values())
    reverse = {name: chr(cp) for cp, name in font.getBestCmap().items()}
    glyphs = font.getGlyphOrder()
    glyf = None
    if "glyf" in font:
        font["glyf"].ensureDecompiled()  # numberOfContours is 0 until decompiled
        glyf = font["glyf"].glyphs
    layers = font["COLR"].ColorLayers
    for name in _ligature_outputs(font["GSUB"]):
        if name in cmap or name in layers or name not in glyphs:
            continue
        if glyf is not None and getattr(glyf[name], "numberOfContours", 0) == 0:
            continue
        layer = LayerRecord()
        layer.name = name
        layer.colorID = palette_index(_ligature_slot(name, reverse, char_slot, default_slot))
        layers[name] = [layer]


def _ligature_slot(name, reverse, char_slot, default="value"):
    """Palette slot for a ligature glyph, from its component glyph names."""
    parts = name.split(".")[0].split("_")
    slots = {char_slot[reverse[p]] for p in parts if reverse.get(p) in char_slot}
    return slots.pop() if len(slots) == 1 else default



def _remap_lookup_references(obj, mapping, seen: set) -> None:
    """Rewrite every ``SubstLookupRecord`` reference reachable from ``obj``
    through ``mapping`` (old lookup index -> new index). Context/chain lookups
    nest these in rule sets and chained subtables, so a shallow walk is not
    enough."""
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, SubstLookupRecord):
        obj.LookupListIndex = mapping[obj.LookupListIndex]
        return
    if isinstance(obj, (list, tuple)):
        for item in obj:
            _remap_lookup_references(item, mapping, seen)
        return
    if isinstance(obj, dict):
        for item in obj.values():
            _remap_lookup_references(item, mapping, seen)
        return
    attrs = getattr(obj, "__dict__", None)
    if attrs:
        for name, value in attrs.items():
            if not name.startswith("_"):
                _remap_lookup_references(value, mapping, seen)


def _register_feature(script, feature_index: int) -> None:
    """Add ``feature_index`` to a script's default and named language systems."""
    for langsys in [script.DefaultLangSys] + [
        r.LangSys for r in (script.LangSysRecord or [])
    ]:
        if langsys is None:
            continue
        if feature_index not in langsys.FeatureIndex:
            langsys.FeatureIndex = sorted(langsys.FeatureIndex + [feature_index])
            langsys.FeatureCount = len(langsys.FeatureIndex)


def merge_gsub(base_gsub, our_gsub, region_ids: set[int] | None = None) -> None:
    """Merge our lookups/features into ``base_gsub`` (in place) keeping the
    base font's own lookups (and its ligatures).

    HarfBuzz applies lookups in lookup-index order, so the final order is:
    our *region* lookups (comments/strings, ``region_ids``) first — so a
    comment/string delimiter is colored before a ligature can swallow it —
    then the base font's lookups (ligatures), then our remaining lookups (so
    they do not break ligature formation). Base and our lookup references are
    remapped accordingly.

    ``region_ids`` are indices into ``our_gsub``; when omitted they are read
    from the ``rlig`` feature (the combined build). Isolated builds pass the
    region lookups of every language instead."""
    base = base_gsub.table
    ours = our_gsub.table

    if region_ids is None:
        region_ids = set()
        for fr in ours.FeatureList.FeatureRecord:
            if fr.FeatureTag == REGION_FEATURE_TAG:
                region_ids.update(fr.Feature.LookupListIndex)

    region_lookups = [ours.LookupList.Lookup[i] for i in sorted(region_ids)]
    other_lookups = [
        lk for i, lk in enumerate(ours.LookupList.Lookup) if i not in region_ids
    ]
    n_region, n_base = len(region_lookups), base.LookupList.LookupCount

    # old index -> new index for every one of our lookups
    region_pos = {old: i for i, old in enumerate(sorted(region_ids))}
    other_old = [
        i for i in range(ours.LookupList.LookupCount) if i not in region_ids
    ]
    mapping = {
        old: region_pos[old]
        for old in region_ids
    }
    mapping.update({old: n_region + n_base + j for j, old in enumerate(other_old)})

    # base references shift by the number of region lookups inserted before them
    base_shift = {i: i + n_region for i in range(n_base)}
    for lookup in base.LookupList.Lookup:
        _remap_lookup_references(lookup, base_shift, set())
    for lookup in ours.LookupList.Lookup:
        _remap_lookup_references(lookup, mapping, set())

    base.LookupList.Lookup = (
        [copy.deepcopy(lk) for lk in region_lookups]
        + list(base.LookupList.Lookup)
        + [copy.deepcopy(lk) for lk in other_lookups]
    )
    base.LookupList.LookupCount = len(base.LookupList.Lookup)

    # base feature lookup indices shift by n_region
    for fr in base.FeatureList.FeatureRecord:
        fr.Feature.LookupListIndex = [i + n_region for i in fr.Feature.LookupListIndex]

    # add our features (region first, then the rest), merging into same-tag ones
    for fr in ours.FeatureList.FeatureRecord:
        indices = [mapping[i] for i in fr.Feature.LookupListIndex]
        matching = [
            b for b in base.FeatureList.FeatureRecord if b.FeatureTag == fr.FeatureTag
        ]
        if matching:
            for b in matching:
                b.Feature.LookupListIndex = list(b.Feature.LookupListIndex) + indices
        else:
            record = copy.deepcopy(fr)
            record.Feature.LookupListIndex = indices
            base.FeatureList.FeatureRecord.append(record)
            base.FeatureList.FeatureCount = len(base.FeatureList.FeatureRecord)
            new_index = base.FeatureList.FeatureCount - 1
            for script in base.ScriptList.ScriptRecord:
                _register_feature(script.Script, new_index)


def build_highlight_font(
    base_font_path: str,
    languages: list[Language],
    theme: Theme,
    out_path: str,
    flavor: str | None = "woff2",
    emit_fea: str | None = None,
    color_all: bool = True,
    extra_chars: str = "",
    keep_ligatures: bool = False,
    language_ids: list[str] | None = None,
    isolated_languages: bool = False,
) -> TTFont:
    font = TTFont(base_font_path)
    ensure_tab_glyph(font)
    base, extra = colorable_characters(font, color_all, extra_chars)
    glyphs = {**base, **extra}

    # variable fonts: decompile the glyph-indexed variation table *before* the
    # glyph order grows (gvar asserts the count on read), then extend it after
    if "gvar" in font:
        font["gvar"]

    new_glyphs = duplicate_alternates(font, base, extra)
    extend_variation_tables(font, new_glyphs)
    # feaLib resolves glyph names through a cached reverse map; decompiling gvar
    # (above) populates it before the alternates exist, so drop the cache
    if hasattr(font, "_reverseGlyphOrderDict"):
        del font._reverseGlyphOrderDict
    write_color_tables(font, base, theme, extra)
    synthesize_name_table(font)

    region_ids: set[int] | None = None
    if isolated_languages:
        if language_ids is None:
            language_ids = [None] * len(languages)
        fea, _, region_ids = generate_isolated_features(
            languages, language_ids, glyphs, base
        )
    else:
        fea = generate_features(languages, glyphs, base, keep_ligatures=keep_ligatures)
    if emit_fea:
        with open(emit_fea, "w") as f:
            f.write(fea)

    # keep the base font's GSUB (ligatures) when asked; otherwise replace it
    base_gsub = copy.deepcopy(font["GSUB"]) if keep_ligatures and "GSUB" in font else None
    if "GSUB" in font:
        del font["GSUB"]
    # feaLib warns about `ignore sub` rules that contain no marked glyph; ours
    # are intentional lookahead guards, so drop just those messages
    fea_logger = logging.getLogger("fontTools.feaLib.parser")
    fea_logger.addFilter(_AMBIGUOUS_IGNORE)
    try:
        # only rebuild GSUB: the default also rebuilds GDEF/GPOS from the fea
        # (which has none) and would drop the base font's kerning/mark tables
        addOpenTypeFeaturesFromString(font, fea, tables=["GSUB"])
    finally:
        fea_logger.removeFilter(_AMBIGUOUS_IGNORE)
    if base_gsub is not None:
        merge_gsub(base_gsub, font["GSUB"], region_ids=region_ids)
        font["GSUB"] = base_gsub
        # a kept ligature is one glyph, so give it a single syntax colour
        char_slot = {
            ch: slot for lang in languages for slot, chars in lang.symbols.items()
            for ch in chars
        }
        color_ligature_glyphs(font, char_slot)

    # set unconditionally: a woff2 input would otherwise keep its flavor.
    # only woff/woff2 are real flavors; "ttf"/"otf"/None all mean raw sfnt.
    font.flavor = flavor if flavor in ("woff", "woff2") else None
    font.save(out_path)
    return font
