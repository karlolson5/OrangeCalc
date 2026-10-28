// Add/rename tools here. `file` is relative to the site root (the workflow copies scripts/ there).
// `hide` lists constants that should not get an input.
const TOOLS = [
  { id: "belt",  title: "Belt",  file: "scripts/belt_combos.py",  hide: ["MM_PER_IN"] },
  { id: "chain", title: "Chain", file: "scripts/chain_combos.py", hide: [] },
  { id: "gear",  title: "Gear",  file: "scripts/gear_combos.py",  hide: [] },
];

// Python helper: loads a script as a module, discovers its config constants
// (every public top-level variable that is a number, bool, string, list of numbers,
// or list of dataclass instances), and runs main() with overrides.
const HELPER = `
import json, io, sys, types, contextlib, traceback, dataclasses, re

_mods, _kinds, _dc = {}, {}, {}

def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def _norm(v):
    return list(v) if isinstance(v, range) else v

def _kind(v):
    if isinstance(v, bool): return "bool"
    if isinstance(v, int): return "int"
    if isinstance(v, float): return "float"
    if isinstance(v, str): return "str"
    if isinstance(v, (list, tuple)) and all(_is_num(x) for x in v):
        return "list_int" if all(isinstance(x, int) for x in v) else "list_float"
    return None

def _field(name, kind, v):
    return {"name": name, "kind": kind, "value": list(v) if kind.startswith("list_") else v}

def load(source, key):
    modname = "user_script_" + re.sub(r"\\W", "_", key)
    mod = types.ModuleType(modname)
    sys.modules[modname] = mod
    exec(compile(source, key, "exec"), mod.__dict__)

    fields = []
    _dc[key] = {}
    for name, v in list(vars(mod).items()):
        if name.startswith("_"):
            continue
        v = _norm(v)
        k = _kind(v)
        if k:
            fields.append(_field(name, k, v))
        elif (isinstance(v, list) and v
              and all(dataclasses.is_dataclass(x) and not isinstance(x, type) for x in v)):
            _dc[key][name] = list(v)
            for i, item in enumerate(v):
                for f in dataclasses.fields(item):
                    fv = _norm(getattr(item, f.name))
                    fk = _kind(fv)
                    if fk:
                        fields.append(_field(f"{name}[{i}].{f.name}", fk, fv))
    _mods[key] = mod
    _kinds[key] = {f["name"]: f["kind"] for f in fields}
    return json.dumps(fields)

_cast = {
    "int": int, "float": float, "bool": bool, "str": str,
    "list_int": lambda l: [int(x) for x in l],
    "list_float": lambda l: [float(x) for x in l],
}

def run(key, overrides_json):
    mod = _mods[key]
    nested = {}
    for n, v in json.loads(overrides_json).items():
        v = _cast[_kinds[key][n]](v)
        m = re.fullmatch(r"(\\w+)\\[(\\d+)\\]\\.(\\w+)", n)
        if m:
            nested.setdefault((m[1], int(m[2])), {})[m[3]] = v
        else:
            setattr(mod, n, v)
    for name, items in _dc[key].items():
        setattr(mod, name, [dataclasses.replace(it, **nested.get((name, i), {}))
                            for i, it in enumerate(items)])
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

const isList = f => f.kind.startsWith("list_");

function parseField(f, input) {
  if (f.kind === "bool") return input.checked;
  const raw = input.value;
  if (f.kind === "str") return raw;
  const isInt = f.kind.endsWith("int");
  const parseOne = s => {
    const n = Number(s);
    if (s === "" || !Number.isFinite(n)) throw new Error(`${f.name}: "${s}" is not a number`);
    if (isInt && !Number.isInteger(n)) throw new Error(`${f.name}: "${s}" must be an integer`);
    return n;
  };
  if (isList(f)) {
    const parts = raw.split(",").map(s => s.trim()).filter(s => s !== "");
    return parts.map(parseOne);
  }
  return parseOne(raw.trim());
}

function setInput(f, input) {
  if (f.kind === "bool") input.checked = f.value;
  else input.value = isList(f) ? f.value.join(", ") : String(f.value);
}

function makeInput(f) {
  let input;
  if (f.kind === "bool") input = el("input", { type: "checkbox" });
  else if (f.kind === "str" || isList(f)) input = el("input", { type: "text" });
  else input = el("input", { type: "number", step: f.kind === "int" ? "1" : "any" });
  setInput(f, input);
  return input;
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

  // Hidden constants are not shown or sent, so the script's own value is used.
  fields = fields.filter(f => !(tool.hide || []).includes(f.name));

  const inputs = {};
  const form = el("div");
  for (const f of fields) {
    const input = makeInput(f);
    if (f.kind !== "bool") {
      input.addEventListener("keydown", e => { if (e.key === "Enter") run(); });
    }
    inputs[f.name] = input;
    form.append(el("label", { className: "field" },
      el("span", {}, f.name, isList(f) ? el("small", { textContent: "  (comma-separated)" }) : ""),
      input));
  }

  const output = el("pre", { className: "output" });
  const error = el("div", { className: "error" });

  async function run() {
    error.textContent = "";
    try {
      const vals = {};
      for (const f of fields) vals[f.name] = parseField(f, inputs[f.name]);
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
    for (const f of fields) setInput(f, inputs[f.name]);
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