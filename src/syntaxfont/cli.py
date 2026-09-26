"""Command line interface for syntaxfont."""

from __future__ import annotations

import argparse
import os
import sys

import yaml

from .builder import build_highlight_font
from .conflicts import detect_conflicts
from .palette import css_font_palette_values, css_language_features
from .schema import (
    Language,
    Theme,
    isolated_language_features,
    parse_language,
    parse_theme,
)


def _package_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve(name: str, kind: str) -> str:
    """Resolve a config name (js) or path (./js.yaml) to a file path."""
    if os.path.exists(name):
        return name
    base = _package_dir()
    candidate = os.path.join(base, kind, f"{name}.yaml")
    if os.path.exists(candidate):
        return candidate
    raise FileNotFoundError(f"unknown {kind[:-1]} {name!r}")


def _load(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_languages(names: list[str]) -> list[Language]:
    languages = []
    for name in names:
        path = _resolve(name, "languages")
        language_id = _bundled_language_id(path, name)
        languages.append(parse_language(_load(path), language_id))
    return languages


def _bundled_language_id(path: str, name: str) -> str | None:
    """The stable id (YAML filename stem) for a bundled language, else None."""
    package_languages = os.path.abspath(os.path.join(_package_dir(), "languages"))
    if os.path.dirname(os.path.abspath(path)) != package_languages:
        return None
    return os.path.splitext(os.path.basename(path))[0]


def load_theme(name: str) -> Theme:
    return parse_theme(_load(_resolve(name, "themes")))


def default_family(font_path: str) -> str:
    try:
        from fontTools.ttLib import TTFont

        base = TTFont(font_path, lazy=True)
        name = (base["name"].getDebugName(1) or "").strip() if "name" in base else ""
    except Exception:
        name = ""
    if name:
        return f"{name} Syntax"
    stem = os.path.splitext(os.path.basename(font_path))[0]
    return f"{stem} Syntax"


def cmd_build(args: argparse.Namespace) -> int:
    languages = load_languages(args.languages)
    language_ids = [lang.id for lang in languages] if args.isolated_languages else None
    theme = load_theme(args.theme)
    extra_themes = [load_theme(t) for t in (args.palettes or [])]

    if args.isolated_languages:
        feature_by_id = isolated_language_features(language_ids, languages)
        for rule_id, feature_tag in feature_by_id.items():
            print(f"{rule_id}: {feature_tag}")
    else:
        for warning in detect_conflicts(languages):
            print(f"warning: {warning}")

    os.makedirs(args.output, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.font))[0]
    suffix = args.name_suffix or "-highlight"
    out_font = os.path.join(args.output, f"{stem}{suffix}.woff2")
    family = default_family(args.font)

    build_highlight_font(
        args.font,
        languages,
        theme,
        out_font,
        flavor="woff2",
        emit_fea=os.path.join(args.output, "features.fea") if args.emit_fea else None,
        color_all=not args.ascii_only,
        extra_chars=args.extra_chars or "",
        keep_ligatures=args.keep_ligatures,
        language_ids=language_ids,
        isolated_languages=args.isolated_languages,
    )

    css = [
        "@font-face {",
        f"  font-family: '{family}';",
        f"  src: url('{os.path.basename(out_font)}') format('woff2');",
        "}",
        "",
        "code, pre {",
        f"  font-family: '{family}', monospace !important;",
        "}",
        "",
    ]
    if args.isolated_languages:
        css.append(css_language_features(feature_by_id))
    css.append(css_font_palette_values(family, [theme, *extra_themes]))
    with open(os.path.join(args.output, "highlight.css"), "w") as f:
        f.write("\n".join(css))

    print(f"wrote {out_font}")
    print(f"wrote {os.path.join(args.output, 'highlight.css')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="syntaxfont")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="build a highlight font")
    build.add_argument("-f", "--font", required=True, help="base TTF/OTF font")
    build.add_argument(
        "-l",
        "--languages",
        required=True,
        help="comma-separated language names or YAML paths",
    )
    build.add_argument("-t", "--theme", default="default", help="theme name or YAML path")
    build.add_argument("-o", "--output", default="dist", help="output directory")
    build.add_argument(
        "--palettes",
        help="comma-separated extra themes to emit as @font-palette-values",
    )
    build.add_argument("--name-suffix", default="-highlight")
    build.add_argument("--emit-fea", action="store_true", help="also write features.fea")
    build.add_argument(
        "--ascii-only",
        action="store_true",
        help="only color ASCII inside comments/strings (smaller output; default is to color every mapped character)",
    )
    build.add_argument(
        "--extra-chars",
        help="extra characters to color inside comments/strings (e.g. '，。！')",
    )
    build.add_argument(
        "--keep-ligatures",
        action="store_true",
        help="keep the base font's ligatures (e.g. Fira Code ->, =>) instead of dropping them",
    )
    build.add_argument(
        "--isolated-languages",
        action="store_true",
        help="emit one OpenType stylistic-set feature per bundled language instead of one combined calt",
    )
    build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    if args.command == "build":
        args.languages = [s.strip() for s in args.languages.split(",") if s.strip()]
        if args.palettes:
            args.palettes = [s.strip() for s in args.palettes.split(",") if s.strip()]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
