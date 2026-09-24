// Tokenize snippets with Shiki and emit, for each character, the SyntaxFont
// palette slot its TextMate scope maps to. Reads {lang: [snippets]} on stdin
// and writes {lang: [{snippet, slots: [...]}]} to stdout. Run via
// scripts/shiki_coverage.py, which pairs this with SyntaxFont's own output.
import { createHighlighter } from "shiki";
import { readFileSync } from "node:fs";

// TextMate scope prefix -> SyntaxFont palette slot (mirrors the deliberate
// reuse scheme in the language YAMLs: operators -> symbol, decorators and
// attributes -> function, YAML keys -> attr, plain scalars -> value, ...).
const SCOPE_RULES = [
  [/comment/, "comment"],
  [/(string|regexp|character\.quoted)/, "string"],
  [/constant\.character\.escape/, "escape"],
  [
    /(storage|keyword|control|conditional|directive|operator\.keyword)/,
    "keyword",
  ],
  [/(constant\.(color|other\.color))/, "number"],
  [
    /(support\.(function|class|type|constant|variable)|builtin|variable\.language)/,
    "builtin",
  ],
  [/(constant\.(numeric|language|character)|literal|boolean|\bnull\b)/, "literal"],
  [/(entity\.name\.function|support\.function|variable\.function|meta\.function-call)/, "function"],
  [/(entity\.name\.(tag|type)|support\.type|entity\.name\.class)/, "tag"],
  [
    /(entity\.other\.attribute-name|variable\.other\.property|support\.type\.property|meta\.object-literal\.key|entity\.name\.property)/,
    "attr",
  ],
  [/(variable|meta\.definition\.variable|entity\.name\.variable)/, "builtin"],
  [/constant\.numeric/, "number"],
  [/punctuation/, "symbol"],
];

// Language-specific overrides applied before the generic rules, since our YAML
// reuses slots differently from Shiki's scope names.
const LANG_RULES = {
  rust: [
    [/meta\.attribute/, "function"], // `#[derive]` -> our function palette
    [/entity\.name\.type/, "builtin"], // Rust types -> our builtin palette
  ],
  css: [
    [/meta\.selector/, "selector"],
    [/entity\.name\.tag\.css/, "selector"],
    [/support\.type\.property/, "attr"],
    [/constant\.other\.color/, "number"],
  ],
  yaml: [
    [/entity\.name\.tag\.yaml/, "attr"], // keys -> attr
    [/string/, "value"], // plain scalars -> value
    [/constant\.language/, "literal"],
  ],
};

function slotFor(scopes, lang) {
  const overrides = LANG_RULES[lang] || [];
  for (let i = scopes.length - 1; i >= 0; i--) {
    for (const [re, slot] of overrides) if (re.test(scopes[i])) return slot;
  }
  for (let i = scopes.length - 1; i >= 0; i--) {
    for (const [re, slot] of SCOPE_RULES) if (re.test(scopes[i])) return slot;
  }
  return null;
}

async function main() {
  const input = JSON.parse(readFileSync(0, "utf8"));
  const langs = Object.keys(input);
  const highlighter = await createHighlighter({
    themes: ["github-light"],
    langs,
  });
  const out = {};
  for (const lang of langs) {
    out[lang] = [];
    for (const snippet of input[lang]) {
      const { tokens } = highlighter.codeToTokens(snippet, {
        lang,
        theme: "github-light",
        includeExplanation: true,
      });
      const slots = new Array(snippet.length).fill(null);
      for (const line of tokens) {
        for (const token of line) {
          const scopes = (token.explanation || []).flatMap((e) =>
            (e.scopes || []).map((s) => s.scopeName)
          );
          const slot = slotFor(scopes, lang);
          if (slot === null) continue;
          const start = token.offset ?? 0;
          for (let i = start; i < start + token.content.length && i < slots.length; i++)
            slots[i] = slot;
        }
      }
      out[lang].push({ snippet, slots });
    }
  }
  process.stdout.write(JSON.stringify(out));
}
main();
