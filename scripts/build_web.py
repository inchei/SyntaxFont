#!/usr/bin/env python3
"""Assemble the static WASM web app under web/data/.

Copies the pure-Python package sources, the bundled language/theme configs and
the sample font so the site can be served as plain static files.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from syntaxfont.schema import ISOLATED_LANGUAGE_FEATURES
DATA = os.path.join(ROOT, "web", "data")

PACKAGE_FILES = [
    "__init__.py",
    "schema.py",
    "palette.py",
    "calt_gen.py",
    "builder.py",
    "conflicts.py",
    "webapp.py",
]


def copy_package() -> list[str]:
    src = os.path.join(ROOT, "src", "syntaxfont")
    dst = os.path.join(DATA, "syntaxfont")
    os.makedirs(dst, exist_ok=True)
    for name in PACKAGE_FILES:
        shutil.copyfile(os.path.join(src, name), os.path.join(dst, name))
    return PACKAGE_FILES


def copy_dir(kind: str) -> list[str]:
    src = os.path.join(ROOT, kind)
    dst = os.path.join(DATA, kind)
    os.makedirs(dst, exist_ok=True)
    names = []
    for fname in sorted(os.listdir(src)):
        if fname.endswith(".yaml"):
            shutil.copyfile(os.path.join(src, fname), os.path.join(dst, fname))
            names.append(fname[: -len(".yaml")])
    return names


def copy_languages() -> list[dict]:
    """Copy language YAMLs and expose {id, name}.

    The filename stem is the id (used to fetch the file); `name` is the display
    name from the YAML."""
    src = os.path.join(ROOT, "languages")
    dst = os.path.join(DATA, "languages")
    os.makedirs(dst, exist_ok=True)
    out = []
    for fname in sorted(os.listdir(src)):
        if not fname.endswith(".yaml"):
            continue
        shutil.copyfile(os.path.join(src, fname), os.path.join(dst, fname))
        with open(os.path.join(src, fname)) as fh:
            data = yaml.safe_load(fh)
        slug = fname[: -len(".yaml")]
        out.append({"id": slug, "name": data.get("name", slug)})
    return out


def copy_samples(lang_names: dict[str, str]) -> list[dict]:
    src = os.path.join(ROOT, "samples")
    dst = os.path.join(DATA, "samples")
    os.makedirs(dst, exist_ok=True)
    out = []
    for fname in sorted(os.listdir(src)):
        if fname.endswith(".txt"):
            shutil.copyfile(os.path.join(src, fname), os.path.join(dst, fname))
            slug = fname[: -len(".txt")]
            out.append({"id": slug, "name": lang_names.get(slug, slug)})
    return out


def load_fonts() -> list[dict]:
    """Remote font catalog (not bundled; fetched by the browser on demand)."""
    with open(os.path.join(ROOT, "fonts.json")) as fh:
        return json.load(fh)["fonts"]


def main() -> int:
    if os.path.isdir(DATA):
        shutil.rmtree(DATA)
    os.makedirs(DATA, exist_ok=True)
    languages = copy_languages()
    lang_names = {lang["id"]: lang["name"] for lang in languages}
    manifest = {
        "python": copy_package(),
        "languages": languages,
        "language_features": ISOLATED_LANGUAGE_FEATURES,
        "themes": copy_dir("themes"),
        "samples": copy_samples(lang_names),
        "fonts": load_fonts(),
    }
    with open(os.path.join(DATA, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    # keep Jekyll from ignoring data/syntaxfont/__init__.py if Pages ever
    # serves this directory as a branch instead of an Actions artifact
    open(os.path.join(ROOT, "web", ".nojekyll"), "w").close()
    print(f"wrote {DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
