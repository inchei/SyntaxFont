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
    PALETTES,
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
    " \t"  # space and tab must be colorable inside comments/strings
    "._#$@%&|+-=~*/:;!?<>()[]{}\"'`,;^\\"
)

# palettes used by comment/string/value finite state machines
FSM_PALETTES = frozenset(
    {palette_index("comment"), palette_index("string"), palette_index("value")}
)

# palette index -> semantic slot name, for stable lookup names
SLOT_BY_INDEX = {index: slot for slot, index in PALETTES.items()}


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
        self.symbol_groups: dict[str, list[str]] = {}
        self.escape_chars: list[str] = []
        self.format_chars: list[str] = []
        self.want_numbers = False
        # palette -> list of stop contexts (base chars). A region of a given
        # palette must stop at *any* terminator that palette can have, otherwise
        # a chain from one comment/string FSM would leak past another's end.
        self.stops: dict[int, list[list[str]]] = {}
        self._prefixes: set[str] = set()
        # palettes that have a comment/string/value FSM; used to stop one region
        # from starting inside another (e.g. `#` or `//` inside a string)
        self.fsm_palettes: set[int] = set()

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
        # regions that leave their delimiters uncolored manage their own stop
        if not token.color_delimiters:
            return
        palette = palette_index(token.palette)
        if token.end and len(token.end) == 1 and len(token.start) == 1 and token.end == token.start:
            return  # paired delimiter: handled per-token in add_fsm_group
        elif token.end:
            if any(c not in self.glyphs for c in token.end):
                return
            stop = list(token.end)
        else:
            return  # line comment: newline terminates naturally
        bucket = self.stops.setdefault(palette, [])
        if stop not in bucket:
            bucket.append(stop)

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
        # one lookup per palette slot, so each punctuation char keeps its
        # category color ({} keyword, ()[]@ function, =+%~ value, rest symbol)
        by_palette: dict[int, list[str]] = {}
        for slot, chars in self.symbol_groups.items():
            palette = palette_index(slot)
            by_palette.setdefault(palette, []).extend(self._present(chars))
        for palette in sorted(by_palette):
            chars = list(dict.fromkeys(by_palette[palette]))
            if not chars:
                continue
            lines = [f"  sub {self.base(c)}' by {self.alt(c, palette)};" for c in chars]
            self.add_lookup(f"AlwaysSymbols{palette}", lines)

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
        # longest first: `ignore` is lookup-wide, so a shorter word's guard must
        # never get to block a longer word that also matches here
        for word in sorted(dict.fromkeys(words), key=lambda w: (-len(w), w)):
            if any(c not in self.glyphs for c in word):
                continue
            names = [self.base(c) for c in word]
            # boundary guards are needed for single-char words too, otherwise
            # e.g. Ruby's `p` builtin matches inside `empty`
            if boundary:
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
        terms = [c for c in rule.terminators if c in self.glyphs]
        if not chars or not terms:
            return
        cls = self._cls(chars)
        alt = self._alt_cls(chars, palette)
        term = self._cls(terms)
        lines = []
        for n in range(1, rule.max_len + 1):
            body = " ".join([f"{cls}'"] + [cls] * (n - 1) + [term])
            lines.append(f"  sub {body} by {alt};")
            if rule.allow_space and " " in self.glyphs:
                spaced = " ".join([f"{cls}'"] + [cls] * (n - 1) + [self.base(" "), term])
                lines.append(f"  sub {spaced} by {alt};")
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
        if rule.terminators:
            # also require one of the terminators after the chars, so only a
            # value that ends the declaration/block is matched (CSS hex color)
            terms = [c for c in rule.terminators if c in self.glyphs]
            if not terms:
                return
            term = self._cls(terms)
            # a hex run is bounded by non-hex chars on both sides, so the chain
            # must not start mid-identifier (`color` -> `c`+`olor`)
            nonhex = [c for c in self._present(CHAR_CLASSES["ident"]) if c not in rule.chars]
            guards = []
            if nonhex:
                nonhex_cls = self._cls(nonhex)
                guards = [
                    f"  ignore sub {nonhex_cls} {cls};",
                    f"  ignore sub {nonhex_cls} {alt};",
                ]
            triggers = [
                " ".join(self.base(c) for c in seq)
                for seq in rule.after
                if all(c in self.glyphs for c in seq)
            ] or [""]
            for seq_names in triggers:
                prefix = f"{seq_names} " if seq_names else ""
                lines.extend(guards)
                if rule.bounded:
                    # color the first char, then each subsequent char while more
                    # chars follow; the last char before the terminator is left
                    # uncolored (no lookahead available)
                    lines.append(f"  ignore sub {prefix}{cls} {cls};")
                    lines.append(f"  ignore sub {alt} {cls} {cls};")
                    lines.append(f"  sub {prefix}{cls}' by {alt};")
                    lines.append(f"  sub {alt} {cls}' by {alt};")
                else:
                    # color every char of the run; the terminator can be the
                    # lookahead that stops the chain
                    lines.append(f"  sub {prefix}{cls}' by {alt};")
                    lines.append(f"  sub {alt} {cls}' by {alt};")
                    lines.append(f"  ignore sub {alt} {cls} {term};")
                    lines.append(f"  ignore sub {alt} {cls};")
            self.add_lookup(f"After_{tag}", lines)
            return
        for seq in rule.after:
            if any(c not in self.glyphs for c in seq):
                continue
            seq_names = " ".join(self.base(c) for c in seq)
            # suppress the trigger when preceded by a `not_after` char (e.g. a
            # digit, so Ruby `.method` does not fire inside `1.5`); the mark must
            # be on the same glyph as the substitution (the ident after the dot)
            for ch in rule.not_after:
                if ch in self.glyphs:
                    lines.append(f"  ignore sub {self.base(ch)} {seq_names} {cls}';")
            lines.append(f"  sub {seq_names} {cls}' by {alt};")
        lines.append(f"  sub {alt} {cls}' by {alt};")
        if lines:
            self.add_lookup(f"After_{tag}", lines)

    def _fsm_start_lines(self, token: FsmToken, palette: int) -> list[str] | None:
        """Start-coloring rules for one FSM token (no stops, no chain)."""
        if any(c not in self.glyphs for c in token.start):
            return None
        start_names = [self.base(c) for c in token.start]
        if token.end and len(token.end) == 1 and len(token.start) == 1 and token.end == token.start:
            lines = []
            if start_names[0] in ("quotedbl", "quotesingle"):
                # don't let apostrophes start strings: a quote right after a
                # word char (don't, x'a') stays plain
                boundary = self._cls(self._present(CHAR_CLASSES["ident"]))
                lines.append(f"  ignore sub {boundary} {start_names[0]}';")
            # color the opening delimiter itself; the chain colors the content
            lines.append(f"  sub {start_names[0]}' @All by {self.alt(token.start[0], palette)};")
            return lines
        if not token.color_delimiters:
            if token.end is not None and any(c not in self.glyphs for c in token.end):
                return None
            # opener stays uncolored and triggers the first content char; the
            # chain runs to the end delimiter (or to a newline when end is None,
            # e.g. a YAML scalar value)
            seq = " ".join(start_names)
            return [f"  sub {seq} @All' by @AllAlt{palette};"]
        chain = " ".join(f"{n}' lookup ALT_SUBS_{palette}" for n in start_names)
        return [f"  sub {chain};"]

    def add_fsm(self, by_palette: dict[int, list[FsmToken]], name: str) -> None:
        """One lookup for a group of comment/string/value regions.

        Merging every palette into a single lookup is what makes regions nest
        correctly: because the chain colors as it scans left to right, the first
        opener in a line wins and the region guard (``@InRegion``) suppresses any
        opener that appears inside an already-colored region. Separate lookups
        can't see each other's coloring, so `#`/`//` would leak into strings."""
        lines = []
        # union stops per palette: a region must stop at any of its own ends
        for palette in sorted(by_palette):
            for stop in self.stops.get(palette, []):
                stop_alts = " ".join(self.alt(c, palette) for c in stop)
                lines.append(f"  ignore sub {stop_alts} @All';")
        # regions that leave their delimiters uncolored stop the chain at the end
        # (must precede the chain below, which is position-sensitive)
        for palette, tokens in by_palette.items():
            for token in tokens:
                ends: list[str] = []
                if token.end and all(c in self.glyphs for c in token.end):
                    ends.append(token.end[0])
                ends.extend(c for c in token.stop_at if c in self.glyphs)
                if not token.color_delimiters:
                    for c in dict.fromkeys(ends):
                        lines.append(
                            f"  ignore sub @AllAlt{palette} {self.base(c)}';"
                        )
        # paired delimiters: stop after the closing one, but an escaped quote
        # (`\'`, `\"`) must not terminate the string
        for palette, tokens in by_palette.items():
            for token in tokens:
                lines.extend(self._paired_stops(token, palette))
        # template guards must come before the chain they constrain
        for palette, tokens in by_palette.items():
            for token in tokens:
                if token.interpolation:
                    lines.extend(self._interpolation_guards(token, palette))
        # the chain propagates an existing region color; it must run before the
        # region guards below so an opener *inside* a region is still colored
        for palette in sorted(by_palette):
            lines.append(f"  sub @AllAlt{palette} @All' by @AllAlt{palette};")
        # don't let a region start while already inside another region (only
        # affects the start rules that follow)
        for tokens in by_palette.values():
            for token in tokens:
                lines.extend(self._fsm_region_guards(token))
        for palette, tokens in by_palette.items():
            for token in tokens:
                start = self._fsm_start_lines(token, palette)
                if start:
                    lines.extend(start)
        # template literals: resume the string after the interpolation close
        for palette, tokens in by_palette.items():
            for token in tokens:
                if token.interpolation:
                    lines.extend(self._interpolation_resume(token, palette))
        self.alt_palettes.update(by_palette)
        self.add_lookup(name, lines)

    def _paired_stops(self, token: FsmToken, palette: int) -> list[str]:
        """Stop rules for a paired delimiter, escape-aware.

        A closing quote is preceded by a string-colored char; an escaped quote
        (`\\'`) is preceded by a string-colored backslash, so it must not stop."""
        if not (token.end and len(token.end) == 1 and len(token.start) == 1
                and token.end == token.start):
            return []
        if token.start[0] not in self.glyphs:
            return []
        quote_alt = self.alt(token.start[0], palette)
        if "\\" not in self.glyphs:
            return [f"  ignore sub {quote_alt} @All';"]
        others = [c for c in self.all_chars if c != "\\"]
        # a closing quote is preceded by a non-backslash string char; an escaped
        # quote (`\'`) is preceded by a backslash and must not stop
        return [f"  ignore sub {self._alt_cls(others, palette)} {quote_alt} @All';"]

    def _fsm_region_guards(self, token: FsmToken) -> list[str]:
        """Suppress a region's opener when the previous char is already colored.

        Without this a `#`/`//` comment opener re-colors inside a string (and a
        quote re-colors inside a comment), because every start rule is otherwise
        context-free."""
        if any(c not in self.glyphs for c in token.start):
            return []
        first = self.base(token.start[0])
        return [f"  ignore sub @InRegion {first}';"]

    def _interpolation_guards(self, token: FsmToken, palette: int) -> list[str]:
        if not all(c in self.glyphs for c in token.interp_open + token.interp_close):
            return []
        open_names = [self.base(c) for c in token.interp_open]
        opener_alt = self.alt(token.start[0], palette)
        first, rest = open_names[0], " ".join(open_names[1:])
        tail = f" {rest}" if rest else ""
        return [
            # opening delimiter followed by the interpolation open must not
            # color the open sequence's first char
            f"  ignore sub {opener_alt} {first}'{tail};",
            # pause: inside a string, the open sequence stops the chain
            f"  ignore sub @AllAlt{palette} {first}'{tail};",
        ]

    def _interpolation_resume(self, token: FsmToken, palette: int) -> list[str]:
        """Resume string coloring right after the interpolation close.

        OpenType can't track unbounded state, so the resume matches a bounded
        interpolation of identifier-ish characters (``name``, ``a.b``, ``fn(x)``)."""
        if not all(c in self.glyphs for c in token.interp_open + token.interp_close):
            return []
        open_names = [self.base(c) for c in token.interp_open]
        close_names = [self.base(c) for c in token.interp_close]
        prefix = " ".join(open_names)
        suffix = " ".join(close_names)
        # cursor class: any colorable char except the open sequence's first char,
        # so an adjacent interpolation isn't swallowed back into the string
        # (the replacement class must match the input class elementwise)
        cursor_chars = [c for c in self.all_chars if c != token.interp_open[0]]
        cursor = self._cls(cursor_chars)
        cursor_alt = self._alt_cls(cursor_chars, palette)
        lines = [f"  sub {prefix} {suffix} {cursor}' by {cursor_alt};"]
        # body class: expression chars, but never the close delimiters (so the
        # first close delimiter ends the interpolation)
        body_chars = [
            c
            for c in self._present(CHAR_CLASSES["interp"])
            if c not in token.interp_close
        ]
        cls = self._cls(body_chars)
        for n in range(1, 25):
            body = " ".join([*open_names] + [cls] * n + [*close_names, cursor + "'"])
            lines.append(f"  sub {body} by {cursor_alt};")
        return lines

    def add_escape_lookup(self) -> None:
        """Re-color `\\x` escape sequences inside strings to the escape palette.

        Runs after the string FSM, so the backslash and its following char are
        already string-colored; this lookup recolors both."""
        chars = self._present("".join(self.escape_chars))
        if not chars or "\\" not in self.glyphs:
            return
        string_p, escape_p = palette_index("string"), palette_index("escape")
        bs_s, bs_e = self.alt("\\", string_p), self.alt("\\", escape_p)
        bs_esc = f"{self.base('\\')}.esc"
        # escaped backslash first: otherwise the introducer rule for the char
        # after `\\` fires at the second backslash
        lines = [
            f"  sub {bs_s}' {bs_s} by {bs_e};",
            f"  sub {bs_e} {bs_s}' by {bs_esc};",
        ]
        for ch in chars:
            if ch == "\\":
                continue
            x_s, x_e = self.alt(ch, string_p), self.alt(ch, escape_p)
            # introducer backslash, then the escaped character
            lines.append(f"  sub {bs_s}' {x_s} by {bs_e};")
            lines.append(f"  sub {bs_e} {x_s}' by {x_e};")
        self.add_lookup("StringEscapes", lines)

    def add_format_lookup(self) -> None:
        """Color printf-style `%...` specifiers inside strings.

        `%` plus a run of specifier characters is recolored to the format
        palette; the run stops at the first non-specifier char."""
        chars = self._present("".join(self.format_chars))
        if not chars or "%" not in self.glyphs:
            return
        string_p, format_p = palette_index("string"), palette_index("format")
        pct_s, pct_f = self.alt("%", string_p), self.alt("%", format_p)
        # the specifier chars are already string-colored, so match those glyphs
        spec_s = self._alt_cls(chars, string_p)
        spec_f = self._alt_cls(chars, format_p)
        lines = [
            f"  sub {pct_s}' {spec_s} by {pct_f};",  # the %
            f"  sub {pct_f} {spec_s}' by {spec_f};",  # first specifier char
            f"  sub {spec_f} {spec_s}' by {spec_f};",  # rest of the specifier
        ]
        self.add_lookup("FormatSpecs", lines)

    # -- top level -------------------------------------------------------

    def add_words_global(
        self, keywords: list[str], builtins: list[str], literals: list[str]
    ) -> None:
        """All words merged per category (keyword beats builtin beats literal).

        One lookup per category replaces one per language per category, which
        cuts most of the small contextual lookups when many languages combine."""
        self._words_lookup(keywords, palette_index("keyword"), "Kw")
        self._words_lookup(builtins, palette_index("builtin"), "Bt")
        self._words_lookup(literals, palette_index("literal"), "Lt")

    def add_after_rules(self, lang: Language) -> None:
        name = self._prefix(lang)
        for i, rule in enumerate(lang.after_rules):
            self._after_rule_lookup(rule, f"{name}A{i}")
        for slot, chars in lang.symbols.items():
            self.symbol_groups.setdefault(slot, []).extend(chars)
        self.escape_chars.extend(lang.escapes)
        self.format_chars.extend(lang.formats)
        self.want_numbers = self.want_numbers or lang.numbers

    def add_word_rules(self, lang: Language) -> None:
        name = self._prefix(lang)
        for i, rule in enumerate(lang.word_rules):
            self._word_rule_lookup(rule, f"{name}W{i}")

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
        # @InRegion matches any char already colored by a comment/string/value
        # region, so a region opener inside one is suppressed.
        fsm_palettes = sorted(self.alt_palettes & FSM_PALETTES)
        if len(fsm_palettes) > 1:
            union = " ".join(f"@AllAlt{p}" for p in fsm_palettes)
            parts.append(f"@InRegion = [{union}];")
        elif fsm_palettes:
            parts.append(f"@InRegion = [@AllAlt{fsm_palettes[0]}];")
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
        builder.escape_chars.extend(lang.escapes)
        builder.format_chars.extend(lang.formats)
    # FSM grouped by palette so comments mask strings; words merged per
    # category; per-language rules after the words so `if(` stays a keyword.
    # Many languages share the same `//`, `"`, ... tokens, so dedupe them first.
    by_palette: dict[int, list[FsmToken]] = {}
    seen_tokens: set = set()
    for lang in languages:
        for token in lang.fsm_tokens:
            key = (
                tuple(token.start),
                tuple(token.end) if token.end else None,
                token.palette,
                token.color_delimiters,
                token.interpolation,
                tuple(token.interp_open),
                tuple(token.interp_close),
            )
            if key in seen_tokens:
                continue
            seen_tokens.add(key)
            by_palette.setdefault(palette_index(token.palette), []).append(token)
    for tokens in by_palette.values():
        for token in tokens:
            builder.register_stop(token)
    for palette in sorted(by_palette):
        builder.fsm_palettes.add(palette)
    # Comment/string regions run first so they mask everything inside them.
    # The `value` FSM (CSS property values) runs later, so a function name or
    # custom property in a value (`color: var(--radius)`) is colored first and
    # the value chain simply stops at it.
    value_p = palette_index("value")
    region = {p: t for p, t in by_palette.items() if p != value_p}
    values = {p: t for p, t in by_palette.items() if p == value_p}
    if region:
        builder.add_fsm(region, "FsmRegion")
    # escape sequences inside strings, after the string FSM has colored them
    builder.add_escape_lookup()
    builder.add_format_lookup()
    builder.add_words_global(
        [w for lang in languages for w in lang.keywords],
        [w for lang in languages for w in lang.builtins],
        [w for lang in languages for w in lang.literals],
    )
    # tags/selectors (after-rules) before functions/properties (word-rules),
    # so `<div>` stays a tag instead of becoming a CSS selector
    for lang in languages:
        builder.add_after_rules(lang)
    for lang in languages:
        builder.add_word_rules(lang)
    if values:
        builder.add_fsm(values, "FsmValue")
    return builder.build()
