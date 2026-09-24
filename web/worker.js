"use strict";
/* SyntaxFont build engine: runs Pyodide off the main thread so the page stays
 * responsive while fonts generate. Protocol (postMessage, both directions
 * carry `id` for request routing):
 *   main -> worker : {id, cmd:"init"}
 *   worker -> main : {id, type:"log", line} | {id, type:"ready", manifest}
 *   main -> worker : {id, cmd:"generate", payload}   (payload is a JSON string)
 *   worker -> main : {id, type:"done", result} | {id, type:"error", message}
 *   main -> worker : {id, cmd:"family", font_b64}
 *   worker -> main : {id, type:"family", name}
 *   main -> worker : {id, cmd:"warnings", languages:[yaml,...]}
 *   worker -> main : {id, type:"warnings", warnings:[...]}
 */

importScripts("https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.js");

const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";

const RUNNER = `
import base64, json
import syntaxfont.webapp as _w

def _family_name(b64):
    return _w.family_name(base64.b64decode(b64))

def _warnings(texts_json):
    from syntaxfont.conflicts import detect_conflicts
    texts = json.loads(texts_json)
    return json.dumps(detect_conflicts([_w.language_from_yaml(t) for t in texts]))

def _run(payload):
    data = json.loads(payload)
    langs = [_w.language_from_yaml(t) for t in data["languages"]]
    theme = _w.theme_from_yaml(data["theme"])
    extras = [_w.theme_from_yaml(t) for t in data.get("extra_themes", [])]
    res = _w.build_from_bytes(
        base64.b64decode(data["font_b64"]),
        langs, theme, extra_themes=extras,
        flavor=(data.get("flavor") or None),
        family=data.get("family") or "SyntaxFont",
        color_all=bool(data.get("color_all")),
    )
    return json.dumps({
        "filename": res["filename"],
        "css": res["css"],
        "fea": res["fea"],
        "flavor": res["flavor"],
        "warnings": res.get("warnings", []),
        "font_b64": base64.b64encode(res["font"]).decode("ascii"),
    })
`;

let pyodide = null;
let manifest = null;
let currentId = null;

function send(msg) {
  self.postMessage(msg);
}

function log(line) {
  send({ id: currentId, type: "log", line: String(line) });
}

async function cmdInit(id) {
  currentId = id;
  log("Loading Pyodide…");
  pyodide = await loadPyodide({
    indexURL: PYODIDE_URL,
    stdout: log,
    stderr: log,
  });
  log("Installing fonttools, pyyaml, brotli…");
  await pyodide.loadPackage(["fonttools", "pyyaml", "brotli"], {
    messageCallback: log,
  });

  manifest = await (await fetch("data/manifest.json")).json();
  pyodide.FS.mkdirTree("/lib/syntaxfont");
  for (const f of manifest.python) {
    const text = await (await fetch(`data/syntaxfont/${f}`)).text();
    pyodide.FS.writeFile(`/lib/syntaxfont/${f}`, text);
  }
  pyodide.runPython("import sys; sys.path.insert(0, '/lib')");
  pyodide.runPython(RUNNER);
  send({ id, type: "ready", manifest });
}

async function cmdGenerate(id, payload) {
  currentId = id;
  pyodide.globals.set("_payload", payload);
  const out = await pyodide.runPythonAsync("_run(_payload)");
  send({ id, type: "done", result: JSON.parse(out) });
}

async function cmdFamily(id, font_b64) {
  currentId = id;
  pyodide.globals.set("_font_b64", font_b64);
  const name = pyodide.runPython("_family_name(_font_b64)");
  send({ id, type: "family", name: name || "" });
}

async function cmdWarnings(id, languages) {
  currentId = id;
  pyodide.globals.set("_warn_langs", JSON.stringify(languages));
  const out = pyodide.runPython("_warnings(_warn_langs)");
  send({ id, type: "warnings", warnings: JSON.parse(out) });
}

self.onmessage = async (e) => {
  const { id, cmd } = e.data || {};
  try {
    if (cmd === "init") await cmdInit(id);
    else if (cmd === "generate") await cmdGenerate(id, e.data.payload);
    else if (cmd === "family") await cmdFamily(id, e.data.font_b64);
    else if (cmd === "warnings") await cmdWarnings(id, e.data.languages);
    else send({ id, type: "error", message: `unknown cmd: ${cmd}` });
  } catch (err) {
    console.error(err);
    send({ id, type: "error", message: String((err && err.message) || err) });
  }
};
