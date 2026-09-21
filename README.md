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
browser through [Pyodide](https://pyodide.org/), so nothing is uploaded.

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

word_rules:                      # a word followed by a terminator
  - terminator: "("
    palette: function
    chars: ident                 # preset, or a literal string of characters
    max_len: 24

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
  - start: '"'
    end: '"'                     # string
    palette: string

symbols: "&|$+=~[](){};:,.?<>!%^*/@#-"
numbers: true
```

Palette slots: `comment, string, keyword, builtin, literal, function, tag,
selector, attr, symbol, number`. Character presets: `letters`, `ident`
(letters + digits + `_$`), `word` (letters + digits + `-_`), or a literal string.

Bundled languages: JavaScript, TypeScript, CSS, HTML, Python, Rust, Go, Java, C,
C++, C#, Kotlin, Swift, PHP, Ruby, Bash, SQL, JSON, YAML, Markdown.
Bundled themes: default, night, github-light, github-dark, dracula, monokai,
nord, one-dark, tokyo-night, gruvbox-dark, catppuccin-mocha, catppuccin-latte,
solarized-light, solarized-dark.

By default every character the font maps (accents, symbols, CJK) is colorable
inside comments/strings; pass `--ascii-only` for a smaller output.

## Known limitations

* **Don't disable `calt`.** Avoid `font-variant-ligatures: none` and
  `font-feature-settings: "calt" 0` — use `no-common-ligatures` instead.
* No regular expressions; matching is literal and bounded.
* A hard newline ends every comment/string region.
* Function/property names longer than `max_len` are only partially colored.
* All enabled languages' rules coexist (there is no language context).

## Development

```bash
uv run pytest
```

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).

Third-party: [neobrutalism-css](https://github.com/tbollinger/neobrutalism-css)
(MIT, vendored under `web/vendor/`); Figtree from Google Fonts (OFL); the fonts
the web app fetches on demand are under SIL OFL 1.1.
