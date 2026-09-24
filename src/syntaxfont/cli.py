"""Command line interface for syntaxfont."""

from __future__ import annotations

import argparse
import os
import sys

import yaml

from .builder import build_highlight_font
from .conflicts import detect_conflicts
from .palette import css_font_palette_values
from .schema import Language, Theme, parse_language, parse_theme


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
    return [parse_language(_load(_resolve(n, "languages"))) for n in names]


def load_theme(name: str) -> Theme:
    return parse_theme(_load(_resolve(name, "themes")))


def cmd_build(args: argparse.Namespace) -> int:
    languages = load_languages(args.languages)
    theme = load_theme(args.theme)
    extra_themes = [load_theme(t) for t in (args.palettes or [])]

    for warning in detect_conflicts(languages):
        print(f"warning: {warning}")

    os.makedirs(args.output, exist_ok=True)
    stem = os.path.splitext(os.path.basename(args.font))[0]
    suffix = args.name_suffix or "-highlight"
    out_font = os.path.join(args.output, f"{stem}{suffix}.woff2")

    build_highlight_font(
        args.font,
        languages,
        theme,
        out_font,
        flavor="woff2",
        emit_fea=os.path.join(args.output, "features.fea") if args.emit_fea else None,
        color_all=not args.ascii_only,
        extra_chars=args.extra_chars or "",
    )

    family = args.family or f"{stem}{suffix}"
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
    build.add_argument("--family", help="font-family name to use in generated CSS")
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
    build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    if args.command == "build":
        args.languages = [s.strip() for s in args.languages.split(",") if s.strip()]
        if args.palettes:
            args.palettes = [s.strip() for s in args.palettes.split(",") if s.strip()]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
