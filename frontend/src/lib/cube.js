// Cube lists: parsing pasted/uploaded lists, resolving them through the API, and custom card images.
import api from "@/lib/api";

/** Card names from a pasted or uploaded list (plain text, "4x Name", CSV first column, or JSON). */
export function parseList(text) {
  const t = (text || "").trim();
  if (t.startsWith("[") || t.startsWith("{")) {
    try {
      const j = JSON.parse(t);
      const arr = Array.isArray(j) ? j : (j.cards || j.mainboard || []);
      return arr.map((x) => (typeof x === "string" ? x : x.name)).filter(Boolean);
    } catch { /* fall through */ }
  }
  return t.split(/\r?\n/).map((ln) => {
    let s = ln.split(",")[0].trim();           // CSV: first column
    s = s.replace(/^\d+\s*[xX]?\s+/, "");       // leading "4 " / "4x "
    s = s.replace(/\s*\([^)]*\)\s*[^\s]*/g, "").trim();
    return s;
  }).filter((s) => s && !/^(name|quantity|count)$/i.test(s));
}

/** The cube id from a CubeCobra link or a bare id. */
export function cubeCobraId(input) {
  let id = (input || "").trim();
  if (id.includes("/cube/")) id = id.split("/").filter(Boolean).pop();
  return id.split("?")[0];
}

/**
 * Resolve a cube from a CubeCobra link/id or a pasted list into card objects.
 * `keep` (optional) is a list of cards already in the cube: cards whose names are still in the
 * list are reused as they are (same printing), so only new names are looked up.
 */
export async function resolveCube({ cubeCobra = "", text = "", keep = [] }) {
  let names;
  if (cubeCobra.trim()) {
    const { data } = await api.get("/cube/cubecobra", { params: { id: cubeCobra.trim() } });
    names = data.names || [];
  } else {
    names = parseList(text);
  }
  const uniq = Array.from(new Set(names));
  const kept = new Map(keep.filter((c) => !c.is_custom).map((c) => [c.name.toLowerCase(), c]));
  const reuse = [];
  const lookup = [];
  uniq.forEach((n) => { const k = kept.get(n.toLowerCase()); if (k) reuse.push(k); else lookup.push(n); });
  let found = [];
  let notFound = [];
  if (lookup.length) {
    const { data } = await api.post("/cards/collection", { names: lookup });
    found = data.cards || [];
    notFound = data.not_found || [];
  }
  return { cards: [...reuse, ...found], notFound, total: uniq.length, cubecobraId: cubeCobra.trim() ? cubeCobraId(cubeCobra) : null };
}

/**
 * Shrink an uploaded image to card size (488 px wide, like Scryfall's "normal" image) as a JPEG
 * data URL, so a custom card adds roughly 50 KB instead of a multi-MB photo.
 */
export function resizeImage(file, width = 488) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, width / img.width);
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Not an image")); };
    img.src = url;
  });
}

export const fileBaseName = (f) => f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();

/** Read a text file the user picked. */
export const readTextFile = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result || ""));
  r.onerror = reject;
  r.readAsText(file);
});
