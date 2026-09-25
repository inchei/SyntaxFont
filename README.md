# SyntaxFont

![Shiki coverage](assets/shiki-coverage.svg)

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
supported). Pass `--keep-ligatures` to preserve the base font's ligatures (see
[Known limitations](#known-limitations)).

```bash
uv run syntaxfont build -f MyMono-Regular.otf -l js -t night -o out
```

**Variable fonts** are supported. Caveats:

* the original `GSUB` features (`ss01`…, `cv01`…, `zero`, `frac`, `locl`, …) are
  lost unless `--keep-ligatures` is used;
* in a **proportional** variable font, colored glyphs can be slightly mis-spaced
  at non-default instances.

### Isolated language highlighting

By default the selected languages share one combined `calt` feature, so
conflicting rules compete. Pass `--isolated-languages` to emit one
OpenType feature per language instead:

```bash
uv run syntaxfont build -f base.ttf -l js,python -t default -o out --isolated-languages
```

Each language gets a short, readable feature tag (OpenType caps tags at 4
characters): `js`, `py`, `css`, `rust`, … A language YAML can override it with
`feature:` (1–4 characters), which is also how a **custom** language takes part
in an isolated build:

```yaml
name: MyLang
feature: myL
keywords: [foo, bar]
```

The generated CSS includes matching `.language-<id>` rules. Activate exactly one
language feature per code block, otherwise conflicts return:

```css
.language-python {
  font-feature-settings: "py";
}
```

Isolated builds cannot currently be combined with `--keep-ligatures`. In the web
app, checking the isolated box makes choosing a sample also switch the preview to
that sample's feature.

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

The theme can be layered at runtime without rebuilding:

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

# characters always drawn in a fixed category color (like the original font);
# operators share one slot so `=>`, `!=`, `->`, `<=` are not two-toned
symbols:
  keyword:  "{}"
  function: "()[]@"
  value:    "=+%~<>!-"
  symbol:   "&|:;$\"';/?*^"
numbers: true
case_insensitive: false          # SQL-style: match keywords/builtins in upper+lower case
```

Palette slots: `comment, string, keyword, builtin, literal, function, tag,
selector, attr, symbol, number, value, escape, format`. Character presets:
`letters`, `ident` (letters + digits + `_$`), `word` (letters + digits + `-_`),
or a literal string.

<details>
<summary>Bundled languages</summary>

JavaScript, TypeScript, CSS, HTML, Python, Rust, Go, Java, C, C++, C#, Kotlin,
Swift, PHP, Ruby, Bash, SQL, JSON, YAML, Markdown.
</details>

<details>
<summary>Bundled themes</summary>

default, night, original, github-light, github-dark, dracula, monokai, nord,
one-dark, tokyo-night, gruvbox-dark, catppuccin-mocha, catppuccin-latte,
solarized-light, solarized-dark.
</details>

By default every character the font maps (accents, symbols, CJK) is colorable
inside comments/strings; pass `--ascii-only` for a smaller output.

## Known limitations

* **Ligatures are dropped by default**; pass `--keep-ligatures` to keep the base
  font's ligatures. A kept ligature is a single glyph, so it gets one colour,
  not per-part colours. Base ligatures that swallow later syntax triggers still
  win (for example Rust `#[`, HTML `</`, or CSS `--`); comment and string
  delimiters still win over ligatures.
* **Don't disable `calt`.** Avoid `font-variant-ligatures: none` and
  `font-feature-settings: "calt" 0` — use `no-common-ligatures` instead.
* No regular expressions; matching is literal and bounded.
* A hard newline ends every comment/string region.
* Escaped quotes (`\'`, `\"`, `` \` ``) do not end a string; escape sequences
  (`\n`, `\t`, `\\`, `\uXXXX`, ...) use the `escape` palette (set `escapes:`).
* printf-style format specifiers (`%s`, `%zu`, `%02d`, ...) use the `format`
  palette (defaults to `escape`; set `formats:`).
* String interpolation is bounded; a very long or expression-heavy `${...}` may
  not resume (set `interpolation:`).
* Function/property names longer than `max_len` are only partially colored.
* All enabled languages' rules coexist (there is no language context), so
  overlapping rules are ambiguous; reusing a token for different purposes warns
  in the CLI and web UI. `--isolated-languages` avoids this by selecting one
  language feature per block instead.
* Without `--keep-ligatures`, `ccmp`/`locl`/`rlig` are dropped, so a base font's
  complex-script shaping (Arabic, Indic) will not work.

Not implemented:

* regular-expression literals (JS/Ruby/PHP) and nested block comments;
* prefix-triggered interpolation (Python `f"..."`, C# `$"..."`);
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
uv run python scripts/shiki_coverage.py --badge assets/shiki-coverage.svg
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
