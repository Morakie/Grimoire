// The bot engine in the browser, for Bot Brain. The server's own Python bot files (GET /api/lab/engine) run in
// a Web Worker through Pyodide (Python compiled to WebAssembly), so turning knobs, re-drafting and looking up
// cards never call the server. A saved pool is downloaded once (GET /api/lab/pool-export) and kept in this
// browser (IndexedDB) until it is rebuilt.
import api from "@/lib/api";

const PYODIDE = "https://cdn.jsdelivr.net/npm/pyodide@0.27.8/";
const DB = "grimoire-bot-brain";

// ---------------------------------------------------------------- a tiny IndexedDB key/value store
function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore("kv");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idb(mode, fn) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("kv", mode);
    const req = fn(tx.objectStore("kv"));
    tx.oncomplete = () => { resolve(req?.result); db.close(); };
    tx.onerror = () => { reject(tx.error); db.close(); };
  });
}
const idbGet = (k) => idb("readonly", (s) => s.get(k)).catch(() => undefined);
const idbPut = (k, v) => idb("readwrite", (s) => s.put(v, k)).catch(() => undefined);
const idbKeys = () => idb("readonly", (s) => s.getAllKeys()).catch(() => []);
const idbDel = (k) => idb("readwrite", (s) => s.delete(k)).catch(() => undefined);

// ---------------------------------------------------------------- the worker
const WORKER = `
importScripts(${JSON.stringify(PYODIDE + "pyodide.js")});
let S = null, current = 0;
const ok = (id, data) => postMessage({ id, ok: true, data });
async function gunzip(buf) {
  const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
  return await new Response(stream).text();
}
async function run(id, cfg, chunk) {
  current = id;
  ok(id, { type: "start", ...JSON.parse(S.run_start(JSON.stringify(cfg))) });
  for (;;) {
    if (current !== id) return;                // a newer run replaced this one
    const r = JSON.parse(S.run_step(chunk));
    ok(id, { type: "picks", ...r });
    if (r.done) return;
    await new Promise((res) => setTimeout(res, 0));   // let views and new runs in between picks
  }
}
onmessage = async ({ data: { id, op, arg, chunk } }) => {
  try {
    if (op === "init") {
      const py = await loadPyodide({ indexURL: ${JSON.stringify(PYODIDE)} });
      py.FS.mkdirTree("/lab/draftbot");
      for (const [name, text] of Object.entries(arg)) py.FS.writeFile("/lab/draftbot/" + name, text);
      py.runPython("import sys; sys.path.insert(0, '/lab')");
      S = py.pyimport("draftbot.browser").SESSION;
      return ok(id, true);
    }
    if (op === "load") return ok(id, JSON.parse(S.load(await gunzip(arg))));
    if (op === "run") return run(id, arg, chunk || 4);
    if (op === "stop") { current = 0; return ok(id, true); }
    if (op === "card") return ok(id, JSON.parse(S.card(arg)));
    return ok(id, JSON.parse(S[op](JSON.stringify(arg))));     // view, lanes, web
  } catch (e) {
    postMessage({ id, ok: false, error: String(e && e.message || e).split("\\n").slice(-3).join(" ") });
  }
};
`;

let engine = null;   // one per page load: {call, run, stop, version}

// Start the engine (once): Pyodide (~10 MB, cached by the browser after the first visit) and the bot files.
export function startEngine() {
  if (engine) return engine;
  const worker = new Worker(URL.createObjectURL(new Blob([WORKER], { type: "text/javascript" })));
  let next = 0;
  const waiting = new Map();
  worker.onmessage = ({ data }) => {
    const w = waiting.get(data.id);
    if (!w) return;
    if (!data.ok) { waiting.delete(data.id); w.reject(new Error(data.error)); return; }
    if (w.stream) {
      w.stream(data.data);
      if (data.data.type === "picks" && data.data.done) { waiting.delete(data.id); w.resolve(); }
    } else { waiting.delete(data.id); w.resolve(data.data); }
  };
  worker.onerror = (e) => waiting.forEach((w) => w.reject(new Error(e.message || "The bot engine stopped")));
  const call = (op, arg) => new Promise((resolve, reject) => {
    const id = ++next;
    waiting.set(id, { resolve, reject });
    worker.postMessage({ id, op, arg });
  });
  const ready = (async () => {
    const { data } = await api.get("/lab/engine", { timeout: 30000 });
    await call("init", data.files);
    return data.version;
  })();
  engine = {
    ready,
    call: async (op, arg) => { await ready; return call(op, arg); },
    // Run a draft a few picks at a time: onChunk({type: "start" | "picks", ...}) for each step. A newer run
    // (or stop) ends this one: its promise then never resolves, so callers check their own run id.
    run: async (cfg, onChunk, chunk = 4) => {
      await ready;
      return new Promise((resolve, reject) => {
        const id = ++next;
        waiting.forEach((w, k) => { if (w.stream) waiting.delete(k); });
        waiting.set(id, { resolve, reject, stream: onChunk });
        worker.postMessage({ id, op: "run", arg: cfg, chunk });
      });
    },
    stop: () => call("stop"),
  };
  return engine;
}

// A saved pool's data, from this browser's copy if it has the latest one, else downloaded once.
// `meta` is a row from GET /api/lab/pools ({key, built_at, ...}). Returns {bytes, cached}.
export async function poolBytes(meta, onStep) {
  const cacheKey = `pool|${meta.key}|${meta.built_at || ""}`;
  const have = await idbGet(cacheKey);
  if (have) return { bytes: have, cached: true };
  onStep?.("Downloading the pool once (it's kept in this browser after that)…");
  const { data } = await api.get("/lab/pool-export", { params: { key: meta.key }, responseType: "arraybuffer", timeout: 120000 });
  // Keep one copy per pool: drop older builds of the same pool.
  for (const k of await idbKeys()) if (String(k).startsWith(`pool|${meta.key}|`)) await idbDel(k);
  await idbPut(cacheKey, data);
  return { bytes: data, cached: false };
}
