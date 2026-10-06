import React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Download, Copy, FileDown } from "lucide-react";
import { toast } from "sonner";

function cardLine(c) {
  const setc = (c.set || "").toUpperCase();
  const cn = c.collector_number || "";
  return setc && cn ? `${c.quantity} ${c.name} (${setc}) ${cn}` : `${c.quantity} ${c.name}`;
}

export function buildExport(deck) {
  const out = [];
  if (deck.commander && deck.commander.length) {
    out.push("Commander");
    deck.commander.forEach((c) => out.push(cardLine(c)));
    out.push("");
  }
  (deck.mainboard || []).forEach((c) => out.push(cardLine(c)));
  if (deck.sideboard && deck.sideboard.length) {
    out.push("");
    out.push("Sideboard");
    deck.sideboard.forEach((c) => out.push(cardLine(c)));
  }
  return out.join("\n").trim();
}

export default function ExportDialog({ open, onOpenChange, deck }) {
  const text = buildExport(deck);

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
          <DialogDescription className="text-slate-400">
            Includes set code and collector number, e.g. <span className="text-slate-300">1 Demonic Tutor (UMA) 93</span>. Compatible with Moxfield, MTGA and Grimoire import.
          </DialogDescription>
        </DialogHeader>
        <Textarea data-testid="export-textarea" readOnly value={text} className="min-h-[260px] bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400" />
        <DialogFooter className="gap-2">
          <Button data-testid="export-download" variant="outline" onClick={download} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800"><FileDown className="w-4 h-4 mr-1" /> Download .txt</Button>
          <Button data-testid="export-copy" onClick={copy} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold"><Copy className="w-4 h-4 mr-1" /> Copy</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
