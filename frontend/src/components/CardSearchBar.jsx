import React, { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, Plus, Loader2, X, SlidersHorizontal } from "lucide-react";
import { MANA_COLORS } from "@/lib/mtg";
import { ManaCost } from "@/components/ManaCost";
import { toast } from "sonner";

const COLORS = ["W", "U", "B", "R", "G"];
const TYPES = ["", "creature", "instant", "sorcery", "artifact", "enchantment", "planeswalker", "land"];

export default function CardSearchBar({ onAdd, target, setTarget, targets }) {
  const [query, setQuery] = useState("");
  const [colors, setColors] = useState([]);
  const [type, setType] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSug, setShowSug] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const sugTimer = useRef(null);
  const skipSug = useRef(false);
  const wrapRef = useRef(null);

  const toggleColor = (c) => setColors((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));
  const targetLabel = (targets.find((t) => t.key === target) || {}).label || "Mainboard";

  useEffect(() => {
    if (skipSug.current) { skipSug.current = false; return; }
    if (sugTimer.current) clearTimeout(sugTimer.current);
    if (query.trim().length < 2 || open) { setSuggestions([]); setShowSug(false); return; }
    sugTimer.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/cards/autocomplete", { params: { q: query } });
        setSuggestions(data.suggestions || []);
        setShowSug((data.suggestions || []).length > 0);
      } catch { setSuggestions([]); }
    }, 220);
    return () => sugTimer.current && clearTimeout(sugTimer.current);
  }, [query, open]);

  useEffect(() => {
    // composedPath() is captured when the click happens, so it still sees the search box even if
    // React has already removed the clicked suggestion from the page (contains() would miss it).
    const onClick = (e) => { if (wrapRef.current && !e.composedPath().includes(wrapRef.current)) { setOpen(false); setShowSug(false); } };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const runSearch = async (term) => {
    const q = term !== undefined ? term : query;
    if (!q.trim() && !colors.length && !type) { toast.error("Enter a search term or pick a filter"); return; }
    setShowSug(false);
    setLoading(true);
    setOpen(true);
    try {
      const { data } = await api.get("/cards/search", { params: { q, colors: colors.join(""), type } });
      setResults(data.cards);
      if (!data.cards.length) toast("No cards found");
    } catch { toast.error("Search failed. Try a different query."); setResults([]); }
    finally { setLoading(false); }
  };

  const addCard = (card) => {
    onAdd(card);
    toast.success(`Added ${card.name}`, { duration: 1000 });
  };

  // A suggestion is an exact card name, so add it straight away and clear the box for the next card.
  // If the exact lookup fails for any reason, fall back to showing normal search results.
  const pickSuggestion = async (name) => {
    skipSug.current = true;
    setShowSug(false);
    try {
      const { data } = await api.get("/cards/search", { params: { q: `!"${name}"` } });
      if (data.cards && data.cards.length) {
        addCard(data.cards[0]);
        skipSug.current = true;
        setQuery("");
        return;
      }
    } catch { /* fall through to a normal search */ }
    setQuery(name);
    runSearch(name);
  };

  return (
    <div ref={wrapRef} className="relative flex-1 min-w-0">
      <div className="flex items-center gap-2">
        <form onSubmit={(e) => { e.preventDefault(); runSearch(); }} className="relative flex-1 min-w-0">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 z-10" />
          <Input
            data-testid="card-search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => { if (suggestions.length && !open) setShowSug(true); }}
            placeholder={`Find and add cards to ${targetLabel.toLowerCase()}...`}
            className="pl-9 pr-10 h-9 bg-slate-900 border-slate-700 focus-visible:ring-amber-400 text-slate-100"
          />
          <button type="button" data-testid="toggle-filters" onClick={() => setShowFilters((s) => !s)}
            className={`absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded ${showFilters ? "text-amber-400" : "text-slate-500 hover:text-slate-300"}`}>
            <SlidersHorizontal className="w-4 h-4" />
          </button>
        </form>
        <Button data-testid="card-search-submit" onClick={() => runSearch()} className="h-9 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0">
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Search"}
        </Button>
        <div className="hidden sm:flex items-center gap-1 shrink-0">
          <span className="text-xs text-slate-500">Add to</span>
          <div className="flex rounded-lg border border-slate-700 overflow-hidden">
            {targets.map((t) => (
              <button key={t.key} data-testid={`target-${t.key}`} onClick={() => setTarget(t.key)}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${target === t.key ? "bg-amber-400 text-stone-900" : "bg-slate-900 text-slate-300 hover:bg-slate-800"}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* mobile target toggle */}
      <div className="flex sm:hidden items-center gap-1 mt-2">
        <span className="text-xs text-slate-500">Add to</span>
        <div className="flex rounded-lg border border-slate-700 overflow-hidden">
          {targets.map((t) => (
            <button key={t.key} data-testid={`target-m-${t.key}`} onClick={() => setTarget(t.key)}
              className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${target === t.key ? "bg-amber-400 text-stone-900" : "bg-slate-900 text-slate-300 hover:bg-slate-800"}`}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {showFilters && (
        <div className="mt-2 flex items-center gap-2 flex-wrap p-2 rounded-lg bg-slate-900 border border-slate-700">
          {COLORS.map((c) => (
            <button key={c} data-testid={`filter-color-${c}`} onClick={() => toggleColor(c)}
              style={{ background: colors.includes(c) ? MANA_COLORS[c].bg : "transparent", color: colors.includes(c) ? MANA_COLORS[c].text : "#94a3b8", borderColor: MANA_COLORS[c].bg }}
              className="w-7 h-7 rounded-full border text-xs font-bold transition-transform hover:scale-110">{c}</button>
          ))}
          <Select value={type || "any"} onValueChange={(v) => setType(v === "any" ? "" : v)}>
            <SelectTrigger data-testid="filter-type-trigger" className="w-36 h-8 bg-slate-950 border-slate-700 text-slate-200 text-sm ml-auto"><SelectValue placeholder="Any type" /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
              {TYPES.map((t) => <SelectItem key={t || "any"} value={t || "any"}>{t ? t[0].toUpperCase() + t.slice(1) : "Any type"}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Autocomplete */}
      {showSug && !open && (
        <div className="absolute z-40 left-0 right-0 mt-1 rounded-lg border border-slate-700 bg-slate-900/95 backdrop-blur-xl shadow-2xl overflow-hidden max-w-xl" data-testid="search-suggestions">
          {suggestions.map((s) => (
            <button type="button" key={s} data-testid={`suggestion-${s}`} onMouseDown={(e) => { e.preventDefault(); pickSuggestion(s); }}
              className="w-full text-left px-3 py-2 text-sm text-slate-200 hover:bg-slate-800 transition-colors truncate">{s}</button>
          ))}
        </div>
      )}

      {/* Results dropdown */}
      {open && (
        <div className="absolute z-40 left-0 right-0 mt-1 rounded-xl border border-slate-700 bg-slate-900/97 backdrop-blur-xl shadow-2xl overflow-hidden flex flex-col max-h-[70vh]" data-testid="search-results-panel">
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 shrink-0">
            <span className="text-xs text-slate-400">{loading ? "Searching..." : `${results.length} result${results.length === 1 ? "" : "s"} · adds to ${targetLabel}`}</span>
            <button data-testid="close-results" onClick={() => setOpen(false)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
          </div>
          <div className="overflow-y-auto p-3">
            {loading ? (
              <div className="h-32 flex items-center justify-center"><Loader2 className="w-6 h-6 text-amber-400 animate-spin" /></div>
            ) : (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3" data-testid="search-results">
                {results.map((card) => (
                  <div key={card.id} role="button" tabIndex={0} title={`Add ${card.name}`}
                    onClick={() => addCard(card)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); addCard(card); } }}
                    className="group relative rounded-lg overflow-hidden border border-slate-800 bg-slate-800 hover:border-amber-400/50 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400" data-testid={`search-card-${card.id}`}>
                    <div className="aspect-[0.716]">
                      {card.image ? <img src={card.image} alt={card.name} loading="lazy" className="w-full h-full object-cover" />
                        : <div className="w-full h-full flex items-center justify-center p-2 text-center text-xs text-slate-300">{card.name}</div>}
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-1.5">
                      <div className="w-full">
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <span className="text-[10px] font-medium text-white truncate">{card.name}</span>
                          <ManaCost cost={card.mana_cost} size={12} />
                        </div>
                        <Button size="sm" data-testid={`add-card-${card.id}`} onClick={(e) => { e.stopPropagation(); addCard(card); }}
                          className="w-full h-6 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-xs"><Plus className="w-3 h-3 mr-0.5" /> Add</Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
