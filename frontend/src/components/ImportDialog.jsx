import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Upload, Loader2, FileUp, ListChecks } from "lucide-react";
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
  // Split / double-faced cards: "Front // Back" (Scryfall), "Front / Back" (Moxfield), "Wear/Tear" (MTGO).
  n = n.split(/\s*\/\/?\s*/)[0].trim();
  return n;
}

// "(SLD) 2199" or "(PLST) EMA-78" → pin the exact printing.
const PRINTING_RE = /\(([A-Za-z0-9]{2,6})\)\s+([^\s*]+)/;
function parsePrinting(name) {
  const m = name.match(PRINTING_RE);
  return m ? { set: m[1].toLowerCase(), collector_number: m[2] } : {};
}

function parseText(text) {
  const out = { mainboard: [], sideboard: [], commander: [], explicitCommander: false };
  let section = "mainboard";
  let block = 0; // blank-line separated chunks; MTGO puts commanders in a final chunk
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) { if (out[section].length && out[section][out[section].length - 1].block === block) block += 1; continue; }
    if (SKIP_RE.test(line)) continue;
    let matchedSection = null;
    for (const [sec, re] of Object.entries(SECTION_RE)) {
      if (re.test(line) && !/\d/.test(line.replace(/^(deck|sideboard|commander)\b/i, ""))) { matchedSection = sec; break; }
    }
    if (matchedSection) {
      section = matchedSection;
      if (section === "commander") out.explicitCommander = true;
      continue;
    }
    if (TYPE_LABEL_RE.test(line) && !/^\d/.test(line)) continue;

    let qty = 1, name = line;
    let m = line.match(/^(\d+)\s*[xX]?\s+(.+)$/);
    if (m) { qty = parseInt(m[1], 10); name = m[2]; }
    else {
      m = line.match(/^(.+?)\s+[xX](\d+)$/);
      if (m) { name = m[1]; qty = parseInt(m[2], 10); }
    }
    const printing = parsePrinting(name);
    name = cleanName(name);
    if (!name) continue;
    out[section].push({ name, quantity: Math.max(1, qty), block, ...printing });
  }
  return out;
}

// ---------- Commander detection for lists without a "Commander" heading ----------

function canCommand(card) {
  const t = card.type_line || "";
  return (t.includes("Legendary") && t.includes("Creature")) || t.includes("Background")
    || /can be your commander/i.test(card.oracle_text || "");
}

// Given the resolved mainboard (in list order, each with its parsed `block`), return how many
// cards to treat as commanders and where they are:
//  - MTGO / plain text: 1–2 commanders in a final chunk after a blank line.
//  - Moxfield: 1–2 commanders listed first, ahead of an otherwise alphabetical list.
function detectCommanders(main) {
  if (main.length < 3) return null;
  const lastBlock = main[main.length - 1].block;
  if (lastBlock > main[0].block) {
    const tail = main.filter((c) => c.block === lastBlock);
    if (tail.length <= 2 && tail.every(canCommand)) return { from: "end", count: tail.length };
  }
  const names = main.map((c) => c.importName.toLowerCase());
  // Sites sort punctuation slightly differently, so allow one out-of-order pair in the rest of the list.
  const descents = (list) => list.slice(1).filter((n, i) => n.localeCompare(list[i]) < 0).length;
  for (const k of [2, 1]) {
    const head = main.slice(0, k);
    if (!head.every(canCommand)) continue;
    if (names[k - 1].localeCompare(names[k]) > 0 && descents(names.slice(k)) <= 1) return { from: "start", count: k };
  }
  return null;
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

// mode="merge": add the pasted cards to the deck (Import).
// mode="replace": the textarea starts as the current decklist and saving replaces the deck (Bulk edit).
export default function ImportDialog({ open, onOpenChange, onImport, mode = "merge", initialText = "", format }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const replace = mode === "replace";

  useEffect(() => {
    if (open) setText(replace ? initialText : "");
  }, [open, replace, initialText]);

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setText(String(reader.result || ""));
    reader.readAsText(file);
  };

  const doImport = async () => {
    const trimmed = text.trim();
    if (!trimmed) {
      if (replace) { onImport({ mainboard: [], sideboard: [], commander: [] }, { replace: true }); toast.success("Deck cleared"); onOpenChange(false); }
      else toast.error("Paste a decklist or upload a file");
      return;
    }
    let parsed;
    try {
      parsed = (trimmed.startsWith("{") || trimmed.startsWith("[")) ? parseJson(JSON.parse(trimmed)) : parseText(trimmed);
    } catch {
      parsed = parseText(trimmed);
    }
    const all = [...parsed.mainboard, ...parsed.sideboard, ...parsed.commander];
    if (!all.length) { toast.error("Could not find any cards in that list"); return; }
    // One lookup per distinct name+printing; each line keeps a key back to its result.
    const keyOf = (c) => [c.name.toLowerCase(), c.set || "", c.collector_number || ""].join("|");
    const entries = Array.from(new Map(all.map((c) => [keyOf(c), {
      key: keyOf(c), name: c.name, set: c.set || null, collector_number: c.collector_number || null,
    }])).values());

    setLoading(true);
    try {
      const { data } = await api.post("/cards/collection", { entries });
      const found = data.resolved || {};
      const resolve = (list) => {
        const resolved = [];
        const missing = [];
        list.forEach((item) => {
          const card = found[keyOf(item)];
          if (card) resolved.push({ ...card, quantity: item.quantity, block: item.block || 0, importName: item.name });
          else missing.push(item.name);
        });
        return { resolved, missing };
      };
      const mb = resolve(parsed.mainboard);
      const sb = resolve(parsed.sideboard);
      const cmd = resolve(parsed.commander);

      // No "Commander" heading? Look for the commander where Moxfield / MTGO put it.
      let detected = [];
      const mainCount = mb.resolved.reduce((n, c) => n + c.quantity, 0);
      if (!parsed.explicitCommander && !cmd.resolved.length && (format === "commander" || (mainCount >= 98 && mainCount <= 101))) {
        const hit = detectCommanders(mb.resolved);
        if (hit) {
          detected = hit.from === "end" ? mb.resolved.slice(-hit.count) : mb.resolved.slice(0, hit.count);
          mb.resolved = hit.from === "end" ? mb.resolved.slice(0, -hit.count) : mb.resolved.slice(hit.count);
          cmd.resolved = detected;
        }
      }
      const strip = (list) => list.map(({ block, importName, ...c }) => c);
      [mb, sb, cmd].forEach((g) => { g.resolved = strip(g.resolved); });
      const missing = [...mb.missing, ...sb.missing, ...cmd.missing];
      // Never silently drop cards when replacing the whole deck: fix the list first.
      if (replace && missing.length) {
        toast.error(`Couldn't find ${missing.length} card${missing.length === 1 ? "" : "s"}: ${missing.slice(0, 4).join(", ")}${missing.length > 4 ? "…" : ""}. Fix ${missing.length === 1 ? "it" : "them"} and save again.`, { duration: 7000 });
        return;
      }
      onImport({ mainboard: mb.resolved, sideboard: sb.resolved, commander: cmd.resolved },
        { replace, format: detected.length && format !== "commander" ? "commander" : undefined });
      if (detected.length) toast.success(`Commander: ${detected.map((c) => c.name).join(" & ")}`, { duration: 4000 });
      const total = mb.resolved.length + sb.resolved.length + cmd.resolved.length;
      toast.success(replace ? "Decklist updated" : `Imported ${total} card${total === 1 ? "" : "s"}`);
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
      <DialogContent className={`bg-slate-900 border-slate-700 text-slate-100 ${replace ? "max-w-2xl" : "max-w-lg"}`} data-testid={replace ? "bulk-edit-dialog" : "import-dialog"}>
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            {replace ? <><ListChecks className="w-5 h-5 text-amber-400" /> Bulk edit decklist</> : <><Upload className="w-5 h-5 text-amber-400" /> Import decklist</>}
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {replace ? (
              <>Edit the whole list at once: change quantities, delete lines, or paste a new list over it. Saving replaces the deck. Clear the box to empty the deck.</>
            ) : (<>
            Paste a decklist or upload a .txt / .json file. Use lines like <span className="text-slate-300">4 Lightning Bolt</span>. Add a <span className="text-slate-300">Sideboard</span> or <span className="text-slate-300">Commander</span> heading to split sections.
            </>)}
          </DialogDescription>
        </DialogHeader>
        <Textarea
          data-testid="import-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"4 Lightning Bolt\n2 Counterspell\n20 Mountain\n\nSideboard\n2 Pyroblast"}
          className={`${replace ? "min-h-[360px]" : "min-h-[220px]"} bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400`}
        />
        <DialogFooter className="flex sm:justify-between items-center gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-300 cursor-pointer hover:text-white" data-testid="import-file-label">
            <FileUp className="w-4 h-4" /> Upload file
            <input type="file" accept=".txt,.json,.dec" onChange={onFile} className="hidden" data-testid="import-file-input" />
          </label>
          <Button data-testid="import-submit" onClick={doImport} disabled={loading} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : replace ? "Save changes" : "Import deck"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
