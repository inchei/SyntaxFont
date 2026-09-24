# Coverage source files

These are real-world, feature-dense example files, one per language, used by
`scripts/shiki_coverage.py` to measure how much of Shiki's highlighting
SyntaxFont reproduces on realistic code (rather than hand-written snippets that
might miss features we never thought to test).

They are vendored from the [sharkdp/bat](https://github.com/sharkdp/bat)
`syntax-tests` corpus (MIT / Apache-2.0), which maintains a dedicated,
feature-covering sample per language. To refresh them, re-run
`scripts/fetch_coverage_sources.py`.

| file | upstream path |
|------|---------------|
| bash.sh | `Bash/batgrep.sh` |
| c.c | `C/test.c` |
| cpp.cpp | `Cpp/test.cpp` |
| csharp.cs | `C-Sharp/Stack.cs` |
| css.css | `CSS/style.css` |
| go.go | `Go/main.go` |
| html.html | `HTML/test.html` |
| java.java | `Java/test.java` |
| js.js | `JavaScript/test.js` |
| json.json | `JSON/test.json` |
| kotlin.kt | `Kotlin/test.kt` |
| markdown.md | `Markdown/typescript.md` |
| php.php | `PHP/test.php` |
| python.py | `Python/battest.py` |
| ruby.rb | `Ruby/output.rb` |
| rust.rs | `Rust/output.rs` |
| sql.sql | `SQL/ims.sql` |
| swift.swift | `Swift/test.swift` |
| typescript.ts | `TypeScript/example.ts` |
| yaml.yaml | `YAML/example.yaml` |

License: these files are distributed under bat's dual MIT/Apache-2.0 license;
see <https://github.com/sharkdp/bat/blob/master/LICENSE-MIT> and
<https://github.com/sharkdp/bat/blob/master/LICENSE-APACHE>.
