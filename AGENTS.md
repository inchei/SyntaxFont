# AGENTS.md

SyntaxFont — build a font with built-in syntax highlighting (COLR/CPAL + calt)
from a base font, language rules and a theme. Python (fontTools) core plus a
static web app that runs the same package in the browser via Pyodide.
License: GPL-3.0-or-later (see LICENSE).

## Commands

```bash
uv sync                  # install deps
uv run pytest            # run tests

uv run syntaxfont build -f assets/JetBrainsMono-Regular.ttf -l js,css,html -t default -o dist

uvx ruff@0.13.3 check .            # lint
uvx ruff@0.13.3 check --fix .      # lint auto-fix
uvx ruff@0.13.3 format .           # format
uvx ruff@0.13.3 format --check .   # format check

uv run python scripts/build_web.py        # bundle sources + configs into web/data
uv run python -m http.server -d web 8000  # serve over http, not file://
```

Ruff is run via `uvx` (pinned) so no install step is needed; config lives in
`pyproject.toml`. The pre-commit hook (`.husky/pre-commit`) runs Ruff lint +
format check on staged Python files and `node --check` on staged JS — quality
is enforced here, not in CI. Setup after clone: `git config core.hooksPath .husky`.
CI (`.github/workflows/pages.yml`) only builds and deploys GitHub Pages.

## Conventions

- Python via uv only.
- Conventional commits, one-line English title: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`, `chore: ...`.
- NEVER commit unless the user explicitly asks.
- Long-running command output goes to files under `/tmp/opencode/`; read/search the file instead of re-running with `head`/`tail`/`grep`.
- Edit code files with the Edit tool only; Python/shell scripts may read/analyze output but must never write code files.
- All code comments in English.
- No browser smoke tests or screenshots unless the user asks.
