"""Detect rule conflicts when several languages are combined.

All enabled languages' rules coexist in one `calt` feature (there is no
language context), so two languages can fight over the same token. These
warnings tell the user which combinations are ambiguous.
"""

from __future__ import annotations

from .schema import Language


def _fmt_uses(uses: list[tuple[str, str]]) -> str:
    return ", ".join(f"{lang} ({palette})" for lang, palette in uses)


def detect_conflicts(languages: list[Language], limit: int = 12) -> list[str]:
    """Return human-readable warnings for ambiguous cross-language rules.

    Trigger conflicts (a token that means different things) come first, then
    palette/word/symbol clashes. ``limit`` caps the list; ``0`` means no cap.
    """
    warnings: list[str] = []

    fsm: dict[str, list[tuple[str, str]]] = {}
    after: dict[str, list[tuple[str, str]]] = {}
    words: dict[str, list[tuple[str, str]]] = {}
    symbols: dict[str, list[tuple[str, str]]] = {}

    for lang in languages:
        for token in lang.fsm_tokens:
            fsm.setdefault("".join(token.start), []).append((lang.name, token.palette))
        for rule in lang.after_rules:
            for seq in rule.after:
                after.setdefault("".join(seq), []).append((lang.name, rule.palette))
        for word in lang.keywords:
            words.setdefault(word, []).append((lang.name, "keyword"))
        for word in lang.builtins:
            words.setdefault(word, []).append((lang.name, "builtin"))
        for word in lang.literals:
            words.setdefault(word, []).append((lang.name, "literal"))
        for slot, chars in lang.symbols.items():
            for ch in chars:
                symbols.setdefault(ch, []).append((lang.name, slot))

    # 1. a token that opens a region in one language but triggers a word rule
    #    in another (e.g. `#` comment vs `#include` preprocessor)
    for key in sorted(set(fsm) & set(after)):
        fsm_uses, after_uses = fsm[key], after[key]
        if {p for _, p in fsm_uses} != {p for _, p in after_uses}:
            warnings.append(
                f"{key!r} opens a region in {_fmt_uses(fsm_uses)} but is a word "
                f"trigger in {_fmt_uses(after_uses)} — only the first rule wins"
            )

    # 2. the same token opens regions with different palettes
    for key, uses in sorted(fsm.items()):
        palettes = {p for _, p in uses}
        if len(palettes) > 1:
            warnings.append(
                f"{key!r} opens different regions: {_fmt_uses(uses)} — one wins"
            )

    # 3. the same word is in different categories
    for word, uses in sorted(words.items()):
        cats = {c for _, c in uses}
        if len(cats) > 1:
            warnings.append(
                f"{word!r} is colored differently: {_fmt_uses(uses)} — one wins"
            )

    # 4. the same symbol has different category colors
    for ch, uses in sorted(symbols.items()):
        slots = {s for _, s in uses}
        if len(slots) > 1:
            warnings.append(
                f"symbol {ch!r} has different colors: {_fmt_uses(uses)} — one wins"
            )

    if limit and len(warnings) > limit:
        extra = len(warnings) - limit
        warnings = warnings[:limit] + [f"…and {extra} more conflict(s)"]

    return warnings
