"""Guard the generated web/data/ bundle against drifting from the sources.

Run `uv run python scripts/build_web.py` to regenerate it.
"""

from __future__ import annotations

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "web", "data")

pytestmark = pytest.mark.skipif(
    not os.path.isdir(DATA), reason="web/data not built (run scripts/build_web.py)"
)


def test_python_sources_are_in_sync():
    manifest = json.load(open(os.path.join(DATA, "manifest.json")))
    for name in manifest["python"]:
        src = open(os.path.join(ROOT, "src", "syntaxfont", name)).read()
        dst = open(os.path.join(DATA, "syntaxfont", name)).read()
        assert src == dst, f"{name} is stale; rerun scripts/build_web.py"


def test_manifest_lists_configs_and_samples():
    manifest = json.load(open(os.path.join(DATA, "manifest.json")))
    ids = {lang["id"] for lang in manifest["languages"]}
    names = {lang["name"] for lang in manifest["languages"]}
    assert {"js", "css", "html", "cpp", "csharp"} <= ids
    assert {"JavaScript", "CSS", "HTML", "C++", "C#"} <= names
    assert "default" in manifest["themes"] and "night" in manifest["themes"]
    sample_ids = {s["id"] for s in manifest["samples"]}
    assert {"js", "rust"} <= sample_ids
    assert os.path.exists(os.path.join(DATA, "samples", "rust.txt"))


def test_font_catalog_is_remote_and_https():
    catalog = json.load(open(os.path.join(ROOT, "fonts.json")))["fonts"]
    names = {f["name"] for f in catalog}
    assert {"jetbrains-mono", "fira-code"} <= names
    for font in catalog:
        assert font["url"].startswith("https://")
        assert font["family"] and font["license"]
    # the manifest exposes the same catalog to the browser
    manifest = json.load(open(os.path.join(DATA, "manifest.json")))
    assert [f["name"] for f in manifest["fonts"]] == [f["name"] for f in catalog]


def test_neobrutalism_is_vendored_and_linked():
    vendor = os.path.join(ROOT, "web", "vendor", "neobrutalism.css")
    assert os.path.exists(vendor), "vendor/neobrutalism.css missing"
    assert os.path.exists(os.path.join(ROOT, "web", "vendor", "neobrutalism.LICENSE"))
    html = open(os.path.join(ROOT, "web", "index.html")).read()
    assert 'href="vendor/neobrutalism.css"' in html
    # the neobrutalism pack expects Figtree; load it from Google Fonts
    assert "family=Figtree" in html
    # repo link on the site
    assert "https://github.com/inchei/SyntaxFont" in html


def test_engine_runs_in_a_web_worker():
    # the Pyodide engine must live in the worker, never on the main thread
    app = open(os.path.join(ROOT, "web", "app.js")).read()
    worker_path = os.path.join(ROOT, "web", "worker.js")
    assert os.path.exists(worker_path)
    worker = open(worker_path).read()
    assert 'new Worker("worker.js")' in app
    assert "loadPyodide" not in app
    assert "importScripts(" in worker and "loadPyodide" in worker
    html = open(os.path.join(ROOT, "web", "index.html")).read()
    assert "pyodide.js" not in html
