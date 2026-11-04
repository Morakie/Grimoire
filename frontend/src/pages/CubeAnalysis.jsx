import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { resolveCube, stepError } from "@/lib/cube";
import { deckName, deckCol } from "@/lib/deckTypes";
import { ManaCost } from "@/components/ManaCost";
import { useAuth } from "@/context/AuthContext";
import { Sparkles, Loader2, Library, RefreshCw, LayoutGrid, Layers, Zap, BarChart3, Search, X, ExternalLink, List as ListIcon, Image as ImageIcon } from "lucide-react";

// Cube Analysis: a breakdown of a whole cube (backend/draftbot/analysis.py). The cube is loaded as a Bot Brain
// pool (CubeCobra Elo and links, Spellbook combos), so what this page shows is what the draft bots see.

const MANA = { W: "#f2e8c9", U: "#3b82f6", B: "#a855f7", R: "#ef4444", G: "#22c55e" };
const STORE = "grim_analysis";
const GROUP_CUBE = "43fd5f2a-942e-40c3-a563-bf3a7ce0cc22";
const PRESETS = [["Group cube", GROUP_CUBE], ["Group cube + PowerLSV", `${GROUP_CUBE} + PowerLSV`], ["PowerLSV", "PowerLSV"]];

const COLUMNS = [
  ["W", "White", "bg-[#3a3826]"], ["U", "Blue", "bg-[#1d3047]"], ["B", "Black", "bg-[#2a2433]"], ["R", "Red", "bg-[#43222a]"],
  ["G", "Green", "bg-[#1f3a2a]"], ["C", "Colorless", "bg-[#2a2f38]"], ["M", "Multicolored", "bg-[#3d3720]"], ["L", "Lands", "bg-[#3b2d22]"],
];
const TYPE_ORDER = ["creature", "planeswalker", "battle", "instant", "sorcery", "artifact", "enchantment", "land", "other"];
const TYPE_LABEL = { creature: "Creature", planeswalker: "Planeswalker", battle: "Battle", instant: "Instant", sorcery: "Sorcery", artifact: "Artifact", enchantment: "Enchantment", land: "Land", other: "Other" };
const GROUP_NAMES = {
  WU: "Azorius", UB: "Dimir", BR: "Rakdos", RG: "Gruul", WG: "Selesnya", WB: "Orzhov", UR: "Izzet", BG: "Golgari", WR: "Boros", UG: "Simic",
  WUG: "Bant", WUB: "Esper", UBR: "Grixis", BRG: "Jund", WRG: "Naya", WBG: "Abzan", WUR: "Jeskai", UBG: "Sultai", WBR: "Mardu", URG: "Temur",
  WUBRG: "Five-color",
};
const groupName = (cols) => GROUP_NAMES[cols] || (cols.length === 4 ? "Four-color" : cols.length === 0 ? "Colorless" : cols);
const ROLE_BADGE = { key: ["Key", "border-amber-400/70 text-amber-300"], core: ["Core", "border-sky-400/60 text-sky-300"], fits: ["Fits", "border-slate-600 text-slate-300"], played: ["Played", "border-slate-700 text-slate-400"] };
const LABEL_STYLE = { Strong: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40", Viable: "bg-amber-400/15 text-amber-300 border-amber-400/40", Thin: "bg-slate-700/40 text-slate-300 border-slate-600", Unlikely: "bg-slate-800/60 text-slate-500 border-slate-700" };
const SORTS = [["fit", "Fit"], ["rate", "Play rate"], ["elo", "Elo rank"], ["name", "Name"], ["type", "Type"], ["cmc", "Mana value"], ["color", "Color"]];

function load(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function save(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* blocked */ } }
const colourKey = (c) => (c.colors.length === 0 ? 9 : c.colors.length > 1 ? 6 + c.colors.length : "WUBRG".indexOf(c.colors));

function sortCards(list, how, extra = {}) {
  const by = {
    elo: (a, b) => a.rank - b.rank,
    name: (a, b) => a.name.localeCompare(b.name),
    type: (a, b) => TYPE_ORDER.indexOf(a.type) - TYPE_ORDER.indexOf(b.type) || a.cmc - b.cmc || a.name.localeCompare(b.name),
    cmc: (a, b) => a.cmc - b.cmc || a.name.localeCompare(b.name),
    color: (a, b) => colourKey(a) - colourKey(b) || a.cmc - b.cmc || a.name.localeCompare(b.name),
    fit: (a, b) => (extra.fit?.[b.id] ?? 0) - (extra.fit?.[a.id] ?? 0) || a.rank - b.rank,
    rate: (a, b) => (extra.rate?.[b.id] ?? -1) - (extra.rate?.[a.id] ?? -1) || (extra.fit?.[b.id] ?? 0) - (extra.fit?.[a.id] ?? 0) || a.rank - b.rank,
  }[how] || ((a, b) => a.rank - b.rank);
  return [...list].sort(by);
}

function Pips({ colors, size = 10 }) {
  if (!colors) return <span className="rounded-full inline-block border border-white/10" style={{ width: size, height: size, background: "#94a3b8" }} />;
  return <span className="inline-flex gap-0.5">{[...colors].map((c) => <span key={c} className="rounded-full inline-block border border-white/20" style={{ width: size, height: size, background: MANA[c] }} />)}</span>;
}

// ---------------------------------------------------------------- card preview and details

function useHover() {
  const [hover, setHover] = useState(null);
  const bind = useCallback((card) => ({
    onMouseEnter: (e) => setHover({ card, x: e.clientX, y: e.clientY }),
    onMouseMove: (e) => setHover((h) => (h ? { ...h, x: e.clientX, y: e.clientY } : h)),
    onMouseLeave: () => setHover(null),
  }), []);
  return [hover, bind, setHover];
}

function HoverPreview({ hover }) {
  if (!hover?.card?.image) return null;
  const w = 230;
  const left = hover.x + 24 + w > window.innerWidth ? hover.x - w - 24 : hover.x + 24;
  const top = Math.max(8, Math.min(hover.y - 160, window.innerHeight - 330));
  return <img src={hover.card.image} alt="" aria-hidden="true" className="fixed z-50 rounded-xl shadow-2xl pointer-events-none hidden md:block" style={{ left, top, width: w }} />;
}

function CardPanel({ card, data, onClose, onPick }) {
  if (!card) return null;
  const combos = data.combos.filter((r) => r.pieces.includes(card.id));
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose} role="dialog" aria-modal="true" aria-label={card.name}>
      <div className="w-full max-w-md h-full overflow-y-auto bg-[#0b1120] border-l border-slate-800 p-5 space-y-5" onClick={(e) => e.stopPropagation()} data-testid="analysis-card-panel">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-2xl font-bold leading-tight">{card.name}</h2>
          <button type="button" onClick={onClose} className="p-1 rounded hover:bg-slate-800 text-slate-400" aria-label="Close"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex gap-4">
          {card.image && <img src={card.image} alt={card.name} className="w-40 rounded-lg border border-slate-700 self-start shrink-0" />}
          <dl className="text-sm space-y-1.5 text-slate-300">
            <div><dt className="inline text-slate-500">Elo </dt><dd className="inline tabular-nums">{card.elo} (#{card.rank} of {data.cards.length})</dd></div>
            <div><dt className="inline text-slate-500">Type </dt><dd className="inline">{card.type_line}</dd></div>
            {card.mana_cost && <div><ManaCost cost={card.mana_cost} size={15} /></div>}
            <div><dt className="inline text-slate-500">Synergy links </dt><dd className="inline tabular-nums">{card.links}</dd></div>
            {card.roles.length > 0 && <div className="flex flex-wrap gap-1 pt-1">{card.roles.map((r) => <span key={r} className="text-[11px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-400">{data.roles[r]}</span>)}</div>}
          </dl>
        </div>
        <section>
          <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Deck types it fits</h3>
          {card.fits.length === 0 ? <p className="text-sm text-slate-500">Not tied to a deck type: it goes in any deck of its colors.</p> : (
            <ul className="space-y-1.5">
              {card.fits.map(([t, v]) => (
                <li key={t} className="flex items-center gap-2 text-sm">
                  <span className="w-36 truncate" style={{ color: deckCol(t) }}>{deckName(t)}</span>
                  <span className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden"><span className="block h-full" style={{ width: `${v * 100}%`, background: deckCol(t) }} /></span>
                  <span className="text-[11px] text-slate-400 w-10 text-right">{card.keys.includes(t) ? "Key" : `${Math.round(v * 100)}%`}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        {combos.length > 0 && (
          <section>
            <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Combos ({combos.length})</h3>
            <ul className="space-y-2">
              {combos.slice(0, 20).map((r) => (
                <li key={r.i} className="text-sm">
                  <span className="text-slate-200">{r.pieces.filter((p) => p !== card.id).map((p) => data.byId[p]?.name).map((n, k) => <React.Fragment key={k}>{k > 0 && " + "}<button type="button" className="hover:text-amber-300" onClick={() => onPick(r.pieces.filter((p) => p !== card.id)[k])}>{n}</button></React.Fragment>)}</span>
                  {r.produces.length > 0 && <span className="block text-xs text-slate-500">{r.produces.join(" · ")}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- List (CubeCobra-style columns)

function ListView({ data, bind, onPick }) {
  const [q, setQ] = useState("");
  const [order, setOrder] = useState("cmc");
  const [highlight, setHighlight] = useState("");
  const fitIds = useMemo(() => {
    const d = data.decks.find((x) => x.type === highlight);
    return d ? new Set(d.members.filter((m) => m.fit >= 0.3).map((m) => m.id)) : null;
  }, [data, highlight]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? data.cards.filter((c) => c.name.toLowerCase().includes(s) || c.type_line.toLowerCase().includes(s)) : data.cards;
  }, [data, q]);
  const columns = useMemo(() => COLUMNS.map(([k, label, bg]) => {
    const cards = shown.filter((c) => c.column === k);
    const groups = new Map();
    cards.forEach((c) => {
      const g = k === "M" ? groupName(c.colors) : k === "L" ? (c.produces.length >= 2 ? groupName(c.produces) : c.produces ? "Mono-color" : "Colorless / utility") : TYPE_LABEL[c.type];
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(c);
    });
    let keys = [...groups.keys()];
    if (k === "M" || k === "L") keys.sort((a, b) => groups.get(b).length - groups.get(a).length);
    else keys.sort((a, b) => TYPE_ORDER.indexOf(a.toLowerCase()) - TYPE_ORDER.indexOf(b.toLowerCase()));
    return { k, label, bg, count: cards.length, groups: keys.map((g) => [g, sortCards(groups.get(g), order)]) };
  }), [shown, order]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative flex-1 min-w-[200px] max-w-md">
          <span className="sr-only">Filter cards</span>
          <Search className="w-4 h-4 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by name or type" className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-sm" data-testid="analysis-list-filter" />
        </label>
        <label className="text-sm text-slate-400 flex items-center gap-1.5">Sort
          <select value={order} onChange={(e) => setOrder(e.target.value)} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200" data-testid="analysis-list-sort">
            <option value="cmc">Mana value</option><option value="elo">Elo rank</option><option value="name">Name</option>
          </select>
        </label>
        <label className="text-sm text-slate-400 flex items-center gap-1.5">Highlight
          <select value={highlight} onChange={(e) => setHighlight(e.target.value)} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200" data-testid="analysis-list-highlight">
            <option value="">No deck type</option>
            {data.decks.filter((d) => d.keys > 0).map((d) => <option key={d.type} value={d.type}>{deckName(d.type)}</option>)}
          </select>
        </label>
        <span className="text-sm text-slate-500 tabular-nums">{shown.length} cards</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8 gap-2" data-testid="analysis-list">
        {columns.map((col) => (
          <div key={col.k} className="min-w-0">
            <div className="text-center pb-1"><div className="font-display font-semibold">{col.label}</div><div className="text-xs text-slate-400 tabular-nums">({col.count})</div></div>
            <div className="space-y-2">
              {col.groups.map(([g, cards]) => (
                <div key={g} className={`rounded border border-slate-700/70 overflow-hidden ${col.bg}`}>
                  <div className="text-[11px] font-semibold text-center py-0.5 bg-black/30 border-b border-slate-700/70">{g} ({cards.length})</div>
                  <ul>
                    {cards.map((c) => (
                      <li key={c.id}>
                        <button type="button" onClick={() => onPick(c.id)} {...bind(c)}
                          className={`w-full text-left px-1.5 py-[3px] text-[12px] leading-tight truncate hover:bg-white/10 border-b border-black/20 ${fitIds && !fitIds.has(c.id) ? "opacity-25" : ""}`}
                          style={fitIds && fitIds.has(c.id) ? { boxShadow: `inset 3px 0 0 ${deckCol(highlight)}` } : undefined}>
                          {c.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Deck types

function DecksView({ data, bind, onPick }) {
  const [sel, setSel] = useState(() => load(STORE, {}).deck || data.decks[0]?.type);
  const [sort, setSort] = useState("fit");
  const [role, setRole] = useState("all");
  const [view, setView] = useState("list");
  const [showAll, setShowAll] = useState(false);
  const deck = data.decks.find((d) => d.type === sel) || data.decks[0];
  useEffect(() => { if (deck) save(STORE, { ...load(STORE, {}), deck: deck.type }); }, [deck]);
  const listed = data.decks.filter((d) => showAll || d.keys > 0);
  const rows = useMemo(() => {
    if (!deck) return [];
    const fit = {}, rate = {};
    deck.members.forEach((m) => { fit[m.id] = m.fit; rate[m.id] = m.rate; });
    const cards = deck.members.filter((m) => role === "all" || m.role === role).map((m) => data.byId[m.id]).filter(Boolean);
    return sortCards(cards, sort, { fit, rate }).map((c) => ({ c, m: deck.members.find((m) => m.id === c.id) }));
  }, [deck, sort, role, data]);
  if (!deck) return <p className="text-sm text-slate-400">No deck types found in this cube.</p>;
  const combos = deck.combos.map((i) => data.comboByI[i]).filter(Boolean);

  return (
    <div className="grid lg:grid-cols-[280px_1fr] gap-6">
      <aside className="space-y-1" data-testid="analysis-deck-list">
        {listed.map((d) => (
          <button key={d.type} type="button" onClick={() => setSel(d.type)} aria-pressed={d.type === deck.type}
            className={`w-full text-left rounded-lg border px-3 py-2 ${d.type === deck.type ? "border-amber-400/70 bg-slate-900" : "border-slate-800 hover:border-slate-600"}`} data-testid={`analysis-deck-${d.type}`}>
            <span className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 min-w-0"><span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: deckCol(d.type) }} /><span className="truncate font-medium">{deckName(d.type)}</span></span>
              <span className={`text-[11px] px-1.5 py-0.5 rounded border shrink-0 ${LABEL_STYLE[d.label]}`}>{d.label}</span>
            </span>
            <span className="flex items-center justify-between mt-1 text-[11px] text-slate-500 tabular-nums">
              <span>{d.keys} key · {d.depth} deep · {d.combos.length} combos</span>
              <Pips colors={Object.keys(d.colors).join("")} size={8} />
            </span>
          </button>
        ))}
        <button type="button" onClick={() => setShowAll((v) => !v)} className="text-xs text-slate-500 hover:text-slate-300 px-1 pt-1">
          {showAll ? "Hide deck types with no key cards" : `Show all ${data.decks.length} deck types`}
        </button>
      </aside>

      <section className="min-w-0 space-y-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-2xl font-bold" style={{ color: deckCol(deck.type) }}>{deckName(deck.type)}</h2>
            <span className={`text-sm px-2 py-0.5 rounded border ${LABEL_STYLE[deck.label]}`}>{deck.label} · {deck.score}/100</span>
          </div>
          <dl className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3 text-sm">
            {[["Key cards", `${deck.keys}`], ["Deep cards", deck.depth], ["Combos", deck.combos.length], ["Avg Elo (best 23)", deck.avg_elo || "–"],
              ["Seats it can feed", deck.seats ? `about ${deck.seats}` : "under 1"], ["Colors", Object.keys(deck.colors).length ? <Pips colors={Object.keys(deck.colors).join("")} size={12} /> : "Any"]].map(([k, v]) => (
              <div key={k}><dt className="text-[11px] uppercase tracking-wide text-slate-500">{k}</dt><dd className="text-lg font-semibold tabular-nums">{v}</dd></div>
            ))}
          </dl>
          <p className="text-xs text-slate-500">
            Key cards define the deck type; deep cards are cards that fit it well (fit 50% or more, from what CubeCobra drafters put together).
            The score weighs key cards most, then depth, then combos.
            {deck.plan && <> Play rate is how often real drafters put a card in <span className="text-slate-300">{deck.plan}</span> decks on CubeCobra ({deck.plan_decks.toLocaleString()} decks), counting only cubes that had it.</>}
          </p>
          {deck.missing_keys.length > 0 && <p className="text-xs text-slate-500">Key cards not in this cube: {deck.missing_keys.join(", ")}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-slate-400 flex items-center gap-1.5">Sort
            <select value={sort} onChange={(e) => setSort(e.target.value)} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-slate-200" data-testid="analysis-deck-sort">
              {SORTS.filter(([k]) => k !== "rate" || deck.plan).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <div className="inline-flex rounded-lg border border-slate-700 overflow-hidden text-sm">
            {[["all", "All"], ["key", "Key"], ["core", "Core"], ["fits", "Fits"], ["played", "Played"]].map(([k, l]) => (
              <button key={k} type="button" onClick={() => setRole(k)} aria-pressed={role === k} className={`px-2.5 py-1.5 ${role === k ? "bg-amber-400 text-stone-900 font-semibold" : "text-slate-300 hover:bg-slate-800"}`} data-testid={`analysis-role-${k}`}>{l}</button>
            ))}
          </div>
          <div className="inline-flex rounded-lg border border-slate-700 overflow-hidden ml-auto">
            {[["list", ListIcon, "List"], ["images", ImageIcon, "Images"]].map(([k, Icon, l]) => (
              <button key={k} type="button" onClick={() => setView(k)} aria-pressed={view === k} aria-label={l} title={l} className={`px-2.5 py-1.5 ${view === k ? "bg-amber-400 text-stone-900" : "text-slate-300 hover:bg-slate-800"}`} data-testid={`analysis-view-${k}`}><Icon className="w-4 h-4" /></button>
            ))}
          </div>
          <span className="text-sm text-slate-500 tabular-nums w-full sm:w-auto">{rows.length} cards</span>
        </div>

        {view === "images" ? (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 xl:grid-cols-7 gap-2" data-testid="analysis-deck-images">
            {rows.map(({ c, m }) => (
              <button key={c.id} type="button" onClick={() => onPick(c.id)} className="relative text-left group" title={c.name}>
                {c.image ? <img src={c.image} alt={c.name} loading="lazy" className="w-full rounded-lg border border-slate-800 group-hover:border-amber-400/60" /> : <div className="aspect-[5/7] rounded-lg border border-slate-800 p-2 text-xs">{c.name}</div>}
                <span className={`absolute top-1 left-1 text-[10px] px-1 rounded border bg-black/70 ${ROLE_BADGE[m.role][1]}`}>{ROLE_BADGE[m.role][0]}</span>
                <span className="absolute bottom-1 right-1 text-[10px] px-1 rounded bg-black/70 text-slate-200 tabular-nums">{sort === "rate" && m.rate != null ? `${m.rate}%` : `${Math.round(m.fit * 100)}%`}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm" data-testid="analysis-deck-table">
              <thead className="text-[11px] uppercase tracking-wide text-slate-500 bg-slate-900/70">
                <tr><th className="text-left font-medium px-3 py-2">Card</th><th className="text-left font-medium px-2 py-2 hidden sm:table-cell">Cost</th><th className="text-left font-medium px-2 py-2 hidden md:table-cell">Type</th><th className="text-left font-medium px-2 py-2">Role</th><th className="text-left font-medium px-2 py-2 w-32">Fit</th>{deck.plan && <th className="text-right font-medium px-2 py-2">Play rate</th>}<th className="text-right font-medium px-3 py-2">Elo</th></tr>
              </thead>
              <tbody>
                {rows.map(({ c, m }) => (
                  <tr key={c.id} className="border-t border-slate-800/80 hover:bg-slate-900/60">
                    <td className="px-3 py-1.5"><button type="button" onClick={() => onPick(c.id)} {...bind(c)} className="flex items-center gap-2 text-left hover:text-amber-300"><Pips colors={c.colors} size={8} /><span>{c.name}</span></button></td>
                    <td className="px-2 py-1.5 hidden sm:table-cell"><ManaCost cost={c.mana_cost} size={14} /></td>
                    <td className="px-2 py-1.5 text-slate-400 hidden md:table-cell truncate max-w-[220px]">{c.type_line}</td>
                    <td className="px-2 py-1.5"><span className={`text-[11px] px-1.5 py-0.5 rounded border ${ROLE_BADGE[m.role][1]}`}>{ROLE_BADGE[m.role][0]}</span></td>
                    <td className="px-2 py-1.5"><span className="flex items-center gap-2"><span className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden"><span className="block h-full" style={{ width: `${m.fit * 100}%`, background: deckCol(deck.type) }} /></span><span className="text-[11px] text-slate-400 tabular-nums w-8 text-right">{Math.round(m.fit * 100)}%</span></span></td>
                    {deck.plan && <td className="px-2 py-1.5 text-right tabular-nums text-slate-300">{m.rate != null ? `${m.rate}%` : <span className="text-slate-600">–</span>}</td>}
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{c.elo}<span className="text-slate-600 text-[11px]"> #{c.rank}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {combos.length > 0 && (
          <div>
            <h3 className="font-display font-semibold mb-2">Combos in this deck type ({combos.length})</h3>
            <ComboList combos={combos.slice(0, 30)} data={data} bind={bind} onPick={onPick} />
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------- Combos

function ComboList({ combos, data, bind, onPick }) {
  return (
    <ul className="grid md:grid-cols-2 gap-2">
      {combos.map((r) => (
        <li key={r.i} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 space-y-2">
          <div className="flex gap-1.5">
            {r.pieces.map((p) => {
              const c = data.byId[p];
              return c && (
                <button key={p} type="button" onClick={() => onPick(p)} {...bind(c)} className="w-16 shrink-0" title={c.name}>
                  {c.art_crop || c.image ? <img src={c.art_crop || c.image} alt="" loading="lazy" className="w-16 h-12 object-cover rounded border border-slate-700" /> : <span className="block w-16 h-12 rounded border border-slate-700" />}
                </button>
              );
            })}
          </div>
          <div className="text-sm text-slate-200 leading-snug">
            {r.pieces.map((p, k) => <React.Fragment key={p}>{k > 0 && <span className="text-slate-500"> + </span>}<button type="button" onClick={() => onPick(p)} {...bind(data.byId[p])} className="hover:text-amber-300">{data.byId[p]?.name}</button></React.Fragment>)}
          </div>
          {r.produces.length > 0 && <p className="text-xs text-slate-400">{r.produces.join(" · ")}</p>}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <Pips colors={r.colors} size={9} />
            {r.decks.slice(0, 3).map((t) => <span key={t} className="px-1.5 py-0.5 rounded border border-slate-700" style={{ color: deckCol(t) }}>{deckName(t)}</span>)}
            {r.sid && <a href={`https://commanderspellbook.com/combo/${r.sid}/`} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 hover:text-amber-300">Spellbook <ExternalLink className="w-3 h-3" /></a>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function CombosView({ data, bind, onPick, onRebuild }) {
  const [q, setQ] = useState("");
  const [size, setSize] = useState("all");
  const [colour, setColour] = useState("");
  const [deck, setDeck] = useState("");
  const [sort, setSort] = useState("popular");
  const [limit, setLimit] = useState(60);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    let list = data.combos.filter((r) =>
      (size === "all" || (size === "4" ? r.pieces.length >= 4 : r.pieces.length === Number(size)))
      && (!colour || (colour === "C" ? !r.colors : [...colour].every((x) => r.colors.includes(x))))
      && (!deck || r.decks.includes(deck))
      && (!s || r.pieces.some((p) => data.byId[p]?.name.toLowerCase().includes(s)) || r.produces.some((x) => x.toLowerCase().includes(s))));
    if (sort === "pieces") list = [...list].sort((a, b) => a.pieces.length - b.pieces.length || b.weight - a.weight);
    if (sort === "elo") list = [...list].sort((a, b) => b.elo - a.elo);
    return list;
  }, [data, q, size, colour, deck, sort]);
  const counts = useMemo(() => {
    const n = { 2: 0, 3: 0, 4: 0 };
    data.combos.forEach((r) => { n[Math.min(4, r.pieces.length)] += 1; });
    return n;
  }, [data]);
  useEffect(() => setLimit(60), [q, size, colour, deck, sort]);

  return (
    <div className="space-y-4">
      {!data.combo_details && data.combos.length > 0 && (
        <p className="text-sm text-amber-200/90 bg-amber-400/10 border border-amber-400/30 rounded-lg px-3 py-2 flex flex-wrap items-center gap-2">
          This cube was loaded before combo results were saved, so what each combo does isn't shown yet.
          <button type="button" onClick={onRebuild} className="underline hover:text-amber-100">Rebuild it</button> to fetch them (about 20 seconds).
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative flex-1 min-w-[200px] max-w-sm">
          <span className="sr-only">Search combos</span>
          <Search className="w-4 h-4 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Card or result (infinite mana…)" className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-sm" data-testid="analysis-combo-search" />
        </label>
        <div className="inline-flex rounded-lg border border-slate-700 overflow-hidden text-sm">
          {[["all", `All ${data.combos.length}`], ["2", `2 cards (${counts[2]})`], ["3", `3 (${counts[3]})`], ["4", `4+ (${counts[4]})`]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setSize(k)} aria-pressed={size === k} className={`px-2.5 py-1.5 ${size === k ? "bg-amber-400 text-stone-900 font-semibold" : "text-slate-300 hover:bg-slate-800"}`} data-testid={`analysis-combo-size-${k}`}>{l}</button>
          ))}
        </div>
        <select value={colour} onChange={(e) => setColour(e.target.value)} aria-label="Color" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm" data-testid="analysis-combo-color">
          <option value="">Any color</option>
          {[["W", "White"], ["U", "Blue"], ["B", "Black"], ["R", "Red"], ["G", "Green"], ["C", "Colorless"]].map(([k, l]) => <option key={k} value={k}>Includes {l.toLowerCase()}</option>)}
        </select>
        <select value={deck} onChange={(e) => setDeck(e.target.value)} aria-label="Deck type" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm" data-testid="analysis-combo-deck">
          <option value="">Any deck type</option>
          {data.decks.filter((d) => d.combos.length).map((d) => <option key={d.type} value={d.type}>{deckName(d.type)} ({d.combos.length})</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort combos" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm" data-testid="analysis-combo-sort">
          <option value="popular">Most played</option><option value="pieces">Fewest pieces</option><option value="elo">Highest Elo</option>
        </select>
      </div>
      <p className="text-xs text-slate-500">Combos from Commander Spellbook whose pieces are all in this cube, plus a few cube staples it leaves out. "Most played" follows Spellbook's popularity.</p>
      {shown.length === 0 ? <p className="text-sm text-slate-400">No combos match.</p> : <ComboList combos={shown.slice(0, limit)} data={data} bind={bind} onPick={onPick} />}
      {shown.length > limit && <button type="button" onClick={() => setLimit((n) => n + 60)} className="px-3 py-1.5 rounded-lg border border-slate-700 text-sm hover:text-amber-300">Show more ({shown.length - limit} left)</button>}
    </div>
  );
}

// ---------------------------------------------------------------- Overview

function Bar({ value, max, colour }) {
  return <span className="block h-2 rounded bg-slate-800 overflow-hidden"><span className="block h-full rounded" style={{ width: `${max ? (100 * value) / max : 0}%`, background: colour }} /></span>;
}

function OverviewView({ data, bind, onPick }) {
  const o = data.overview;
  const colMax = Math.max(...COLUMNS.map(([k]) => o.columns[k] || 0));
  const curveCols = COLUMNS.filter(([k]) => k !== "L" && o.curve[k]);
  const curveMax = Math.max(1, ...curveCols.flatMap(([k]) => o.curve[k]));
  const viable = data.decks.filter((d) => d.label === "Strong" || d.label === "Viable");
  const roleRows = Object.entries(o.roles).filter(([, v]) => v.total > 0).sort((a, b) => b[1].total - a[1].total);
  const top = data.cards.slice().sort((a, b) => a.rank - b.rank).slice(0, 24);
  const fill = { W: MANA.W, U: MANA.U, B: MANA.B, R: MANA.R, G: MANA.G, C: "#94a3b8", M: "#e0b23a", L: "#a08262" };

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[["Cards", o.total], ["Lands", `${o.lands.total} (${o.lands.fixing} fixing)`], ["Combos", data.combos.length],
          ["Viable deck types", viable.length], ["Avg Elo", Math.round(data.cards.reduce((s, c) => s + c.elo, 0) / Math.max(1, data.cards.length))],
          ["With CubeCobra links", `${Math.round((100 * data.meta.with_partners) / Math.max(1, o.total))}%`]].map(([k, v]) => (
          <div key={k} className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3"><dt className="text-[11px] uppercase tracking-wide text-slate-500">{k}</dt><dd className="text-xl font-semibold tabular-nums mt-0.5">{v}</dd></div>
        ))}
      </dl>

      <div className="grid lg:grid-cols-2 gap-6">
        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="font-display font-semibold mb-3">Colors</h3>
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-slate-500"><tr><th className="text-left font-medium pb-1">Column</th><th className="text-right font-medium pb-1 w-12">Cards</th><th className="pb-1" /><th className="text-right font-medium pb-1 w-16">Avg Elo</th></tr></thead>
            <tbody>
              {COLUMNS.map(([k, l]) => (
                <tr key={k}><td className="py-1">{l}</td><td className="text-right tabular-nums">{o.columns[k] || 0}</td><td className="px-3 w-1/2"><Bar value={o.columns[k] || 0} max={colMax} colour={fill[k]} /></td><td className="text-right tabular-nums text-slate-400">{o.avg_elo[k] || "–"}</td></tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="font-display font-semibold mb-3">Mana curve (non-land)</h3>
          <div className="space-y-1.5">
            {curveCols.map(([k, l]) => (
              <div key={k} className="flex items-end gap-2">
                <span className="w-24 text-xs text-slate-400 shrink-0">{l}</span>
                <div className="flex-1 grid grid-cols-8 gap-1 items-end h-10">
                  {o.curve[k].map((n, i) => <span key={i} title={`${l}, ${i === 7 ? "7+" : i} mana: ${n}`} className="rounded-sm" style={{ height: `${Math.max(2, (100 * n) / curveMax)}%`, background: fill[k] }} />)}
                </div>
              </div>
            ))}
            <div className="flex gap-2"><span className="w-24 shrink-0" /><div className="flex-1 grid grid-cols-8 gap-1 text-[10px] text-slate-500 text-center">{["0", "1", "2", "3", "4", "5", "6", "7+"].map((x) => <span key={x}>{x}</span>)}</div></div>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="font-display font-semibold mb-1">Color pairs</h3>
          <p className="text-xs text-slate-500 mb-3">What a two-color deck could play: its colors' cards and colorless ones. Best-23 Elo is the average Elo of its 23 strongest non-land cards.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-slate-500"><tr><th className="text-left font-medium pb-1">Pair</th><th className="text-right font-medium pb-1">Playable</th><th className="text-right font-medium pb-1">Gold</th><th className="text-right font-medium pb-1">Fixing</th><th className="text-right font-medium pb-1">Best-23 Elo</th></tr></thead>
              <tbody>
                {o.pairs.map((p) => (
                  <tr key={p.pair} className="border-t border-slate-800/70"><td className="py-1"><span className="flex items-center gap-2"><Pips colors={p.pair} size={10} />{p.name}</span></td><td className="text-right tabular-nums">{p.playable}</td><td className="text-right tabular-nums">{p.gold}</td><td className="text-right tabular-nums">{p.fixing}</td><td className="text-right tabular-nums">{p.top_elo}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="font-display font-semibold mb-3">Interaction and engines</h3>
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wide text-slate-500"><tr><th className="text-left font-medium pb-1">Kind</th><th className="text-right font-medium pb-1 w-12">Cards</th><th className="text-left font-medium pb-1 pl-3">By color</th></tr></thead>
            <tbody>
              {roleRows.map(([r, v]) => (
                <tr key={r} className="border-t border-slate-800/70">
                  <td className="py-1">{data.roles[r]}</td><td className="text-right tabular-nums">{v.total}</td>
                  <td className="pl-3"><span className="flex flex-wrap gap-x-2 text-[11px] text-slate-400 tabular-nums">{Object.entries(v.by).sort((a, b) => b[1] - a[1]).map(([k, n]) => <span key={k} className="flex items-center gap-1">{k === "" ? <Pips colors="" size={8} /> : k === "M" ? <span className="w-2 h-2 rounded-full" style={{ background: fill.M }} /> : <Pips colors={k} size={8} />}{n}</span>)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section>
        <h3 className="font-display font-semibold mb-2">Deck types at a glance</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {data.decks.filter((d) => d.keys > 0).map((d) => (
            <div key={d.type} className="rounded-lg border border-slate-800 bg-slate-900/40 px-3 py-2">
              <div className="flex items-center justify-between gap-2"><span className="font-medium truncate" style={{ color: deckCol(d.type) }}>{deckName(d.type)}</span><span className={`text-[11px] px-1.5 py-0.5 rounded border ${LABEL_STYLE[d.label]}`}>{d.label}</span></div>
              <div className="mt-1.5"><Bar value={d.score} max={100} colour={deckCol(d.type)} /></div>
              <div className="mt-1 text-[11px] text-slate-500 tabular-nums">{d.keys} key · {d.depth} deep · {d.combos.length} combos</div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="font-display font-semibold mb-2">Highest rated cards</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-4">
          {top.map((c) => (
            <button key={c.id} type="button" onClick={() => onPick(c.id)} {...bind(c)} className="flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-slate-800/70 text-left text-sm">
              <span className="flex items-center gap-2 min-w-0"><span className="text-[11px] text-slate-600 tabular-nums w-5">{c.rank}</span><Pips colors={c.colors} size={8} /><span className="truncate">{c.name}</span></span>
              <span className="text-[11px] tabular-nums text-slate-500">{c.elo}</span>
            </button>
          ))}
        </div>
      </section>
      <p className="text-xs text-slate-500">CubeCobra deck data from the export of {data.meta.export ? new Date(data.meta.export).toLocaleDateString() : "–"}. Elo and links are CubeCobra's for each card.</p>
    </div>
  );
}

// ---------------------------------------------------------------- page

const TABS = [["list", "List", LayoutGrid], ["decks", "Deck types", Layers], ["combos", "Combos", Zap], ["overview", "Overview", BarChart3]];

export default function CubeAnalysis() {
  const { user } = useAuth() || {};
  const saved = load(STORE, {});
  const [cubeId, setCubeId] = useState(saved.cubeId || GROUP_CUBE);
  const [tab, setTab] = useState(saved.tab || "decks");
  const [data, setData] = useState(null);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [pools, setPools] = useState([]);
  const [myCubes, setMyCubes] = useState([]);
  const [pick, setPick] = useState(null);
  const [hover, bind, setHover] = useHover();
  const cardsRef = React.useRef(null);

  useEffect(() => { api.get("/lab/pools").then(({ data: d }) => setPools((d.pools || []).filter((p) => !p.vrd))).catch(() => {}); }, []);
  useEffect(() => { if (user) api.get("/cubes").then(({ data: d }) => setMyCubes(d.cubes || [])).catch(() => {}); }, [user]);
  useEffect(() => { save(STORE, { ...load(STORE, {}), tab }); }, [tab]);

  const analyse = useCallback(async (body, label) => {
    setStep("Reading CubeCobra links and combos for this cube… the first time can take 20 seconds");
    const src = (await api.post("/lab/source", body, { timeout: 120000 })).data;
    setStep("Breaking the cube down…");
    const { data: a } = await api.post("/lab/analysis", { source: src.source }, { timeout: 60000 });
    const byId = Object.fromEntries(a.cards.map((c) => [c.id, c]));
    const comboByI = Object.fromEntries(a.combos.map((r) => [r.i, r]));
    setData({ ...a, byId, comboByI, label: label || a.label });
  }, []);

  const run = useCallback(async ({ id = cubeId, pool = null, mine = null, refresh = false } = {}) => {
    setError(""); setPick(null); setHover(null);
    try {
      if (pool) {
        const meta = pools.find((p) => p.key === pool);
        cardsRef.current = null;
        await analyse({ pool }, meta?.label);
        if (meta?.label) setCubeId(meta.label);
        save(STORE, { ...load(STORE, {}), cubeId: meta?.label || cubeId });
        return;
      }
      if (mine) {
        setStep("Loading your saved cube…");
        const { data: c } = await api.get(`/cubes/${mine}`);
        cardsRef.current = { cards: c.cards, label: c.name };
      } else if (refresh && cardsRef.current) {
        // rebuild what's loaded
      } else {
        const res = await resolveCube({ cubeCobra: id, onStep: setStep });
        cardsRef.current = { cards: res.cards, label: id.trim() };
        save(STORE, { ...load(STORE, {}), cubeId: id.trim() });
      }
      await analyse({ cards: cardsRef.current.cards, label: cardsRef.current.label, refresh }, cardsRef.current.label);
      api.get("/lab/pools").then(({ data: d }) => setPools((d.pools || []).filter((p) => !p.vrd))).catch(() => {});
    } catch (e) {
      setError(e.message && !e.response ? e.message : stepError("Couldn't analyze the cube", e));
    } finally { setStep(""); }
  }, [cubeId, pools, analyse, setHover]);

  const rebuild = useCallback(() => {
    if (cardsRef.current) return run({ refresh: true });
    return (async () => {
      setError("");
      try {
        const res = await resolveCube({ cubeCobra: data?.label || cubeId, onStep: setStep });
        cardsRef.current = { cards: res.cards, label: (data?.label || cubeId).trim() };
        await analyse({ cards: res.cards, label: cardsRef.current.label, refresh: true }, cardsRef.current.label);
      } catch (e) { setError(e.message && !e.response ? e.message : stepError("Couldn't rebuild the cube", e)); } finally { setStep(""); }
    })();
  }, [run, analyse, data, cubeId]);

  useEffect(() => {
    // Open the last cube: a saved pool loads in a second or two.
    api.get("/lab/pools").then(({ data: d }) => {
      const list = (d.pools || []).filter((p) => !p.vrd);
      setPools(list);
      const meta = list.find((p) => p.label === (saved.cubeId || GROUP_CUBE));
      if (meta) {
        setError("");
        analyse({ pool: meta.key }, meta.label).catch((e) => setError(stepError("Couldn't open the cube", e))).finally(() => setStep(""));
      }
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onPick = useCallback((id) => { setHover(null); setPick(id); }, [setHover]);
  const presetName = (label) => PRESETS.find(([, v]) => v === label)?.[0] || label;

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100">
      <header className="border-b border-slate-800">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <nav className="flex items-center gap-4 text-sm"><Link to="/draft" className="text-slate-400 hover:text-white">Cube Draft</Link><Link to="/bots" className="text-slate-400 hover:text-white">Bot Brain</Link><Link to="/dashboard" className="text-slate-400 hover:text-white">My Decks</Link></nav>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold flex items-center gap-2"><BarChart3 className="w-7 h-7 text-amber-400" /> Cube Analysis</h1>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">The whole cube at a glance: every card, the decks it can draft, how viable each one is, and its combos.</p>
          </div>
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); run({ id: cubeId }); }} data-testid="analysis-source">
            {pools.length > 0 && (
              <select value="" onChange={(e) => e.target.value && run({ pool: e.target.value })} aria-label="Cubes loaded before" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm max-w-[220px]" data-testid="analysis-pool">
                <option value="">Loaded before…</option>
                {pools.map((p) => <option key={p.key} value={p.key}>{presetName(p.label)} · {p.cards} cards</option>)}
              </select>
            )}
            {myCubes.length > 0 && (
              <select value="" onChange={(e) => e.target.value && run({ mine: e.target.value })} aria-label="My saved cubes" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm max-w-[200px]" data-testid="analysis-my-cube">
                <option value="">My cubes…</option>
                {myCubes.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.card_count}</option>)}
              </select>
            )}
            <select value={PRESETS.some(([, v]) => v === cubeId) ? cubeId : ""} onChange={(e) => { if (e.target.value) { setCubeId(e.target.value); run({ id: e.target.value }); } }} aria-label="Cube" className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm" data-testid="analysis-preset">
              {PRESETS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
              <option value="">Other CubeCobra cube…</option>
            </select>
            <label htmlFor="analysis-cube" className="sr-only">CubeCobra cube ID or link (join several with +)</label>
            <input id="analysis-cube" value={cubeId} onChange={(e) => setCubeId(e.target.value)} placeholder="CubeCobra ID, link, or A + B" className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm w-56" data-testid="analysis-cube-input" />
            <button type="submit" disabled={!!step} className="px-3 py-1.5 rounded-lg bg-amber-400 text-stone-900 font-semibold text-sm flex items-center gap-1.5 disabled:opacity-60" data-testid="analysis-load"><Library className="w-4 h-4" /> Analyze</button>
            {data && <button type="button" onClick={rebuild} disabled={!!step} title="Fetch CubeCobra links and combos again" className="px-2.5 py-1.5 rounded-lg border border-slate-700 text-sm text-slate-300 hover:text-amber-300 disabled:opacity-60" data-testid="analysis-rebuild"><RefreshCw className="w-4 h-4" /><span className="sr-only">Rebuild</span></button>}
          </form>
        </div>

        {error && <p className="text-sm text-red-300" role="alert">{error}</p>}
        {step && <p className="text-sm text-slate-400 flex items-center gap-2" role="status"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> {step}</p>}

        {data && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800">
              <div className="flex gap-1 overflow-x-auto" role="tablist">
                {TABS.map(([k, l, Icon]) => (
                  <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                    className={`px-3 py-2 text-sm flex items-center gap-1.5 border-b-2 -mb-px whitespace-nowrap ${tab === k ? "border-amber-400 text-amber-300" : "border-transparent text-slate-400 hover:text-white"}`} data-testid={`analysis-tab-${k}`}>
                    <Icon className="w-4 h-4" /> {l}
                    {k === "combos" && <span className="text-[11px] text-slate-500">{data.combos.length}</span>}
                  </button>
                ))}
              </div>
              <span className="text-sm text-slate-400 pb-2">{presetName(data.label)} · {data.cards.length} cards{data.partial ? " · CubeCobra links still loading (rebuild later)" : ""}</span>
            </div>
            {tab === "list" && <ListView data={data} bind={bind} onPick={onPick} />}
            {tab === "decks" && <DecksView data={data} bind={bind} onPick={onPick} />}
            {tab === "combos" && <CombosView data={data} bind={bind} onPick={onPick} onRebuild={rebuild} />}
            {tab === "overview" && <OverviewView data={data} bind={bind} onPick={onPick} />}
          </>
        )}
      </main>
      <HoverPreview hover={hover} />
      {data && pick && <CardPanel card={data.byId[pick]} data={data} onClose={() => setPick(null)} onPick={onPick} />}
    </div>
  );
}
