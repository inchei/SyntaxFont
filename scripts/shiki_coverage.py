"""Measure how much of Shiki's highlighting SyntaxFont reproduces.

For each bundled language, a set of probe snippets is tokenized twice:

* by Shiki (via ``scripts/shiki/compare.mjs``, run with Node), and
* by SyntaxFont (shaping a font built for that language with HarfBuzz).

Both sides are reduced to a palette *slot* per character using the same reuse
scheme (operators -> symbol, decorators -> function, ...). The script then
reports, per language and overall, the fraction of characters that Shiki colors
where SyntaxFont colors something (**any**) and where it picks the same slot
(**match**).

Usage::

    uv run python scripts/shiki_coverage.py            # summary table
    uv run python scripts/shiki_coverage.py -v         # list mismatches

Requires Node and ``scripts/shiki/node_modules`` (``npm install`` in that dir);
if missing the script exits with a clear message (and the coverage test skips).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import uharfbuzz as hb  # noqa: E402

from syntaxfont.builder import build_highlight_font  # noqa: E402
from syntaxfont.cli import load_languages, load_theme  # noqa: E402
from syntaxfont.schema import PALETTES  # noqa: E402

SHIKI_DIR = os.path.join(ROOT, "scripts", "shiki")
BASE_FONT = os.path.join(ROOT, "assets", "JetBrainsMono-Regular.ttf")

# our language file id -> Shiki language id
SHIKI_ID = {
    "js": "javascript",
    "bash": "shellscript",
}

SLOT_BY_INDEX = {v: k for k, v in PALETTES.items()}

SOURCES_DIR = os.path.join(ROOT, "tests", "coverage_sources")

# language id -> source file name (feature-dense real-world samples vendored
# from sharkdp/bat; see tests/coverage_sources/README.md)
SOURCES = {
    "bash": "bash.sh",
    "c": "c.c",
    "cpp": "cpp.cpp",
    "csharp": "csharp.cs",
    "css": "css.css",
    "go": "go.go",
    "html": "html.html",
    "java": "java.java",
    "js": "js.js",
    "json": "json.json",
    "kotlin": "kotlin.kt",
    "markdown": "markdown.md",
    "php": "php.php",
    "python": "python.py",
    "ruby": "ruby.rb",
    "rust": "rust.rs",
    "sql": "sql.sql",
    "swift": "swift.swift",
    "typescript": "typescript.ts",
    "yaml": "yaml.yaml",
}

# very long lines (minified JSON, data blobs) add noise; cap them
MAX_LINE = 120


def load_probes() -> dict[str, list[str]]:
    """Read the coverage sources into {language: [non-trivial lines]}."""
    probes: dict[str, list[str]] = {}
    for lang, filename in SOURCES.items():
        path = os.path.join(SOURCES_DIR, filename)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        probes[lang] = [
            line for line in text.splitlines() if line.strip() and len(line) < MAX_LINE
        ]
    return probes


PROBES = load_probes()


def shiki_available() -> bool:
    return shutil.which("node") is not None and os.path.isdir(
        os.path.join(SHIKI_DIR, "node_modules", "shiki")
    )


def run_shiki(payload: dict[str, list[str]]) -> dict:
    node = shutil.which("node")
    script = os.path.join(SHIKI_DIR, "compare.mjs")
    proc = subprocess.run(
        [node, script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=SHIKI_DIR,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"shiki failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def _shape(path: str, text: str) -> list[str]:
    blob = hb.Blob.from_file_path(path)
    font = hb.Font(hb.Face(blob))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    return [font.glyph_to_string(i.codepoint) for i in buf.glyph_infos]


def syntaxfont_slots(path: str, text: str) -> list[str | None]:
    """Per-character palette slot from a SyntaxFont glyph layout."""
    slots: list[str | None] = []
    for glyph in _shape(path, text):
        m = re.search(r"\.alt(\d+)$", glyph)
        slots.append(SLOT_BY_INDEX.get(int(m.group(1))) if m else None)
    # shape() drops nothing for BMP ASCII, but guard length mismatch
    slots = (slots + [None] * len(text))[: len(text)]
    return slots


def measure(languages: list[str] | None = None) -> dict:
    """Return {lang: {any_hit, match, total, mismatches}} plus an overall row."""
    ids = languages or list(PROBES)
    payload = {SHIKI_ID.get(i, i): PROBES[i] for i in ids}
    shiki = run_shiki(payload)
    theme = load_theme("default")
    results: dict = {}
    overall = {"any_hit": 0, "match": 0, "total": 0, "mismatches": [], "missed": []}
    for lang in ids:
        sid = SHIKI_ID.get(lang, lang)
        text_list = PROBES[lang]
        build_highlight_font(
            BASE_FONT,
            load_languages([lang]),
            theme,
            "/tmp/syntaxfont-shiki.ttf",
            flavor=None,
        )
        row = {"any_hit": 0, "match": 0, "total": 0, "mismatches": [], "missed": []}
        for snippet, ref in zip(text_list, shiki[sid]):
            ours = syntaxfont_slots("/tmp/syntaxfont-shiki.ttf", snippet)
            for i, ch in enumerate(snippet):
                want = ref["slots"][i]
                if want is None or ch.isspace():
                    continue
                got = ours[i]
                row["total"] += 1
                if got is not None:
                    row["any_hit"] += 1
                else:
                    row["missed"].append(
                        {"snippet": snippet, "char": ch, "pos": i, "want": want}
                    )
                if got == want:
                    row["match"] += 1
                elif len(row["mismatches"]) < 8:
                    row["mismatches"].append(
                        {"snippet": snippet, "char": ch, "pos": i, "want": want, "got": got}
                    )
        results[lang] = row
        for key in ("any_hit", "match", "total"):
            overall[key] += row[key]
        overall["mismatches"].extend(row["mismatches"])
        overall["missed"].extend(row["missed"])
    results["__overall__"] = overall
    return results


def _pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else 100.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true", help="show mismatches")
    ap.add_argument("languages", nargs="*", help="only these language ids")
    args = ap.parse_args()

    if not shiki_available():
        print(
            "Shiki is not installed. Run:\n"
            f"  (cd {os.path.relpath(SHIKI_DIR, ROOT)} && npm install)",
            file=sys.stderr,
        )
        return 2

    results = measure(args.languages or None)
    print(f"{'language':<14}{'any %':>8}{'match %':>9}{'chars':>8}")
    print("-" * 39)
    for lang, row in results.items():
        if lang == "__overall__":
            continue
        print(
            f"{lang:<14}{_pct(row['any_hit'], row['total']):>8.1f}"
            f"{_pct(row['match'], row['total']):>9.1f}{row['total']:>8}"
        )
    o = results["__overall__"]
    print("-" * 39)
    print(
        f"{'OVERALL':<14}{_pct(o['any_hit'], o['total']):>8.1f}"
        f"{_pct(o['match'], o['total']):>9.1f}{o['total']:>8}"
    )

    if args.verbose:
        from collections import Counter

        print("\nmissed by slot (shiki colors, syntaxfont does not):")
        counts = Counter(m["want"] for m in o["missed"])
        for slot, n in counts.most_common():
            print(f"  {slot:10} {n:6}")
        print("\nmissed (shiki colors, syntaxfont does not):")
        seen = set()
        for m in o["missed"]:
            key = (m["want"], m["char"])
            if key in seen:
                continue
            seen.add(key)
            print(f"  {m['snippet']!r} {m['char']!r}: want {m['want']}")
        print("\nmismatches (want = shiki slot, got = syntaxfont slot):")
        for m in o["mismatches"]:
            print(
                f"  {m['snippet']!r} pos {m['pos']} {m['char']!r}: "
                f"want {m['want']}, got {m['got']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
