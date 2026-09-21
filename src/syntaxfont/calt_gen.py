"""Generate the OpenType feature file (GSUB `calt`) for a set of languages.

The techniques mirror the original FontWithASyntaxHighlighter:

1. Chained keyword substitution (Behdad's trick) so a multi-glyph word can be
   replaced by its colored alternates in a single passage:
       sub i' lookup ALT_SUBS_3 f' lookup ALT_SUBS_3;
   with `ignore sub` guards for word boundaries.

2. "First marked glyph + chain" for function names, properties, attributes and
   tags: a class repeated up to N times followed by a terminator marks only the
   first glyph, and a propagation rule colors the rest until a non-class glyph.

3. A finite-state machine for comments and strings: a region stays colored as
   long as the previous glyph is already colored, so unknown-length runs work.
   Newlines terminate every FSM (the documented limitation of the technique).

Glyph names are taken from the base font's cmap (they are not assumed to follow
AGL), so any monospace font can be used.
"""

from __future__ import annotations

import re

from .schema import (
    CHAR_CLASSES,
    AfterRule,
    FsmToken,
    Language,
    WordRule,
    palette_index,
)

# every character that can occur inside a colored region
_ALL = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " "  # space must be colorable inside comments/strings
    "._#$@%&|+-=~*/:;!?<>()[]{}\"'`,;^\\"
)

# palettes used by comment/string finite state machines
FSM_PALETTES = frozenset({palette_index("comment"), palette_index("string")})


class FeaBuilder:
    """Accumulates lookups and the ordered list of calt lookups."""

    def __init__(self, glyphs: dict[str, str], base_chars=None):
        # char -> base glyph name, only for chars present in the font
        self.glyphs = glyphs
        self.all_chars = list(dict.fromkeys(glyphs.keys()))
        # "base" chars are colorable in every palette (keywords, symbols, ...);
        # extra chars (e.g. CJK) are only colored inside comments/strings, so
        # they only need alternates for the FSM palettes.
        if base_chars is None:
            self.base_chars = list(self.all_chars)
        else:
            self.base_chars = [c for c in base_chars if c in glyphs]
        self.alt_palettes: set[int] = set()
        self.lookups: list[tuple[str, str]] = []  # (name, text)
        self.symbol_chars: list[str] = []
        self.want_numbers = False
        # palette -> list of stop contexts (base chars). A region of a given
        # palette must stop at *any* terminator that palette can have, otherwise
        # a chain from one comment/string FSM would leak past another's end.
        self.stops: dict[int, list[list[str]]] = {}
        self._prefixes: set[str] = set()

    def _prefix(self, lang: Language) -> str:
        """A unique, valid lookup-name prefix derived from the display name.

        Lookup names must be identifiers and unique; sanitizing a display name
        can collide (C, C++ and C# all become "C"), so disambiguate with a
        counter. Nothing user-facing depends on this value."""
        base = re.sub(r"[^A-Za-z0-9]", "", lang.name) or "Lang"
        if not (base[0].isalpha() or base[0] == "_"):
            base = "L" + base
        candidate, i = base, 2
        while candidate in self._prefixes:
            candidate, i = f"{base}{i}", i + 1
        self._prefixes.add(candidate)
        return candidate

    def register_stop(self, token: FsmToken) -> None:
        if any(c not in self.glyphs for c in token.start):
            return
        palette = palette_index(token.palette)
        if token.end and len(token.end) == 1 and len(token.start) == 1 and token.end == token.start:
            stop = [token.start[0]]  # paired delimiter: stop at the closing quote
        elif token.end:
            if any(c not in self.glyphs for c in token.end):
                return
            stop = list(token.end)
        else:
            return  # line comment: newline terminates naturally
        self.stops.setdefault(palette, []).append(stop)

    # -- helpers ---------------------------------------------------------

    def base(self, ch: str) -> str:
        return self.glyphs[ch]

    def alt(self, ch: str, palette: int) -> str:
        return f"{self.glyphs[ch]}.alt{palette}"

    def _present(self, chars: str) -> list[str]:
        return [c for c in dict.fromkeys(chars) if c in self.glyphs]

    def _cls(self, chars: list[str]) -> str:
        return "[" + " ".join(self.base(c) for c in chars) + "]"

    def _alt_cls(self, chars: list[str], palette: int) -> str:
        return "[" + " ".join(self.alt(c, palette) for c in chars) + "]"

    @property
    def all_class(self) -> str:
        return self._cls(self.all_chars)

    def add_lookup(self, name: str, body_lines: list[str]) -> None:
        text = f"lookup {name} {{\n" + "\n".join(body_lines) + f"\n}} {name};"
        self.lookups.append((name, text))

    # -- rule groups -----------------------------------------------------

    def symbol_lookup(self) -> None:
        chars = self._present("".join(self.symbol_chars))
        if not chars:
            return
        palette = palette_index("symbol")
        lines = [f"  sub {self.base(c)}' by {self.alt(c, palette)};" for c in chars]
        self.add_lookup("AlwaysSymbols", lines)

    def number_lookup(self) -> None:
        if not self.want_numbers:
            return
        chars = self._present("0123456789")
        if not chars:
            return
        palette = palette_index("number")
        lines = [f"  sub {self.base(c)}' by {self.alt(c, palette)};" for c in chars]
        self.add_lookup("AlwaysNumbers", lines)

    def _words_lookup(self, words: list[str], palette: int, tag: str) -> None:
        boundary = self._present(CHAR_CLASSES["ident"])
        boundary_cls = self._cls(boundary)
        lines = []
        for word in sorted(dict.fromkeys(words)):
            if any(c not in self.glyphs for c in word):
                continue
            names = [self.base(c) for c in word]
            if len(names) > 1 and boundary:
                pre = " ".join(n + "'" for n in names)
                lines.append(f"  ignore sub {boundary_cls} {pre};")
                lines.append(f"  ignore sub {pre} {boundary_cls};")
            chain = " ".join(f"{n}' lookup ALT_SUBS_{palette}" for n in names)
            lines.append(f"  sub {chain};")
        if lines:
            self.alt_palettes.add(palette)
            self.add_lookup(f"Words_{tag}", lines)

    def _word_rule_lookup(self, rule: WordRule, tag: str) -> None:
        palette = palette_index(rule.palette)
        chars = self._present("".join(rule.chars))
        if not chars or any(c not in self.glyphs for c in rule.terminator):
            return
        cls = self._cls(chars)
        alt = self._alt_cls(chars, palette)
        term = [self.base(c) for c in rule.terminator]
        lines = []
        for n in range(1, rule.max_len + 1):
            pattern = " ".join([f"{cls}'"] + [cls] * (n - 1) + term)
            lines.append(f"  sub {pattern} by {alt};")
        lines.append(f"  sub {alt} {cls}' by {alt};")
        self.add_lookup(f"Word_{tag}", lines)

    def _after_rule_lookup(self, rule: AfterRule, tag: str) -> None:
        palette = palette_index(rule.palette)
        chars = self._present("".join(rule.chars))
        if not chars:
            return
        cls = self._cls(chars)
        alt = self._alt_cls(chars, palette)
        lines = []
        for seq in rule.after:
            if any(c not in self.glyphs for c in seq):
                continue
            seq_names = " ".join(self.base(c) for c in seq)
            lines.append(f"  sub {seq_names} {cls}' by {alt};")
        lines.append(f"  sub {alt} {cls}' by {alt};")
        if lines:
            self.add_lookup(f"After_{tag}", lines)

    def _fsm_lookup(self, token: FsmToken, tag: str) -> None:
        palette = palette_index(token.palette)
        if any(c not in self.glyphs for c in token.start):
            return
        start_names = [self.base(c) for c in token.start]
        lines = []

        # stops for every FSM region that shares this palette, so chains never
        # continue past another region's terminator
        for stop in self.stops.get(palette, []):
            stop_alts = " ".join(self.alt(c, palette) for c in stop)
            lines.append(f"  ignore sub {stop_alts} @All';")

        if token.end and len(token.end) == 1 and len(token.start) == 1 and token.end == token.start:
            # paired delimiter (quotes): opening stays uncolored and triggers the
            # first content glyph; the closing one is colored by the chain, after
            # which an ignore stops propagation.
            lines.append(f"  sub {start_names[0]} @All' by @AllAlt{palette};")
        else:
            chain = " ".join(f"{n}' lookup ALT_SUBS_{palette}" for n in start_names)
            lines.append(f"  sub {chain};")
        lines.append(f"  sub @AllAlt{palette} @All' by @AllAlt{palette};")
        self.alt_palettes.add(palette)
        self.add_lookup(f"Fsm_{tag}", lines)

    # -- top level -------------------------------------------------------

    def add_language(self, lang: Language) -> None:
        name = self._prefix(lang)
        # FSM regions first: they mask everything inside comments/strings
        for i, token in enumerate(lang.fsm_tokens):
            self._fsm_lookup(token, f"{name}Fsm{i}")
        # words (keywords/builtins/literals) before function rules, so `if(`
        # stays a keyword instead of being taken over by the function rule
        self._words_lookup(lang.keywords, palette_index("keyword"), f"{name}Kw")
        self._words_lookup(lang.builtins, palette_index("builtin"), f"{name}Bt")
        self._words_lookup(lang.literals, palette_index("literal"), f"{name}Lt")
        for i, rule in enumerate(lang.word_rules):
            self._word_rule_lookup(rule, f"{name}W{i}")
        for i, rule in enumerate(lang.after_rules):
            self._after_rule_lookup(rule, f"{name}A{i}")
        self.symbol_chars.extend(lang.symbols)
        self.want_numbers = self.want_numbers or lang.numbers

    def build(self) -> str:
        # symbols/numbers run last so they only color glyphs nothing else claimed
        self.symbol_lookup()
        self.number_lookup()

        parts = [f"@All = {self.all_class};"]
        # @AllAlt must match @All elementwise, so it includes extra chars; it is
        # only referenced by the comment/string FSM.
        alt_defs = [
            f"@AllAlt{p} = {self._alt_cls(self.all_chars, p)};"
            for p in sorted(self.alt_palettes & FSM_PALETTES)
        ]
        if alt_defs:
            parts.append("\n".join(alt_defs))
        # ALT_SUBS only needs the base chars (keywords, delimiters are ASCII)
        for p in sorted(self.alt_palettes):
            lines = [
                f"  sub {self.base(c)} by {self.alt(c, p)};" for c in self.base_chars
            ]
            parts.append(
                f"lookup ALT_SUBS_{p} {{\n" + "\n".join(lines) + f"\n}} ALT_SUBS_{p};"
            )
        for _, text in self.lookups:
            parts.append(text)
        feature = (
            "feature calt {\n"
            + "\n".join(f"  lookup {name};" for name, _ in self.lookups)
            + "\n} calt;"
        )
        parts.append(feature)
        return "\n\n".join(parts) + "\n"


def generate_features(
    languages: list[Language], glyphs: dict[str, str], base_chars=None
) -> str:
    """Build the complete .fea text for all languages.

    ``glyphs`` maps every colorable char to its glyph name; ``base_chars`` is
    the subset colorable in all palettes (defaults to all of ``glyphs``)."""
    builder = FeaBuilder(glyphs, base_chars)
    for lang in languages:
        for token in lang.fsm_tokens:
            builder.register_stop(token)
    for lang in languages:
        builder.add_language(lang)
    return builder.build()
