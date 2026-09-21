"""Configuration schema for syntaxfont.

A build is described by three inputs:

* a base font (any monospace TTF/OTF),
* one or more ``Language`` definitions (YAML),
* a ``Theme`` (YAML) mapping semantic palette slots to colors.

Palette slots are semantic names; each maps to a fixed CPAL index. Colored
glyph alternates are named ``<glyph>.alt<index>``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# semantic slot -> CPAL palette index. Index 0 is unused: base text keeps the
# CSS `color`, only alternates are painted through COLR.
PALETTES: dict[str, int] = {
    "comment": 1,
    "string": 2,
    "keyword": 3,
    "builtin": 4,
    "literal": 5,
    "function": 6,
    "tag": 7,
    "selector": 8,
    "attr": 9,
    "symbol": 10,
    "number": 11,
}
NUM_PALETTES = max(PALETTES.values()) + 1

# character class presets usable from YAML as `chars: <name>`
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
CHAR_CLASSES: dict[str, str] = {
    "letters": _LETTERS,
    "ident": _LETTERS + _DIGITS + "_$",
    "word": _LETTERS + _DIGITS + "-_",
    "digits": _DIGITS,
}

AGL_NAMES = {
    " ": "space",
    "!": "exclam",
    '"': "quotedbl",
    "#": "numbersign",
    "$": "dollar",
    "%": "percent",
    "&": "ampersand",
    "'": "quotesingle",
    "(": "parenleft",
    ")": "parenright",
    "*": "asterisk",
    "+": "plus",
    ",": "comma",
    "-": "hyphen",
    ".": "period",
    "/": "slash",
    ":": "colon",
    ";": "semicolon",
    "<": "less",
    "=": "equal",
    ">": "greater",
    "?": "question",
    "@": "at",
    "[": "bracketleft",
    "\\": "backslash",
    "]": "bracketright",
    "^": "asciicircum",
    "_": "underscore",
    "`": "grave",
    "{": "braceleft",
    "|": "bar",
    "}": "braceright",
    "~": "asciitilde",
}

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def glyph_name(ch: str) -> str:
    """Map a character to its glyph name (AGL where available)."""
    if ch in AGL_NAMES:
        return AGL_NAMES[ch]
    if _IDENT_RE.match(ch):
        return ch
    return "uni%04X" % ord(ch)


def palette_index(name: str) -> int:
    try:
        return PALETTES[name]
    except KeyError:
        raise ValueError(
            f"unknown palette slot {name!r}; known: {', '.join(PALETTES)}"
        ) from None


def resolve_chars(spec) -> list[str]:
    """Resolve a YAML `chars` value: preset name, or literal string of chars."""
    if spec is None:
        return list(CHAR_CLASSES["ident"])
    if isinstance(spec, list):
        return list("".join(spec))
    if spec in CHAR_CLASSES:
        return list(CHAR_CLASSES[spec])
    return list(spec)


def _string_list(value, field: str) -> list[str]:
    """Validate a list of strings (guards against YAML booleans/null sneaking
    in, e.g. unquoted `NULL` or `ON`)."""
    out = []
    for item in value or []:
        if not isinstance(item, str):
            raise ValueError(f"{field} entries must be strings, got {item!r}")
        out.append(item)
    return out


def _sequence(value, field: str) -> list[str]:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {value!r}")
    return list(value)


@dataclass
class FsmToken:
    """A variable-length region colored by a finite state machine.

    ``start`` is the opening character sequence, ``end`` the closing one
    (``None`` means "to end of line"). Newlines always terminate the FSM,
    matching the original font's limitation.
    """

    start: list[str]
    palette: str = "comment"
    end: list[str] | None = None


@dataclass
class WordRule:
    """A word immediately followed by ``terminator`` gets ``palette`` color.

    Example: CSS/JS function names -> terminator ``"("``; CSS properties and
    HTML attributes -> terminator ``"="`` or ``":"``.
    """

    terminator: list[str]
    palette: str
    chars: list[str] = field(default_factory=lambda: list(CHAR_CLASSES["ident"]))
    max_len: int = 24


@dataclass
class AfterRule:
    """A word immediately *preceded* by one of ``after`` sequences gets colored.

    Example: HTML tags after ``<`` / ``</``, CSS selectors after ``.`` / ``#``.
    """

    after: list[list[str]]
    palette: str
    chars: list[str] = field(default_factory=lambda: list(CHAR_CLASSES["word"]))


@dataclass
class Language:
    name: str  # display name, e.g. "JavaScript", "C++"
    keywords: list[str] = field(default_factory=list)
    builtins: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    numbers: bool = True
    word_rules: list[WordRule] = field(default_factory=list)
    after_rules: list[AfterRule] = field(default_factory=list)
    fsm_tokens: list[FsmToken] = field(default_factory=list)


@dataclass
class Theme:
    name: str
    colors: dict[str, str]  # semantic slot -> "#rrggbb"


def parse_fsm_token(data: dict) -> FsmToken:
    return FsmToken(
        start=_sequence(data["start"], "fsm start"),
        palette=data.get("palette", "comment"),
        end=_sequence(data["end"], "fsm end") if data.get("end") else None,
    )


def parse_word_rule(data: dict) -> WordRule:
    term = data["terminator"]
    return WordRule(
        terminator=list(term) if isinstance(term, str) else list(term),
        palette=data.get("palette", "function"),
        chars=resolve_chars(data.get("chars")),
        max_len=int(data.get("max_len", 24)),
    )


def parse_after_rule(data: dict) -> AfterRule:
    after = data["after"]
    seqs = [after] if isinstance(after, str) else after
    return AfterRule(
        after=[list(s) for s in seqs],
        palette=data.get("palette", "selector"),
        chars=resolve_chars(data.get("chars")),
    )


def parse_language(data: dict) -> Language:
    return Language(
        name=data["name"],
        keywords=_string_list(data.get("keywords"), "keywords"),
        builtins=_string_list(data.get("builtins"), "builtins"),
        literals=_string_list(data.get("literals"), "literals"),
        symbols=_string_list(data.get("symbols"), "symbols"),
        numbers=bool(data.get("numbers", True)),
        word_rules=[parse_word_rule(w) for w in data.get("word_rules", [])],
        after_rules=[parse_after_rule(a) for a in data.get("after_rules", [])],
        fsm_tokens=[parse_fsm_token(t) for t in data.get("fsm_tokens", [])],
    )


def parse_theme(data: dict) -> Theme:
    unknown = set(data.get("colors", {})) - set(PALETTES)
    if unknown:
        raise ValueError(
            f"theme {data.get('name')!r} has unknown color slots: {', '.join(sorted(unknown))}"
        )
    return Theme(name=data["name"], colors=dict(data.get("colors", {})))
