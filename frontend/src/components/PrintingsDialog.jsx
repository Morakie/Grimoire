import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Loader2, Check } from "lucide-react";

export default function PrintingsDialog({ open, onOpenChange, card, onSelect }) {
  const [printings, setPrintings] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !card) return;
    setLoading(true);
    setPrintings([]);
    api.get("/cards/printings", { params: { name: card.name } })
      .then(({ data }) => setPrintings(data.printings))
      .catch(() => setPrintings([]))
      .finally(() => setLoading(false));
  }, [open, card]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900/95 backdrop-blur-xl border-slate-700 text-slate-100 max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" data-testid="printings-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Choose printing — {card?.name}</DialogTitle>
          <DialogDescription className="text-slate-400">Select an alternate printing to change this card's displayed art.</DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto flex-1 -mx-2 px-2">
          {loading && <div className="h-40 flex items-center justify-center"><Loader2 className="w-7 h-7 text-amber-400 animate-spin" /></div>}
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
            {printings.map((p) => {
              const active = p.id === card?.id;
              return (
                <button
                  key={p.id}
                  data-testid={`printing-${p.id}`}
                  onClick={() => { onSelect(p); onOpenChange(false); }}
                  className={`relative rounded-lg overflow-hidden border-2 transition-all hover:scale-[1.03] ${active ? "border-amber-400" : "border-transparent hover:border-slate-600"}`}
                >
                  <div className="aspect-[0.716] bg-slate-800">
                    {p.image && <img src={p.image} alt={p.set_name} loading="lazy" className="w-full h-full object-cover" />}
                  </div>
                  {active && <span className="absolute top-1 right-1 bg-amber-400 text-stone-900 rounded-full p-0.5"><Check className="w-3 h-3" /></span>}
                  <div className="absolute bottom-0 inset-x-0 bg-black/80 px-1.5 py-1 text-[10px] text-slate-200 truncate uppercase">{p.set} · {p.set_name}</div>
                </button>
              );
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
