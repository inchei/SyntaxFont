"""Refresh tests/coverage_sources/* from the sharkdp/bat syntax-test corpus.

The files are feature-dense real-world samples used by
``scripts/shiki_coverage.py``. Run this only when you want to pull newer
upstream versions::

    uv run python scripts/fetch_coverage_sources.py

Requires network access. See ``tests/coverage_sources/README.md`` for the
upstream path of each file and license notes.
"""

from __future__ import annotations

import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "tests", "coverage_sources")
BASE = "https://raw.githubusercontent.com/sharkdp/bat/master/tests/syntax-tests/source"

# our file name -> upstream path
FILES = {
    "bash.sh": "Bash/batgrep.sh",
    "c.c": "C/test.c",
    "cpp.cpp": "Cpp/test.cpp",
    "csharp.cs": "C-Sharp/Stack.cs",
    "css.css": "CSS/style.css",
    "go.go": "Go/main.go",
    "html.html": "HTML/test.html",
    "java.java": "Java/test.java",
    "js.js": "JavaScript/test.js",
    "json.json": "JSON/test.json",
    "kotlin.kt": "Kotlin/test.kt",
    "markdown.md": "Markdown/typescript.md",
    "php.php": "PHP/test.php",
    "python.py": "Python/battest.py",
    "ruby.rb": "Ruby/output.rb",
    "rust.rs": "Rust/output.rs",
    "sql.sql": "SQL/ims.sql",
    "swift.swift": "Swift/test.swift",
    "typescript.ts": "TypeScript/example.ts",
    "yaml.yaml": "YAML/example.yaml",
}


def main() -> int:
    os.makedirs(DEST, exist_ok=True)
    for name, path in FILES.items():
        url = f"{BASE}/{path}"
        dst = os.path.join(DEST, name)
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        with open(dst, "wb") as fh:
            fh.write(data)
        print(f"{name:<16} <- {path} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
