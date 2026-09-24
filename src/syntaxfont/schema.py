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
    "value": 12,
    "escape": 13,
    "format": 14,
}
NUM_PALETTES = max(PALETTES.values()) + 1

# character class presets usable from YAML as `chars: <name>`
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
CHAR_CLASSES: dict[str, str] = {
    "letters": _LETTERS,
    "ident": _LETTERS + _DIGITS + "_$",
    "word": _LETTERS + _DIGITS + "-_",
    "cssword": _LETTERS + _DIGITS + "-._#*",
    "interp": _LETTERS + _DIGITS + "_.$()[]+-*/%<>=!&|?:,^~@ ",
    "digits": _DIGITS,
}

# Characters the original font colors unconditionally (via COLR on the base
# glyph), grouped by the palette they use. The original gives each punctuation
# char a fixed category color rather than one "symbol" color:
#   {} -> keyword, ()[]@ -> function, =+%~ -> value, &|:;$<>"';/ -> symbol
# digits are always colored with the `number` palette.
DEFAULT_SYMBOLS: dict[str, str] = {
    "keyword": "{}",
    "function": "()[]@",
    "value": "=+%~",
    "symbol": "&|:;$<>\"';/!?*^",
}

# characters that form an escape sequence when preceded by `\` inside a string
DEFAULT_ESCAPES = "ntrvfb0ux\\\"'`"

# characters that can appear in a printf-style `%...` format specifier
FORMAT_CHARS = "diouxXeEfFgGcspnhlLzjt0123456789.+#-%"

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
    matching the original font's limitation. With ``color_delimiters=False``
    the delimiters themselves stay uncolored (e.g. CSS `:`/`;`).

    With ``interpolation=True`` (template literals) the region is paused at
    ``${`` so the interpolation is highlighted as code, then resumed after the
    matching ``}``. The delimiters are configurable (``open``/``close``) for
    languages that use another syntax, e.g. Swift ``\\(...)`` or Ruby ``#{}``.
    """

    start: list[str]
    palette: str = "comment"
    end: list[str] | None = None
    color_delimiters: bool = True
    interpolation: bool = False
    interp_open: list[str] = field(default_factory=lambda: ["$", "{"])
    interp_close: list[str] = field(default_factory=lambda: ["}"])
    # extra single chars that also terminate the region (e.g. CSS values end at
    # `)`, `{`, `}` as well as their declared `end`)
    stop_at: list[str] = field(default_factory=list)


@dataclass
class WordRule:
    """A word immediately followed by ``terminators`` gets ``palette`` color.

    Example: CSS/JS function names -> terminator ``"("``; CSS properties and
    HTML attributes -> terminator ``"="`` or ``":"``; CSS selectors ->
    terminators ``">", "{", "~", "+"`` with ``allow_space`` for `div >`.
    """

    terminators: list[str]
    palette: str
    chars: list[str] = field(default_factory=lambda: list(CHAR_CLASSES["ident"]))
    max_len: int = 24
    allow_space: bool = False


@dataclass
class AfterRule:
    """A word immediately *preceded* by one of ``after`` sequences gets colored.

    Example: HTML tags after ``<`` / ``</``, CSS selectors after ``.`` / ``#``.
    """

    after: list[list[str]]
    palette: str
    chars: list[str] = field(default_factory=lambda: list(CHAR_CLASSES["word"]))
    # when set, the word must also be followed by one of ``terminators`` (e.g.
    # CSS hex colors: `#` + hexdigits that end at a `;`, `}` or `!`)
    terminators: list[str] | None = None
    # when set, color the chars only when more chars follow (a bounded run); the
    # last char is left for the preceding ``after`` match to color. Used together
    # with ``terminators`` for bounded lookahead-less runs like CSS hex colors.
    bounded: bool = False
    # when set, the trigger must not be immediately preceded by one of these
    # chars (e.g. Ruby `.method` must not fire inside a float like `1.5`)
    not_after: list[str] = field(default_factory=list)


@dataclass
class Language:
    name: str  # display name, e.g. "JavaScript", "C++"
    keywords: list[str] = field(default_factory=list)
    builtins: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    symbols: dict[str, str] = field(default_factory=dict)  # palette slot -> chars
    numbers: bool = True
    escapes: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    word_rules: list[WordRule] = field(default_factory=list)
    after_rules: list[AfterRule] = field(default_factory=list)
    fsm_tokens: list[FsmToken] = field(default_factory=list)
    # keywords/builtins/literals are matched case-insensitively (SQL, ...). The
    # generator is case-sensitive, so the word lists are expanded to upper+lower
    # forms at parse time.
    case_insensitive: bool = False


@dataclass
class Theme:
    name: str
    colors: dict[str, str]  # semantic slot -> "#rrggbb"


def parse_fsm_token(data: dict) -> FsmToken:
    interp = data.get("interpolation", False)
    interp_open, interp_close = ["$", "{"], ["}"]
    if isinstance(interp, dict):
        interp_open = _sequence(interp.get("open", "${"), "interpolation open")
        interp_close = _sequence(interp.get("close", "}"), "interpolation close")
        interp = True
    return FsmToken(
        start=_sequence(data["start"], "fsm start"),
        palette=data.get("palette", "comment"),
        end=_sequence(data["end"], "fsm end") if data.get("end") else None,
        color_delimiters=bool(data.get("color_delimiters", True)),
        interpolation=bool(interp),
        interp_open=interp_open,
        interp_close=interp_close,
        stop_at=(
            _sequence(data["stop_at"], "stop_at") if data.get("stop_at") else []
        ),
    )


def parse_word_rule(data: dict) -> WordRule:
    if "terminators" in data:
        terms = [str(t) for t in data["terminators"]]
    else:
        term = data["terminator"]
        terms = [term] if isinstance(term, str) else [str(t) for t in term]
    for term in terms:
        if len(term) != 1:
            raise ValueError(f"word terminators must be single characters, got {term!r}")
    return WordRule(
        terminators=terms,
        palette=data.get("palette", "function"),
        chars=resolve_chars(data.get("chars")),
        max_len=int(data.get("max_len", 24)),
        allow_space=bool(data.get("allow_space", False)),
    )


def parse_after_rule(data: dict) -> AfterRule:
    after = data.get("after", "")
    seqs = [after] if isinstance(after, str) else after
    return AfterRule(
        after=[list(s) for s in seqs],
        palette=data.get("palette", "selector"),
        chars=resolve_chars(data.get("chars")),
        terminators=(
            [str(t) for t in data["terminators"]]
            if "terminators" in data
            else None
        ),
        bounded=bool(data.get("bounded", False)),
        not_after=(
            _sequence(data["not_after"], "not_after")
            if data.get("not_after")
            else []
        ),
    )


def parse_language(data: dict) -> Language:
    if "symbols" not in data:
        symbols = dict(DEFAULT_SYMBOLS)
    elif isinstance(data["symbols"], dict):
        symbols = {str(slot): "".join(chars) for slot, chars in data["symbols"].items()}
    else:
        symbols = {"symbol": "".join(_string_list(data["symbols"], "symbols"))}
    case_insensitive = bool(data.get("case_insensitive", False))

    def words(key: str) -> list[str]:
        items = _string_list(data.get(key), key)
        if not case_insensitive:
            return items
        expanded: list[str] = []
        for word in items:
            for form in (word.upper(), word.lower()):
                if form not in expanded:
                    expanded.append(form)
        return expanded

    return Language(
        name=data["name"],
        keywords=words("keywords"),
        builtins=words("builtins"),
        literals=words("literals"),
        symbols=symbols,
        numbers=bool(data.get("numbers", True)),
        escapes=(
            _string_list(data["escapes"], "escapes")
            if "escapes" in data
            else list(DEFAULT_ESCAPES)
        ),
        formats=(
            _string_list(data["formats"], "formats")
            if "formats" in data
            else list(FORMAT_CHARS)
        ),
        word_rules=[parse_word_rule(w) for w in data.get("word_rules", [])],
        after_rules=[parse_after_rule(a) for a in data.get("after_rules", [])],
        fsm_tokens=[parse_fsm_token(t) for t in data.get("fsm_tokens", [])],
        case_insensitive=case_insensitive,
    )


def parse_theme(data: dict) -> Theme:
    unknown = set(data.get("colors", {})) - set(PALETTES)
    if unknown:
        raise ValueError(
            f"theme {data.get('name')!r} has unknown color slots: {', '.join(sorted(unknown))}"
        )
    return Theme(name=data["name"], colors=dict(data.get("colors", {})))
