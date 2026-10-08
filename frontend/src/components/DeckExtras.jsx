import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Sparkles, CircleDollarSign } from "lucide-react";

const money = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Bottom of the deck board: the tokens the deck makes, and a small price line (prices from Scryfall, today). */
export default function DeckExtras({ deck }) {
  const [data, setData] = useState(null);
  const cards = useMemo(() => [...deck.commander, ...deck.mainboard, ...deck.sideboard].filter((c) => c.id && !c.is_custom), [deck]);
  const key = useMemo(() => [...new Set(cards.map((c) => c.id))].sort().join(","), [cards]);

  useEffect(() => {
    if (!key) { setData(null); return undefined; }
    let alive = true;
    const t = setTimeout(() => {
      api.post("/cards/extras", { ids: key.split(",") })
        .then(({ data: d }) => { if (alive) setData(d); })
        .catch(() => { /* extras are optional */ });
    }, 1200);
    return () => { alive = false; clearTimeout(t); };
  }, [key]);

  if (!data || !cards.length) return null;
  const byId = Object.fromEntries(cards.map((c) => [c.id, c]));

  const price = (list) => list.reduce((acc, c) => {
    const p = data.prices[c.id] || {};
    const usd = parseFloat(p.usd ?? p.usd_foil);
    const tix = parseFloat(p.tix);
    if (!Number.isNaN(usd)) acc.usd += usd * (c.quantity || 1); else acc.missing += 1;
    if (!Number.isNaN(tix)) acc.tix += tix * (c.quantity || 1);
    return acc;
  }, { usd: 0, tix: 0, missing: 0 });
  const main = price([...deck.commander, ...deck.mainboard]);
  const side = price(deck.sideboard);

  return (
    <div className="mt-10 space-y-6" data-testid="deck-extras">
      {data.tokens.length > 0 && (
        <section data-testid="deck-tokens">
          <div className="flex items-center gap-2 mb-3">
            <h3 className="text-sm font-display font-bold uppercase tracking-wide text-amber-400/90 flex items-center gap-1.5"><Sparkles className="w-3.5 h-3.5" /> Tokens</h3>
            <span className="text-xs text-slate-500 tabular-nums">{data.tokens.length}</span>
          </div>
          <div className="flex flex-wrap gap-3">
            {data.tokens.map((t) => (
              <HoverCard key={t.id} openDelay={100} closeDelay={60}>
                <HoverCardTrigger asChild>
                  <div tabIndex={0} className="w-[96px] sm:w-[110px] rounded-md overflow-hidden border border-slate-800 bg-slate-800 aspect-[0.716] outline-none focus:ring-2 focus:ring-amber-400" data-testid={`token-${t.id}`}>
                    {t.image ? <img src={t.image} alt={t.name} loading="lazy" className="w-full h-full object-cover" />
                      : <div className="w-full h-full flex items-center justify-center p-1 text-center text-[11px] text-slate-300">{t.name}</div>}
                  </div>
                </HoverCardTrigger>
                <HoverCardContent side="top" className="w-60 p-0 bg-slate-900 border-slate-700 overflow-hidden">
                  {t.image && <img src={t.image} alt={t.name} className="w-full" />}
                  <div className="p-2.5 text-xs text-slate-300">
                    <span className="text-slate-500">Made by </span>
                    {t.made_by.map((id) => byId[id]?.name).filter(Boolean).join(", ")}
                  </div>
                </HoverCardContent>
              </HoverCard>
            ))}
          </div>
        </section>
      )}

      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-xs text-slate-500 border-t border-slate-800 pt-3" data-testid="deck-price">
        <CircleDollarSign className="w-3.5 h-3.5 text-slate-600" />
        <span>Deck price <span className="text-slate-300 tabular-nums">{money(main.usd)}</span>
          {main.tix > 0 && <span className="tabular-nums"> · {main.tix.toFixed(1)} TIX</span>}</span>
        {side.usd > 0 && <span>Sideboard <span className="text-slate-300 tabular-nums">{money(side.usd)}</span></span>}
        <span className="text-slate-600">Scryfall prices for these printings{main.missing ? `, ${main.missing} without a price` : ""}</span>
      </div>
    </div>
  );
}
