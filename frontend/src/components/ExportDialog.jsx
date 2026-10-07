import React, { useState } from "react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Download, Copy, FileDown } from "lucide-react";
import { toast } from "sonner";

// Each site writes decklists a little differently; these match what each one exports
// so the text can be pasted straight back into it (and into Grimoire's importer).
export const EXPORT_STYLES = [
  { value: "arena", label: "Grimoire / Arena", hint: "Commander, Deck and Sideboard headings with printings. Best for re-importing here." },
  { value: "moxfield", label: "Moxfield", hint: "Commanders first, then the deck, with set code and collector number." },
  { value: "mtgo", label: "MTGO / plain text", hint: "Card names only. Commanders go last, after a blank line." },
];

function cardName(c, style) {
  if (!c.name.includes("//")) return c.name;
  const faces = c.name.split("//").map((f) => f.trim());
  return style === "mtgo" ? faces.join("/") : style === "moxfield" ? faces.join(" / ") : faces.join(" // ");
}

function cardLine(c, style) {
  const name = cardName(c, style);
  const setc = (c.set || "").toUpperCase();
  const cn = c.collector_number || "";
  if (style === "mtgo" || !setc || !cn) return `${c.quantity} ${name}`;
  return `${c.quantity} ${name} (${setc}) ${cn}`;
}

export function buildExport(deck, style = "arena") {
  const lines = (list) => (list || []).map((c) => cardLine(c, style));
  const commander = lines(deck.commander);
  // Moxfield and MTGO list the deck alphabetically; matching that lets our importer spot the commanders.
  const byName = (list) => [...(list || [])].sort((a, b) => a.name.localeCompare(b.name));
  const main = lines(style === "arena" ? deck.mainboard : byName(deck.mainboard));
  const side = lines(deck.sideboard);
  let out;
  if (style === "moxfield") {
    out = [...commander, ...main];
    if (side.length) out.push("", "SIDEBOARD:", ...side);
  } else if (style === "mtgo") {
    out = [...main];
    if (side.length) out.push("", ...side);
    if (commander.length) out.push("", ...commander);
  } else {
    out = [];
    if (commander.length) out.push("Commander", ...commander, "", "Deck");
    out.push(...main);
    if (side.length) out.push("", "Sideboard", ...side);
  }
  return out.join("\n").trim();
}

export default function ExportDialog({ open, onOpenChange, deck }) {
  const [style, setStyle] = useState("arena");
  const text = buildExport(deck, style);
  const hint = EXPORT_STYLES.find((x) => x.value === style).hint;

  const copy = () => { navigator.clipboard.writeText(text); toast.success("Decklist copied"); };
  const download = () => {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(deck.name || "deck").replace(/[^a-z0-9]+/gi, "_")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Downloaded .txt");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-lg" data-testid="export-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Download className="w-5 h-5 text-amber-400" /> Export decklist</DialogTitle>
          <DialogDescription className="text-slate-400">{hint}</DialogDescription>
        </DialogHeader>
        <Select value={style} onValueChange={setStyle}>
          <SelectTrigger data-testid="export-style" className="h-9 bg-slate-950 border-slate-700 text-slate-200 text-sm"><SelectValue /></SelectTrigger>
          <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
            {EXPORT_STYLES.map((x) => <SelectItem key={x.value} value={x.value}>{x.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Textarea data-testid="export-textarea" readOnly value={text} className="min-h-[260px] bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400" />
        <DialogFooter className="gap-2">
          <Button data-testid="export-download" variant="outline" onClick={download} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800"><FileDown className="w-4 h-4 mr-1" /> Download .txt</Button>
          <Button data-testid="export-copy" onClick={copy} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold"><Copy className="w-4 h-4 mr-1" /> Copy</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
