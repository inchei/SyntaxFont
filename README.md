# SyntaxFont

Build a font with **built-in syntax highlighting** from any base font — inspired
by [Font with Built-In Syntax Highlighting](https://blog.glyphdrawing.club/font-with-built-in-syntax-highlighting/).

```
base font  +  language rules (YAML)  +  theme (YAML)  ->  COLR/calt woff2 + CSS
```

Highlighting lives entirely in OpenType (`COLR`/`CPAL` + `calt`): no JavaScript,
no per-token markup. It works in `<pre>`, `<code>` and `<textarea>`, and themes
switch at runtime from CSS.

**[Web app →](https://inchei.github.io/SyntaxFont/)** ·
[Source on GitHub](https://github.com/inchei/SyntaxFont)

## Quick start

```bash
uv sync
uv run syntaxfont build -f assets/JetBrainsMono-Regular.ttf -l js,css,html -t default -o dist
```

This writes `dist/<font>-highlight.woff2` and `dist/highlight.css`.

## Web app (WASM)

A client-side generator lives in `web/`: it runs this same package in the
browser through [Pyodide](https://pyodide.org/), so nothing is uploaded. The
engine runs in a Web Worker (`web/worker.js`), so the page stays responsive
while fonts generate — this needs serving over http(s), not `file://`.

```bash
uv run python scripts/build_web.py      # bundle sources + configs into web/data
uv run python -m http.server -d web 8000
```

It deploys to GitHub Pages via `.github/workflows/pages.yml` (enable
**Settings → Pages → Source: GitHub Actions** once).

## Customising

### 1. Base font

Pass any monospace TTF or OTF with `-f` (TrueType and CFF/CFF2 outlines are
supported). Glyph names are read from the font's cmap. The font's existing
`GSUB` is replaced by the generated `calt`; `GPOS` and everything else is kept.

```bash
uv run syntaxfont build -f MyMono-Regular.otf -l js -t night -o out
```

### 2. Theme

`themes/*.yaml` maps semantic slots to colors; omitted slots fall back to gray.

```yaml
name: my-theme
colors:
  comment:  "#6a737d"
  string:   "#032f62"
  keyword:  "#d73a49"
  builtin:  "#005cc5"
  literal:  "#005cc5"
  function: "#6f42c1"
  tag:      "#22863a"
  selector: "#22863a"
  attr:     "#b31d28"
  symbol:   "#24292e"
  number:   "#005cc5"
```

The theme is baked into the font's CPAL palette **and** emitted as
`@font-palette-values`, so extra themes can be layered without rebuilding:

```bash
uv run syntaxfont build -f base.ttf -l js -t default --palettes night -o out
```

```css
code { font-palette: --default; }
body.dark code { font-palette: --night; }
```

### 3. Language / highlight rules

`languages/*.yaml` declares keywords/literals/builtins, function/property rules,
comment/string regions and always-colored symbols:

```yaml
name: JavaScript  # display name; the file name (js.yaml) is the id

keywords: [if, for, return, const, ...]
literals: ["true", "false", "null"]
builtins: [console, Math, JSON, ...]

word_rules:                      # a word followed by terminators
  - terminators: [">", "{", "~", "+"]
    palette: selector
    chars: word
    max_len: 30
    allow_space: true            # also match `div >`

after_rules:                     # a word preceded by a sequence
  - after: ["<", "</"]
    palette: tag
    chars: word

fsm_tokens:                      # variable-length regions
  - start: "//"                  # line comment
    palette: comment
  - start: "/*"
    end: "*/"                    # block comment
    palette: comment
  - start: ":"
    end: ";"                     # CSS value; delimiters stay uncolored
    palette: value
    color_delimiters: false
  - start: '"'
    end: '"'                     # string
    palette: string

# characters always drawn in a fixed category color (like the original font)
symbols:
  keyword:  "{}"
  function: "()[]@"
  value:    "=+%~"
  symbol:   "&|:;$<>\"';/"
numbers: true
case_insensitive: false          # SQL-style: match keywords/builtins in upper+lower case
```

Palette slots: `comment, string, keyword, builtin, literal, function, tag,
selector, attr, symbol, number, value, escape, format`. Character presets:
`letters`, `ident` (letters + digits + `_$`), `word` (letters + digits + `-_`),
or a literal string.

Bundled languages: JavaScript, TypeScript, CSS, HTML, Python, Rust, Go, Java, C,
C++, C#, Kotlin, Swift, PHP, Ruby, Bash, SQL, JSON, YAML, Markdown.
Bundled themes: default, night, original, github-light, github-dark, dracula,
monokai, nord, one-dark, tokyo-night, gruvbox-dark, catppuccin-mocha,
catppuccin-latte, solarized-light, solarized-dark.

By default every character the font maps (accents, symbols, CJK) is colorable
inside comments/strings; pass `--ascii-only` for a smaller output.

## Known limitations

* **Don't disable `calt`.** Avoid `font-variant-ligatures: none` and
  `font-feature-settings: "calt" 0` — use `no-common-ligatures` instead.
* No regular expressions; matching is literal and bounded.
* Escaped quotes (`\'`, `\"`, `` \` ``) do **not** end a string, and escape
  sequences (`\n`, `\t`, `\\`, `\uXXXX`, ...) are colored with the `escape`
  palette — both a step beyond the original font, which stops at escaped quotes
  and has no escape handling. The escape character set is configurable per
  language via `escapes:`.
* printf-style format specifiers (`%s`, `%zu`, `%02d`, ...) inside strings are
  colored with the `format` palette (defaults to the `escape` color); the
  specifier character set is configurable per language via `formats:`.
* A hard newline ends every comment/string region.
* **String interpolation** colors the literal text as a string and pauses at
  the interpolation opener, so the expression is highlighted as code; the string
  resumes after the matching close. The delimiters are configurable per language
  (`interpolation: {open: '\\(', close: ')'}`), covering JS/TS/Kotlin `` ${} ``,
  Swift `\(...)`, Ruby `#{}`, PHP `{$...}` and Bash `${...}`. Because OpenType
  can't track unbounded state, the resume matches a bounded, expression-like
  body; a very long or nested `${...}` may not resume.
* Regions nest correctly: a `#`/`//` inside a string (e.g. a URL) stays string
  colored, and a quote inside a comment stays comment colored.
* Function/property names longer than `max_len` are only partially colored.
* All enabled languages' rules coexist (there is no language context), so
  overlapping rules are ambiguous. Combining languages that reuse a token for
  different purposes prints a warning (CLI) and shows one in the web UI. The
  common case is `#`: it is a comment in Python/Bash/Ruby/YAML/PHP but a
  preprocessor/attribute trigger in C/C++/Rust, so with both enabled whichever
  rule runs first wins (currently the comment).

Because matching is literal and bounded, the following TextMate/Shiki features
are **not** implemented:

* regular-expression literals (JS/Ruby/PHP) and nested block comments;
* prefix-triggered interpolation (Python `f"..."`, C# `$"..."`), because a
  plain string and an f-string are indistinguishable without the prefix;
* JSX/TSX and other grammar-embedded languages;
* heredocs (`<<EOF`, `<<~SQL`) and multi-line strings/comments;
* one grammar embedded in another (HTML `<script>`/`<style>`, Markdown code
  fences, PHP in HTML);
* semantic/type-name heuristics (coloring identifiers that resolve to types).

## Development

```bash
uv run pytest
```

### Shiki alignment coverage

`scripts/shiki_coverage.py` measures how much of [Shiki](https://shiki.style)'s
highlighting SyntaxFont reproduces on **real-world code**. It tokenizes the
feature-dense sample files in `tests/coverage_sources/` (one per language,
vendored from the [sharkdp/bat](https://github.com/sharkdp/bat) syntax-test
corpus) with Shiki (via Node) and with SyntaxFont (by shaping a built font),
reduces both to palette slots, and reports a per-language and overall coverage
percentage.

```bash
(cd scripts/shiki && npm install)              # once
uv run python scripts/shiki_coverage.py        # summary table
uv run python scripts/shiki_coverage.py -v     # missed-by-slot + examples
uv run python scripts/fetch_coverage_sources.py  # refresh the sample files
```

`-v` prints a **missed-by-slot** breakdown. Most misses fall under
`builtin`/`symbol`/`tag` (Shiki colors every identifier, operator and type
reference — it has a symbol table, we don't), which is structural; misses under
`comment`/`string`/`keyword`/`function` are the actionable ones.

The `tests/test_shiki_coverage.py` test asserts a minimum coverage floor and
skips automatically when Shiki is not installed. CI installs it (see
`.github/workflows/pages.yml`).

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).

Third-party: [neobrutalism-css](https://github.com/tbollinger/neobrutalism-css)
(MIT, vendored under `web/vendor/`); Figtree from Google Fonts (OFL); the fonts
the web app fetches on demand are under SIL OFL 1.1.
