"use strict";
/* Thin client: the Pyodide build engine lives in worker.js so heavy builds
 * never block the page. Requires serving over http(s); file:// blocks workers. */

const $ = (id) => document.getElementById(id);

let manifest = null;
let baseFontBytes = null;
let lastResult = null;
let lastIsolatedBuild = false;
let worker = null;
let engineReady = false;
let seq = 0;
const pending = new Map();

function rpc(cmd, data) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, cmd, ...(data || {}) });
  });
}

function onWorkerMessage(e) {
  const msg = e.data || {};
  const entry = pending.get(msg.id);
  if (msg.type === "log") {
    log(msg.line);
    return;
  }
  if (!entry) return;
  pending.delete(msg.id);
  if (msg.type === "error") entry.reject(new Error(msg.message));
  else entry.resolve(msg);
}

function log(line) {
  const el = $("log");
  el.textContent += (el.textContent ? "\n" : "") + line;
  el.scrollTop = el.scrollHeight;
}

function abToB64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(s);
}

function b64ToU8(b64) {
  const bin = atob(b64);
  const u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}

function paletteIdent(name) {
  return "--" + name.replace(/[^A-Za-z0-9_-]/g, "-").replace(/^-+|-+$/g, "");
}

let baseFontLabel = "";

function setFont(buffer, label) {
  baseFontBytes = buffer;
  baseFontLabel = label;
  $("font-name").textContent = `${label} (${(buffer.byteLength / 1024).toFixed(0)} KB)`;
  applyDefaultFamily();
  updateGenerateState();
}

// default the family name to "<original family>-Syntax"; the original name
// comes from fontTools (name table) once the engine is up, else the filename
function applyDefaultFamily() {
  let original = baseFontLabel.replace(/\.[^.]+$/, "") || "SyntaxFont";
  $("family").value = `${original}-Syntax`;
  if (engineReady && baseFontBytes) {
    rpc("family", { font_b64: abToB64(baseFontBytes) })
      .then((msg) => {
        if (msg.name) $("family").value = `${msg.name}-Syntax`;
      })
      .catch((err) => console.warn("could not read family name:", err));
  }
}

async function loadBundledFont(name) {
  const entry = manifest.fonts.find((f) => f.name === name) || manifest.fonts[0];
  if (!entry) return;
  log(`Downloading ${entry.family}…`);
  try {
    const res = await fetch(entry.url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buffer = await res.arrayBuffer();
    setFont(buffer, `${entry.family}.ttf`);
    log(`Loaded ${entry.family} (${(buffer.byteLength / 1024).toFixed(0)} KB)`);
  } catch (err) {
    log(`Could not download ${entry.family}: ${err} — upload a .ttf instead.`);
  }
}

function updateGenerateState() {
  $("generate").disabled = !(engineReady && manifest && baseFontBytes);
}

// styled status chip using neobrutalism-css's filled-chip mechanism
function setEngine(state, text) {
  const el = $("engine");
  el.className = "nb-chip nb-pill";
  el.textContent = text;
  const color = {
    loading: "var(--nb-info)",
    ready: "var(--nb-success)",
    error: "var(--nb-danger)",
  }[state];
  el.style.setProperty("--nb-pill-color", color);
}

async function initEngine() {
  setEngine("loading", "Loading engine…");
  try {
    worker = new Worker("worker.js");
    worker.onmessage = onWorkerMessage;
    worker.onerror = (ev) => {
      console.error(ev);
      setEngine("error", "Engine failed to load");
      log("Error: worker failed to start (serve over http, not file://).");
    };
    const msg = await rpc("init");
    manifest = msg.manifest;
    engineReady = true;
    populateControls();
    if (baseFontBytes) applyDefaultFamily();
    setEngine("ready", "Engine ready");
    updateGenerateState();
    refreshWarnings();
  } catch (err) {
    console.error(err);
    setEngine("error", "Engine failed to load");
    log("Error: " + err);
  }
}

function populateControls() {
  const langs = $("languages");
  langs.innerHTML = "";
  const defaultOn = new Set(["js", "css", "html"]);
  for (const lang of manifest.languages) {
    const label = document.createElement("label");
    label.className = "nb-checkbox";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "nb-checkbox__input";
    cb.value = lang.id;
    cb.checked = defaultOn.has(lang.id);
    cb.addEventListener("change", scheduleWarnings);
    const box = document.createElement("span");
    box.className = "nb-checkbox__box";
    const text = document.createElement("span");
    text.textContent = lang.name;
    label.append(cb, box, text);
    langs.append(label);
  }

  const themes = $("themes");
  themes.innerHTML = "";
  const defaultThemes = new Set(["default", "night"]);
  for (const name of manifest.themes) {
    const label = document.createElement("label");
    label.className = "nb-checkbox";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "nb-checkbox__input";
    cb.value = name;
    cb.checked = defaultThemes.has(name);
    const box = document.createElement("span");
    box.className = "nb-checkbox__box";
    const text = document.createElement("span");
    text.textContent = name;
    label.append(cb, box, text);
    themes.append(label);
  }

  const sample = $("sample-code");
  sample.innerHTML = "";
  for (const s of manifest.samples) {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    sample.append(opt);
  }
  const jsSample = manifest.samples.find((s) => s.id === "js");
  sample.value = jsSample ? jsSample.id : manifest.samples[0]?.id;
  loadSampleCode(sample.value);

  const fonts = $("bundled-font");
  fonts.innerHTML = "";
  for (const font of manifest.fonts) {
    const opt = document.createElement("option");
    opt.value = font.name;
    opt.textContent = font.family;
    fonts.append(opt);
  }
  const preferred = manifest.fonts.find((f) => f.name === "jetbrains-mono");
  fonts.value = preferred ? preferred.name : manifest.fonts[0]?.name;
  loadBundledFont(fonts.value);
}

async function loadSampleCode(name) {
  if (!name) return;
  const text = await fetchText(`data/samples/${name}.txt`);
  $("preview").value = text;
  // make sure the matching language is enabled so the sample is highlighted
  const cb = document.querySelector(`#languages input[value="${name}"]`);
  if (cb) cb.checked = true;
  applySampleFeature(name);
  scheduleWarnings();
}

function applySampleFeature(sampleId) {
  const preview = $("preview");
  const feature =
    lastIsolatedBuild && lastResult?.language_features
      ? lastResult.language_features[sampleId]
      : null;
  // An isolated build has no combined `calt`; activate exactly the sample's
  // language feature so other languages cannot interfere with the preview.
  preview.style.fontFeatureSettings = feature ? `"${feature}"` : "";
}

async function fetchText(url) {
  return (await fetch(url)).text();
}

async function generate() {
  if (!baseFontBytes) return;
  $("generate").disabled = true;
  $("log").textContent = "";
  try {
    const selected = [...document.querySelectorAll("#languages input:checked")].map(
      (i) => i.value
    );
    const languages = [];
    for (const name of selected) {
      languages.push(await fetchText(`data/languages/${name}.yaml`));
    }
    const customLang = $("custom-language").value.trim();
    const isolated = $("isolated-languages").checked;
    if (isolated && $("keep-ligatures").checked) {
      log("Language-isolated features cannot currently be combined with keep-ligatures.");
      return;
    }
    if (customLang) languages.push(customLang);
    if (!languages.length) {
      log("Select at least one language, or paste a custom language.");
      return;
    }

    const customTheme = $("custom-theme").value.trim();
    const useCustomTheme = Boolean(customTheme);
    const selectedThemes = useCustomTheme
      ? []
      : [...document.querySelectorAll("#themes input:checked")].map((i) => i.value);
    if (!useCustomTheme && !selectedThemes.length) {
      log("Select at least one theme, or paste a custom theme.");
      return;
    }

    // first selected theme is baked into CPAL; the rest become CSS palettes
    const themeText = useCustomTheme
      ? customTheme
      : await fetchText(`data/themes/${selectedThemes[0]}.yaml`);
    const extraThemes = [];
    for (const name of selectedThemes.slice(1)) {
      extraThemes.push(await fetchText(`data/themes/${name}.yaml`));
    }

    const payload = {
      font_b64: abToB64(baseFontBytes),
      languages,
      language_ids: selected,
      theme: themeText,
      extra_themes: extraThemes,
      flavor: $("flavor").value,
      family: $("family").value.trim() || "SyntaxFont",
      color_all: $("color-all").checked,
      keep_ligatures: $("keep-ligatures").checked,
      isolated_languages: isolated,
    };
    const family = payload.family;

    log("Building… (this can take a few seconds; the page stays responsive)");
    const msg = await rpc("generate", { payload: JSON.stringify(payload) });
    const result = msg.result;
    result.bytes = b64ToU8(result.font_b64);
    lastResult = result;

    // palettes actually emitted in the CSS (custom themes are baked only)
    const paletteNames = useCustomTheme ? [] : selectedThemes.map(paletteIdent);
    renderResult(result, paletteNames, family);
    lastIsolatedBuild = isolated;
    applySampleFeature($("sample-code").value);
    log(`Done: ${result.filename} (${(result.bytes.length / 1024).toFixed(0)} KB, ${result.flavor})`);
  } catch (err) {
    console.error(err);
    log("Error: " + (err && err.message ? err.message : err));
  } finally {
    updateGenerateState();
  }
}

function renderWarnings(warnings) {
  const el = $("warnings");
  if (!warnings || !warnings.length) {
    el.hidden = true;
    el.replaceChildren();
    return;
  }
  const title = document.createElement("strong");
  title.textContent = "Language conflicts";
  const ul = document.createElement("ul");
  for (const w of warnings) {
    const li = document.createElement("li");
    li.textContent = w;
    ul.append(li);
  }
  el.replaceChildren(title, ul);
  el.hidden = false;
}

// re-check for conflicting rules as soon as the language selection changes,
// without building a font (the worker only parses the YAML and diffs rules)
let warningsTimer = null;

function selectedLanguageYamls() {
  const selected = [...document.querySelectorAll("#languages input:checked")].map(
    (i) => i.value
  );
  return selected;
}

async function refreshWarnings() {
  if (!engineReady) return;
  if ($("isolated-languages")?.checked) {
    // Isolated builds keep one opt-in feature per language, so the combined
    // `calt` conflicts checked here do not apply.
    renderWarnings([]);
    return;
  }
  const languages = [];
  for (const name of selectedLanguageYamls()) {
    languages.push(await fetchText(`data/languages/${name}.yaml`));
  }
  const customLang = $("custom-language").value.trim();
  if (customLang) languages.push(customLang);
  if (!languages.length) {
    renderWarnings([]);
    return;
  }
  try {
    const msg = await rpc("warnings", { languages });
    renderWarnings(msg.warnings);
  } catch (err) {
    renderWarnings([`Could not parse languages: ${err.message || err}`]);
  }
}

function scheduleWarnings() {
  clearTimeout(warningsTimer);
  warningsTimer = setTimeout(refreshWarnings, 250);
}

// rough size impact of each build option, measured with JetBrains Mono and
// JavaScript + CSS + HTML (the default selection); shown as a total percentage
const SIZE_BASE_KB = 97.2;
const SIZE_DELTA_KB = { colorAll: 34.1, keepLigatures: 10.0, isolated: 0.0 };

function updateSizeHint() {
  const kb =
    ($("color-all").checked ? SIZE_DELTA_KB.colorAll : 0) +
    ($("keep-ligatures").checked ? SIZE_DELTA_KB.keepLigatures : 0) +
    ($("isolated-languages").checked ? SIZE_DELTA_KB.isolated : 0);
  const el = $("size-hint");
  if (kb < 0.5) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  el.hidden = false;
  el.textContent = `Estimated ≈ +${Math.round((100 * kb) / SIZE_BASE_KB)}% larger (JetBrains Mono baseline).`;
}

function renderResult(result, paletteNames, family) {
  for (const id of ["download-font", "download-css", "download-fea"]) {
    $(id).disabled = false;
  }
  $("css-out").textContent = result.css;

  const blobUrl = URL.createObjectURL(
    new Blob([result.bytes], { type: "font/" + result.flavor })
  );
  const css = result.css
    .split(result.filename)
    .join(blobUrl)
    .replace(/^code, pre \{/m, "#preview {");
  let style = $("result-style");
  if (!style) {
    style = document.createElement("style");
    style.id = "result-style";
    document.head.append(style);
  }
  style.textContent = css;

  const preview = $("preview");
  preview.style.setProperty("font-family", `'${family}', monospace`, "important");
  // the preview is a <textarea> (plain text), so the palette applies directly
  const applyPalette = (value) => {
    preview.style.fontPalette = value;
  };

  // preview theme selector: normal + one entry per emitted palette
  const sel = $("preview-palette");
  sel.innerHTML = "";
  for (const p of ["normal", ...paletteNames]) {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    sel.append(opt);
  }
  sel.onchange = () => applyPalette(sel.value);
  // default to the system colour scheme unless the user picked a background
  const dark = previewIsDark();
  const night = paletteNames.find((p) => p === "--night");
  const light = paletteNames.find((p) => p === "--default");
  const initial = dark ? night || "normal" : light || "normal";
  applyPalette(initial);
  sel.value = initial;
  setPreviewBackground(dark, { switchPalette: false });
}

// null = follow the system colour scheme; true/false = the user's choice
let previewDark = null;

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function previewIsDark() {
  return previewDark === null ? systemPrefersDark() : previewDark;
}

// set an explicit light/dark preview background (independent of the page
// theme); when `switchPalette` is set, also pick the matching palette so the
// text stays readable
function setPreviewBackground(dark, { switchPalette = true } = {}) {
  const preview = $("preview");
  preview.classList.toggle("dark", dark);
  preview.classList.toggle("light", !dark);
  $("preview-bg").textContent = dark ? "Light background" : "Dark background";
  if (!switchPalette) return;
  const sel = $("preview-palette");
  const want = dark
    ? [...sel.options].find((o) => o.value === "--night")
    : [...sel.options].find((o) => o.value === "--default") ||
      [...sel.options].find((o) => o.value === "normal");
  if (want) {
    sel.value = want.value;
    preview.style.fontPalette = want.value;
  }
}

function togglePreviewBackground() {
  previewDark = !previewIsDark();
  setPreviewBackground(previewDark);
}

function download(kind) {
  if (!lastResult) return;
  let name, data, type;
  if (kind === "font") {
    name = lastResult.filename;
    data = lastResult.bytes;
    type = "font/" + lastResult.flavor;
  } else if (kind === "css") {
    name = "highlight.css";
    data = lastResult.css;
    type = "text/css";
  } else {
    name = "features.fea";
    data = lastResult.fea;
    type = "text/plain";
  }
  const blob = new Blob([data], { type });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function wireDropZone() {
  const drop = $("drop");
  const input = $("font-input");
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (file) setFont(await file.arrayBuffer(), file.name);
  });
  for (const ev of ["dragenter", "dragover"]) {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.add("dragover");
    });
  }
  for (const ev of ["dragleave", "drop"]) {
    drop.addEventListener(ev, (e) => {
      e.preventDefault();
      drop.classList.remove("dragover");
    });
  }
  drop.addEventListener("drop", async (e) => {
    const file = e.dataTransfer.files[0];
    if (file) setFont(await file.arrayBuffer(), file.name);
  });
}

function main() {
  wireDropZone();
  // set the preview background before the first build, and follow the system
  // theme until the user explicitly toggles it
  setPreviewBackground(previewIsDark(), { switchPalette: false });
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (previewDark === null) {
        setPreviewBackground(previewIsDark(), { switchPalette: false });
      }
    });
  $("bundled-font").addEventListener("change", () => loadBundledFont($("bundled-font").value));
  $("sample-code").addEventListener("change", () => loadSampleCode($("sample-code").value));
  $("generate").addEventListener("click", generate);
  $("custom-language").addEventListener("input", scheduleWarnings);
  $("keep-ligatures").addEventListener("change", scheduleWarnings);
  $("isolated-languages").addEventListener("change", scheduleWarnings);
  for (const id of ["color-all", "keep-ligatures", "isolated-languages"]) {
    $(id).addEventListener("change", updateSizeHint);
  }
  $("preview-bg").addEventListener("click", togglePreviewBackground);
  $("download-font").addEventListener("click", () => download("font"));
  $("download-css").addEventListener("click", () => download("css"));
  $("download-fea").addEventListener("click", () => download("fea"));
  updateSizeHint();
  initEngine();
}

main();
