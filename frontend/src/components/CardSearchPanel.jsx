import React, { useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus, Loader2 } from "lucide-react";
import { MANA_COLORS } from "@/lib/mtg";
import { ManaCost } from "@/components/ManaCost";
import { toast } from "sonner";

const COLORS = ["W", "U", "B", "R", "G"];
const TYPES = ["", "creature", "instant", "sorcery", "artifact", "enchantment", "planeswalker", "land"];

export default function CardSearchPanel({ onAdd, targetLabel }) {
  const [query, setQuery] = useState("");
  const [colors, setColors] = useState([]);
  const [type, setType] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const toggleColor = (c) => setColors((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));

  const doSearch = async (e) => {
    e && e.preventDefault();
    if (!query.trim() && !colors.length && !type) {
      toast.error("Enter a search term or pick a filter");
      return;
    }
    setLoading(true);
    setSearched(true);
    try {
      const { data } = await api.get("/cards/search", {
        params: { q: query, colors: colors.join(""), type },
      });
      setResults(data.cards);
      if (!data.cards.length) toast("No cards found");
    } catch (err) {
      toast.error("Search failed. Try a different query.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full lg:w-[38%] h-full border-r border-slate-800 bg-[#070c17] flex flex-col" data-testid="card-search-panel">
      <div className="p-4 border-b border-slate-800 space-y-3">
        <form onSubmit={doSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <Input
              data-testid="card-search-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search cards by name..."
              className="pl-9 bg-slate-900 border-slate-700 focus-visible:ring-amber-400 text-slate-100"
            />
          </div>
          <Button type="submit" data-testid="card-search-submit" className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
          </Button>
        </form>
        <div className="flex items-center gap-2 flex-wrap">
          {COLORS.map((c) => (
            <button
              key={c}
              data-testid={`filter-color-${c}`}
              onClick={() => toggleColor(c)}
              style={{
                background: colors.includes(c) ? MANA_COLORS[c].bg : "transparent",
                color: colors.includes(c) ? MANA_COLORS[c].text : "#94a3b8",
                borderColor: MANA_COLORS[c].bg,
              }}
              className="w-7 h-7 rounded-full border text-xs font-bold transition-transform hover:scale-110"
            >
              {c}
            </button>
          ))}
          <Select value={type || "any"} onValueChange={(v) => setType(v === "any" ? "" : v)}>
            <SelectTrigger data-testid="filter-type-trigger" className="w-36 h-8 bg-slate-900 border-slate-700 text-slate-200 text-sm ml-auto">
              <SelectValue placeholder="Any type" />
            </SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
              {TYPES.map((t) => (
                <SelectItem key={t || "any"} value={t || "any"}>
                  {t ? t[0].toUpperCase() + t.slice(1) : "Any type"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {!searched && (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-500 gap-2 px-6">
            <Search className="w-10 h-10 text-slate-700" />
            <p className="text-sm">Search the entire Magic multiverse.</p>
            <p className="text-xs text-slate-600">Adds go to <span className="text-amber-400 font-semibold">{targetLabel}</span></p>
          </div>
        )}
        {loading && (
          <div className="h-full flex items-center justify-center"><Loader2 className="w-7 h-7 text-amber-400 animate-spin" /></div>
        )}
        {!loading && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="search-results">
            {results.map((card) => (
              <div key={card.id} className="group relative rounded-xl overflow-hidden border border-slate-800 bg-slate-900 hover:border-amber-400/50 transition-colors" data-testid={`search-card-${card.id}`}>
                <div className="aspect-[0.716] bg-slate-800">
                  {card.image ? (
                    <img src={card.image} alt={card.name} loading="lazy" className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center p-2 text-center text-xs text-slate-400">{card.name}</div>
                  )}
                </div>
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2">
                  <div className="w-full">
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-[11px] font-medium text-white truncate">{card.name}</span>
                      <ManaCost cost={card.mana_cost} size={13} />
                    </div>
                    <Button
                      size="sm"
                      data-testid={`add-card-${card.id}`}
                      onClick={() => { onAdd(card); toast.success(`Added ${card.name}`, { duration: 1200 }); }}
                      className="w-full h-7 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-xs"
                    >
                      <Plus className="w-3 h-3 mr-1" /> Add
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
