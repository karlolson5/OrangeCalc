// Add/rename tools here. `file` is relative to the site root (the workflow copies scripts/ there).
const TOOLS = [
  { id: "tool1", title: "Tool 1", file: "scripts/tool1.py" },
  { id: "tool2", title: "Tool 2", file: "scripts/tool2.py" },
  { id: "tool3", title: "Tool 3", file: "scripts/tool3.py" },
];

// Python helper: loads a script as a module, discovers its config constants
// (top-level assignments before the first def/class), and runs main() with overrides.
const HELPER = `
import ast, io, json, sys, types, contextlib, traceback

_mods, _kinds = {}, {}

def load(source, key):
    tree = ast.parse(source)
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            break
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_") and t.id not in names:
                    names.append(t.id)

    mod = types.ModuleType("user_script_" + key.replace("/", "_").replace(".", "_"))
    sys.modules[mod.__name__] = mod
    exec(compile(source, key, "exec"), mod.__dict__)

    def is_num(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    fields = []
    for n in names:
        v = getattr(mod, n, None)
        if isinstance(v, range):
            v = list(v)
        if is_num(v):
            fields.append({"name": n, "kind": "float" if isinstance(v, float) else "int", "value": v})
        elif isinstance(v, (list, tuple)) and v and all(is_num(x) for x in v):
            kind = "int" if all(isinstance(x, int) for x in v) else "float"
            fields.append({"name": n, "kind": "list_" + kind, "value": list(v)})
    _mods[key] = mod
    _kinds[key] = {f["name"]: f["kind"] for f in fields}
    return json.dumps(fields)

def run(key, overrides_json):
    mod = _mods[key]
    for name, v in json.loads(overrides_json).items():
        kind = _kinds[key][name]
        if kind == "int": v = int(v)
        elif kind == "float": v = float(v)
        elif kind == "list_int": v = [int(x) for x in v]
        elif kind == "list_float": v = [float(x) for x in v]
        setattr(mod, name, v)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.main()
    except Exception:
        buf.write("\\nERROR:\\n" + traceback.format_exc())
    return buf.getvalue()
`;

let pyPromise = null;
function getPyodide() {
  if (!pyPromise) {
    pyPromise = loadPyodide().then(py => { py.runPython(HELPER); return py; });
  }
  return pyPromise;
}

const tabsEl = document.getElementById("tabs");
const panelsEl = document.getElementById("panels");
const panels = {};

function el(tag, props = {}, ...children) {
  const e = Object.assign(document.createElement(tag), props);
  children.forEach(c => e.append(c));
  return e;
}

function parseField(f, raw) {
  const isInt = f.kind.endsWith("int");
  const parseOne = s => {
    const n = Number(s);
    if (s === "" || !Number.isFinite(n)) throw new Error(`${f.name}: "${s}" is not a number`);
    if (isInt && !Number.isInteger(n)) throw new Error(`${f.name}: "${s}" must be an integer`);
    return n;
  };
  if (f.kind.startsWith("list_")) {
    const parts = raw.split(",").map(s => s.trim()).filter(s => s !== "");
    if (!parts.length) throw new Error(`${f.name}: list is empty`);
    return parts.map(parseOne);
  }
  return parseOne(raw.trim());
}

async function buildPanel(tool) {
  const panel = el("div", { className: "panel" }, el("p", { textContent: "Loading Python (first load takes a few seconds)..." }));
  panels[tool.id] = panel;
  panelsEl.append(panel);

  let fields;
  try {
    const py = await getPyodide();
    const src = await (await fetch(tool.file)).text();
    py.globals.set("_src", src);
    py.globals.set("_key", tool.file);
    fields = JSON.parse(py.runPython("load(_src, _key)"));
  } catch (err) {
    panel.replaceChildren(el("pre", { className: "error", textContent: String(err) }));
    return;
  }

  const inputs = {};
  const form = el("div");
  for (const f of fields) {
    const isList = f.kind.startsWith("list_");
    const input = el("input", {
      type: isList ? "text" : "number",
      value: isList ? f.value.join(", ") : String(f.value),
    });
    if (!isList) input.step = "any";
    input.addEventListener("keydown", e => { if (e.key === "Enter") run(); });
    inputs[f.name] = input;
    form.append(el("label", { className: "field" },
      el("span", {}, f.name, isList ? el("small", { textContent: "  (comma-separated)" }) : ""),
      input));
  }

  const output = el("pre", { className: "output" });
  const error = el("div", { className: "error" });

  async function run() {
    error.textContent = "";
    try {
      const vals = {};
      for (const f of fields) vals[f.name] = parseField(f, inputs[f.name].value);
      output.textContent = "Running...";
      await new Promise(r => setTimeout(r, 20)); // let the browser paint first
      const py = await getPyodide();
      py.globals.set("_key", tool.file);
      py.globals.set("_ov", JSON.stringify(vals));
      output.textContent = py.runPython("run(_key, _ov)");
    } catch (err) {
      output.textContent = "";
      error.textContent = err.message;
    }
  }

  function reset() {
    for (const f of fields) {
      inputs[f.name].value = f.kind.startsWith("list_") ? f.value.join(", ") : String(f.value);
    }
    run();
  }

  panel.replaceChildren(
    form,
    el("div", { className: "buttons" },
      el("button", { textContent: "Run", onclick: run }),
      el("button", { textContent: "Reset to defaults", onclick: reset })),
    error,
    output,
  );
  run();
}

function show(id) {
  for (const t of TOOLS) {
    document.getElementById("tab-" + t.id).classList.toggle("active", t.id === id);
    if (panels[t.id]) panels[t.id].hidden = t.id !== id;
  }
  if (!panels[id]) buildPanel(TOOLS.find(t => t.id === id));
  history.replaceState(null, "", "#" + id);
}

for (const t of TOOLS) {
  tabsEl.append(el("button", { id: "tab-" + t.id, textContent: t.title, onclick: () => show(t.id) }));
}
show(TOOLS.some(t => "#" + t.id === location.hash) ? location.hash.slice(1) : TOOLS[0].id);