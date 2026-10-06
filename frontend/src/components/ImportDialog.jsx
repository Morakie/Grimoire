import React, { useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Upload, Loader2, FileUp } from "lucide-react";
import { toast } from "sonner";

const SECTION_RE = {
  sideboard: /^(side ?board|sb)\b/i,
  commander: /^(commander|command zone|commanders)\b/i,
  mainboard: /^(deck|main ?deck|main ?board)\b/i,
};
const SKIP_RE = /^(maybe ?board|tokens?|about|name|layout|\/\/)/i;
const TYPE_LABEL_RE = /^(creatures?|lands?|spells?|instants?|sorcer(y|ies)|artifacts?|enchantments?|planeswalkers?|battles?|other)\b.*$/i;

function cleanName(name) {
  let n = name
    .replace(/\s*\([^)]*\)\s*[^\s]*/g, "") // (SET) 123
    .replace(/\s*\*[^*]*\*/g, "")          // *F*
    .replace(/\s*\[[^\]]*\]/g, "")         // [tags]
    .replace(/\s+#.*$/, "")                // trailing #comment
    .trim();
  if (n.includes("//")) n = n.split("//")[0].trim();
  return n;
}

function parseText(text) {
  const out = { mainboard: [], sideboard: [], commander: [] };
  let section = "mainboard";
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (SKIP_RE.test(line)) continue;
    let matchedSection = null;
    for (const [sec, re] of Object.entries(SECTION_RE)) {
      if (re.test(line) && !/\d/.test(line.replace(/^(deck|sideboard|commander)\b/i, ""))) { matchedSection = sec; break; }
    }
    if (matchedSection) { section = matchedSection; continue; }
    if (TYPE_LABEL_RE.test(line) && !/^\d/.test(line)) continue;

    let qty = 1, name = line;
    let m = line.match(/^(\d+)\s*[xX]?\s+(.+)$/);
    if (m) { qty = parseInt(m[1], 10); name = m[2]; }
    else {
      m = line.match(/^(.+?)\s+[xX](\d+)$/);
      if (m) { name = m[1]; qty = parseInt(m[2], 10); }
    }
    name = cleanName(name);
    if (!name) continue;
    out[section].push({ name, quantity: Math.max(1, qty) });
  }
  return out;
}

function parseJson(obj) {
  const out = { mainboard: [], sideboard: [], commander: [] };
  const pushList = (arr, section) => arr.forEach((it) => {
    if (typeof it === "string") out[section].push({ name: cleanName(it), quantity: 1 });
    else if (it && it.name) out[section].push({ name: cleanName(it.name), quantity: it.quantity || it.count || it.qty || 1 });
  });
  const pushMap = (mapObj, section) => Object.entries(mapObj).forEach(([k, v]) => {
    if (v && typeof v === "object") out[section].push({ name: cleanName(v.name || k), quantity: v.quantity || v.count || v.qty || 1 });
    else out[section].push({ name: cleanName(k), quantity: v || 1 });
  });
  const handle = (val, section) => { if (!val) return; Array.isArray(val) ? pushList(val, section) : (typeof val === "object" ? pushMap(val, section) : null); };
  if (Array.isArray(obj)) pushList(obj, "mainboard");
  else {
    ["mainboard", "main", "maindeck", "deck", "cards"].forEach((k) => handle(obj[k], "mainboard"));
    ["sideboard", "side"].forEach((k) => handle(obj[k], "sideboard"));
    ["commander", "commanders"].forEach((k) => handle(obj[k], "commander"));
  }
  return out;
}

export default function ImportDialog({ open, onOpenChange, onImport }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(file);
  };

  const doImport = async () => {
    const trimmed = text.trim();
    if (!trimmed) { toast.error("Paste a decklist or upload a file"); return; }
    let parsed;
    try {
      parsed = (trimmed.startsWith("{") || trimmed.startsWith("[")) ? parseJson(JSON.parse(trimmed)) : parseText(trimmed);
    } catch {
      parsed = parseText(trimmed);
    }
    const all = [...parsed.mainboard, ...parsed.sideboard, ...parsed.commander];
    if (!all.length) { toast.error("Could not find any cards in that list"); return; }
    const uniqueNames = Array.from(new Set(all.map((c) => c.name)));

    setLoading(true);
    try {
      const { data } = await api.post("/cards/collection", { names: uniqueNames });
      const lookup = {};
      (data.cards || []).forEach((c) => {
        lookup[c.name.toLowerCase()] = c;
        if (c.name.includes("//")) lookup[c.name.split("//")[0].trim().toLowerCase()] = c;
      });
      const resolve = (list) => {
        const resolved = [];
        const missing = [];
        list.forEach((item) => {
          const card = lookup[item.name.toLowerCase()];
          if (card) resolved.push({ ...card, quantity: item.quantity });
          else missing.push(item.name);
        });
        return { resolved, missing };
      };
      const mb = resolve(parsed.mainboard);
      const sb = resolve(parsed.sideboard);
      const cmd = resolve(parsed.commander);
      const missing = [...mb.missing, ...sb.missing, ...cmd.missing];
      onImport({ mainboard: mb.resolved, sideboard: sb.resolved, commander: cmd.resolved });
      const total = mb.resolved.length + sb.resolved.length + cmd.resolved.length;
      toast.success(`Imported ${total} card${total === 1 ? "" : "s"}`);
      if (missing.length) toast.error(`${missing.length} not found: ${missing.slice(0, 4).join(", ")}${missing.length > 4 ? "…" : ""}`, { duration: 5000 });
      setText("");
      onOpenChange(false);
    } catch {
      toast.error("Import failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-lg" data-testid="import-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Upload className="w-5 h-5 text-amber-400" /> Import decklist</DialogTitle>
          <DialogDescription className="text-slate-400">
            Paste a decklist or upload a .txt / .json file. Use lines like <span className="text-slate-300">4 Lightning Bolt</span>. Add a <span className="text-slate-300">Sideboard</span> or <span className="text-slate-300">Commander</span> heading to split sections.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          data-testid="import-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"4 Lightning Bolt\n2 Counterspell\n20 Mountain\n\nSideboard\n2 Pyroblast"}
          className="min-h-[220px] bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400"
        />
        <DialogFooter className="flex sm:justify-between items-center gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-300 cursor-pointer hover:text-white" data-testid="import-file-label">
            <FileUp className="w-4 h-4" /> Upload file
            <input type="file" accept=".txt,.json,.dec" onChange={onFile} className="hidden" data-testid="import-file-input" />
          </label>
          <Button data-testid="import-submit" onClick={doImport} disabled={loading} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Import deck"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
