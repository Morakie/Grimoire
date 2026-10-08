import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Minus, Plus, Loader2 } from "lucide-react";
import { BASIC_COLORS, BASIC_LABEL, MANA_COLORS, getBasics } from "@/lib/mtg";
import { toast } from "sonner";

/**
 * Add or remove basic lands without searching. Basics come from outside the deck's pool (drafted decks
 * add them freely), and changes apply straight to the chosen section.
 */
export default function BasicLandsDialog({ open, onOpenChange, deck, target, onChange }) {
  const [basics, setBasics] = useState(null);

  useEffect(() => {
    if (!open || basics) return;
    getBasics(api).then(setBasics).catch(() => { toast.error("Couldn't load basic lands"); onOpenChange(false); });
  }, [open, basics, onOpenChange]);

  const list = deck[target] || [];
  const countOf = (name) => list.filter((c) => c.name === name).reduce((n, c) => n + (c.quantity || 0), 0);
  const total = list.reduce((n, c) => n + (c.quantity || 0), 0);

  const change = (col, delta) => {
    const card = basics[col];
    const next = [...list];
    const idx = next.findIndex((c) => c.name === card.name);
    if (idx >= 0) {
      const q = next[idx].quantity + delta;
      if (q <= 0) next.splice(idx, 1);
      else next[idx] = { ...next[idx], quantity: q };
    } else if (delta > 0) {
      next.push({ ...card, quantity: delta });
    }
    onChange(target, next);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-sm" data-testid="basic-lands-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Basic lands</DialogTitle>
          <DialogDescription className="text-slate-400">
            Adding to the {target}. It has <span className="text-slate-200 tabular-nums">{total}</span> cards.
          </DialogDescription>
        </DialogHeader>
        {!basics ? (
          <div className="py-8 flex justify-center"><Loader2 className="w-6 h-6 text-amber-400 animate-spin" /></div>
        ) : (
          <div className="divide-y divide-slate-800">
            {BASIC_COLORS.filter((col) => basics[col]).map((col) => {
              const n = countOf(basics[col].name);
              return (
                <div key={col} className="flex items-center gap-3 py-2" data-testid={`basic-${col}`}>
                  <span className="w-4 h-4 rounded-full border border-black/30 shrink-0" style={{ background: MANA_COLORS[col].bg }} />
                  <span className="flex-1 text-sm">{BASIC_LABEL[col]}</span>
                  <Button size="icon" variant="outline" data-testid={`basic-dec-${col}`} onClick={() => change(col, -1)} disabled={!n}
                    className="h-8 w-8 bg-slate-950 border-slate-700 text-slate-200 hover:bg-slate-800"><Minus className="w-4 h-4" /></Button>
                  <span className="w-7 text-center tabular-nums font-semibold text-amber-400" data-testid={`basic-count-${col}`}>{n}</span>
                  <Button size="icon" variant="outline" data-testid={`basic-inc-${col}`} onClick={() => change(col, 1)}
                    className="h-8 w-8 bg-slate-950 border-slate-700 text-slate-200 hover:bg-slate-800"><Plus className="w-4 h-4" /></Button>
                </div>
              );
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
