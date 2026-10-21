import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { resolveCube, stepError } from "@/lib/cube";
import BotLab from "@/components/BotLab";
import { Sparkles, Loader2, Brain, Search, Shuffle, Dices, Play, Network, Library, RefreshCw, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Undo2, GitCompare } from "lucide-react";

// Bot Brain: how the draft bots think, outside any draft. Load a cube (CubeCobra) or the VRD pool, then
// look up any card (what the bots know about it and what it links to) or run an all-bot draft and step
// through its picks in the Bot Lab view. A built pool is saved on the server (one document) and listed under
// "Saved pools", so loading it again skips CubeCobra, Scryfall and the stats lookups. Draft runs are never
// saved: rewind to any pick, change weights and re-draft from there to see what changes.

const DECK_NAMES = { tolarian: "Tolarian", workshop: "Workshop", artifacts: "Artifacts", storm: "Storm", reanimator: "Reanimator", cheat: "Cheat", lands: "Lands", aggro: "Aggro" };
const DECK_COL = { tolarian: "#38bdf8", workshop: "#a8a29e", artifacts: "#f59e0b", storm: "#e879f9", reanimator: "#8b5cf6", cheat: "#f43f5e", lands: "#84cc16", aggro: "#fb923c" };
const MANA = { W: "#f2e8c9", U: "#3b82f6", B: "#a855f7", R: "#ef4444", G: "#22c55e" };
const COL_NAME = { W: "white", U: "blue", B: "black", R: "red", G: "green" };
const STORE = "grim_brain";
const GROUP_CUBE = "43fd5f2a-942e-40c3-a563-bf3a7ce0cc22";
const PRESETS = [   // [label, CubeCobra ids]
  ["Group cube", GROUP_CUBE],
  ["Group cube + PowerLSV", `${GROUP_CUBE} + PowerLSV`],
  ["PowerLSV", "PowerLSV"],
];
const TUNING_STORE = "grim_botlab_tuning";

function colourOf(c) {
  if (c.land) return "#a08262";
  if (!c.colors) return "#94a3b8";
  return c.colors.length > 1 ? "#e0b23a" : MANA[c.colors];
}
function load(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function save(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* blocked */ } }

function botRead(d) {
  if (d.staple) return "Taken on sight: the bots rate it with the pool's very top picks, whatever its Elo.";
  if (d.key_of.length) return `A key card: owning it puts a bot into ${d.key_of.map((t) => DECK_NAMES[t]).join(" and ")}. Bots not in that deck type count it at 55%, unless the deck type is still open early in the draft.`;
  if (d.universal) return "Universal: goes in nearly every deck, so owning it tells the bots nothing about which deck they're building.";
  if (d.narrow) return "Narrow: it only pays off in some decks, so a bot values it at 40% until it's in a deck that uses it.";
  if (d.home) return "Colourless, with a home: it counts most in the colours its partners are drafted in.";
  return "A normal card: the bots judge it by rating, colours, combos and the cards they already own.";
}

// ---------------------------------------------------------------- the card's link graph

function EgoGraph({ graph, centre, onPick }) {
  const W = 760, H = 420;
  // Rings: synergistic partners close in, "drafted with" ones further out. A short force pass moves cards
  // along their ring so linked ones end up near each other, without piling up on an edge.
  const layout = useMemo(() => {
    const c0 = graph.nodes[0].id;
    const synIds = new Set(graph.edges.filter(([a, b, s]) => s >= 1 && (a === c0 || b === c0)).map(([a, b]) => (a === c0 ? b : a)));
    const nodes = graph.nodes.map((n, i) => ({ ...n, i, inner: synIds.has(n.id) }));
    const at = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
    const edges = graph.edges.filter(([a, b]) => at[a] != null && at[b] != null).map(([a, b, s]) => [at[a], at[b], s]);
    const spread = (list, offset) => list.forEach((n, k) => { n.t = offset + (k / Math.max(list.length, 1)) * Math.PI * 2; });
    const inner = nodes.filter((n) => n.i && n.inner), outer = nodes.filter((n) => n.i && !n.inner);
    spread(inner, -Math.PI / 2);
    // Outer cards sit next to the inner cards they're linked to (circular mean of those angles), spread evenly.
    outer.forEach((n) => {
      let sx = 0, sy = 0;
      edges.forEach(([a, b]) => { const o = a === n.i ? nodes[b] : b === n.i ? nodes[a] : null; if (o && o.i && o.inner) { sx += Math.cos(o.t); sy += Math.sin(o.t); } });
      n.want = sx || sy ? Math.atan2(sy, sx) : 0;
    });
    outer.sort((a, b) => a.want - b.want);
    spread(outer, outer.length ? outer[0].want : 0);
    const R = { inner: [140, 105], outer: [265, 175] };
    nodes.forEach((n) => {
      if (!n.i) { n.x = W / 2; n.y = H / 2; return; }
      const [rx, ry] = n.inner ? R.inner : R.outer;
      n.x = W / 2 + Math.cos(n.t) * rx; n.y = H / 2 + Math.sin(n.t) * ry;
    });
    return { nodes, edges };
  }, [graph]);
  const [hover, setHover] = useState(null);
  const hot = (i) => hover == null || i === hover || layout.edges.some(([a, b]) => (a === hover && b === i) || (b === hover && a === i));
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[520px] h-auto block" role="img" aria-label={`Link graph of ${centre} and its closest partners`}>
        <ellipse cx={W / 2} cy={H / 2} rx={140} ry={105} fill="none" stroke="#1e293b" strokeDasharray="3 5" />
        <ellipse cx={W / 2} cy={H / 2} rx={265} ry={175} fill="none" stroke="#1e293b" strokeDasharray="3 5" />
        {layout.edges.map(([a, b, s], k) => {
          const lit = hover != null && (a === hover || b === hover);
          const spoke = a === 0 || b === 0;
          return <line key={k} x1={layout.nodes[a].x} y1={layout.nodes[a].y} x2={layout.nodes[b].x} y2={layout.nodes[b].y}
            stroke={spoke || lit ? "#fbbf24" : "#64748b"} strokeOpacity={lit ? 0.9 : spoke ? (s >= 1 ? 0.55 : 0.18) : (hover == null ? (s >= 1 ? 0.22 : 0.07) : 0.03)} strokeWidth={s >= 1 ? 1.4 : 0.8} />;
        })}
        {layout.nodes.map((n, i) => {
          const left = i && n.x < W / 2 - 4;
          return (
            <g key={n.id} transform={`translate(${n.x},${n.y})`} className="cursor-pointer" opacity={hot(i) ? 1 : 0.3}
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => i && onPick(n.id)}>
              <circle r={i === 0 ? 9 : 6} fill={colourOf(n)} stroke={i === 0 ? "#fbbf24" : "#020617"} strokeWidth={i === 0 ? 2.5 : 1} />
              <text x={i === 0 ? 0 : left ? -9 : 9} y={i === 0 ? -15 : 4} textAnchor={i === 0 ? "middle" : left ? "end" : "start"} fontSize={i === 0 ? 14 : 11}
                fill={i === 0 ? "#fbbf24" : "#e2e8f0"} style={{ paintOrder: "stroke", stroke: "#020617", strokeWidth: 3 }}>
                {n.name.split(" // ")[0].slice(0, 20)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CardLink({ c, onPick, right }) {
  return (
    <button type="button" onClick={() => onPick(c.id)} className="w-full flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-slate-800/70 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400">
      <span className="flex items-center gap-2 min-w-0 text-sm text-slate-200"><span className="w-2 h-2 rounded-full shrink-0" style={{ background: colourOf(c) }} /><span className="truncate">{c.name}</span></span>
      <span className="text-[11px] tabular-nums text-slate-500 shrink-0">{right ?? c.elo}</span>
    </button>
  );
}

function Dossier({ d, card, onPick }) {
  const syn = d.partners.filter((p) => p.s >= 1), dw = d.partners.filter((p) => p.s < 1);
  const [allDw, setAllDw] = useState(false);
  useEffect(() => { setAllDw(false); }, [d.id]);
  const img = card && (card.image || card.art_crop);
  return (
    <div className="space-y-5" data-testid="brain-dossier">
      <div className="flex gap-4">
        {img && <img src={img} alt={d.name} className="w-32 sm:w-40 rounded-lg border border-slate-700 self-start shrink-0" />}
        <div className="min-w-0 space-y-2">
          <h2 className="font-display text-2xl font-bold leading-tight">{d.name}</h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-400">
            <span className="flex gap-0.5">{d.colors ? [...d.colors].map((c) => <span key={c} className="w-3 h-3 rounded-full border border-white/20" style={{ background: MANA[c] }} title={COL_NAME[c]} />) : <span className="w-3 h-3 rounded-full" style={{ background: colourOf(d) }} />}</span>
            <span className="tabular-nums">Elo {d.elo}</span>
            <span className="tabular-nums">{d.partner_count.synergy} synergy · {d.partner_count.all} total links</span>
            {d.combo_count > 0 && <span>{d.combo_count} combo{d.combo_count === 1 ? "" : "s"}</span>}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[["Key card", d.key_of.length > 0], ["Narrow", d.narrow], ["Universal", d.universal], ["Take on sight", d.staple]].map(([l, on]) => (
              <span key={l} className={`text-xs px-2 py-0.5 rounded-full border ${on ? "border-amber-400/70 text-amber-300" : "border-slate-700 text-slate-500"}`}>{l}</span>
            ))}
          </div>
          <p className="text-sm text-slate-300 max-w-prose">{botRead(d)}</p>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <section className="space-y-2">
          <h3 className="text-[11px] uppercase tracking-wider text-slate-500">Deck-type membership</h3>
          {Object.keys(d.deck).length ? Object.entries(d.deck).map(([t, v]) => (
            <div key={t} className="grid grid-cols-[90px_1fr_40px] items-center gap-2 text-sm">
              <span className="text-slate-300">{DECK_NAMES[t] || t}</span>
              <span className="relative h-2 rounded bg-slate-800 overflow-hidden"><span className="absolute inset-y-0 left-0 rounded" style={{ width: `${v * 100}%`, background: DECK_COL[t] }} /><span className="absolute -inset-y-0.5 left-1/2 w-px bg-slate-500" title="A bot counts a card as in from 50%" /></span>
              <span className="text-xs tabular-nums text-slate-400 text-right">{Math.round(v * 100)}%</span>
            </div>
          )) : <p className="text-sm text-slate-500">In no deck type: none of its partners are key cards.</p>}
          {d.home && <>
            <h3 className="text-[11px] uppercase tracking-wider text-slate-500 pt-2">Home colours</h3>
            {Object.entries(d.home).sort((a, b) => b[1] - a[1]).map(([c, v]) => (
              <div key={c} className="grid grid-cols-[90px_1fr_40px] items-center gap-2 text-sm">
                <span className="text-slate-300 capitalize">{COL_NAME[c]}</span>
                <span className="relative h-2 rounded bg-slate-800 overflow-hidden"><span className="absolute inset-y-0 left-0 rounded" style={{ width: `${v * 100}%`, background: MANA[c] }} /></span>
                <span className="text-xs tabular-nums text-slate-400 text-right">{Math.round(v * 100)}%</span>
              </div>
            ))}
          </>}
        </section>
        <section className="space-y-2">
          <h3 className="text-[11px] uppercase tracking-wider text-slate-500">Roles the bots read</h3>
          <div className="flex flex-wrap gap-1.5">{d.roles.length ? d.roles.map((r) => <span key={r} className="text-xs font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-200">{r}</span>) : <span className="text-sm text-slate-500">None</span>}</div>
          {d.combos.length > 0 && <>
            <h3 className="text-[11px] uppercase tracking-wider text-slate-500 pt-2">Combos</h3>
            <ul className="space-y-1">{d.combos.slice(0, 8).map((cb, i) => (
              <li key={i} className={`text-sm flex flex-wrap items-center gap-x-1.5 ${cb.counted ? "text-slate-200" : "text-slate-500"}`} title={cb.counted ? `Spellbook weight ${cb.weight}` : "Four or more pieces: the bots ignore lines this long"}>
                {cb.pieces.map((p, k) => <React.Fragment key={p.id}>{k > 0 && <span className="text-slate-600">+</span>}<button type="button" onClick={() => onPick(p.id)} className="hover:text-amber-300 underline decoration-dotted decoration-slate-600 underline-offset-2">{p.name.split(" // ")[0]}</button></React.Fragment>)}
              </li>
            ))}</ul>
          </>}
        </section>
      </div>

      {d.graph.nodes.length > 1 && (
        <section className="space-y-2">
          <h3 className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5"><Network className="w-3.5 h-3.5" /> Closest partners and how they link to each other</h3>
          <EgoGraph graph={d.graph} centre={d.name} onPick={onPick} />
          <p className="text-xs text-slate-500">Inner ring: "synergistic" partners (count fully for the bots). Outer ring: strongest "often drafted with" partners (count half). Grey lines link partners to each other. Hover a card to see its links; tap one to open it.</p>
        </section>
      )}

      <div className="grid md:grid-cols-2 gap-5">
        <section><h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Synergistic with ({syn.length})</h3>
          {syn.length ? syn.map((p) => <CardLink key={p.id} c={p} onPick={onPick} />) : <p className="text-sm text-slate-500">None listed on CubeCobra for this pool.</p>}</section>
        <section><h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Often drafted with ({d.partner_count.all - d.partner_count.synergy})</h3>
          {(allDw ? dw : dw.slice(0, 15)).map((p) => <CardLink key={p.id} c={p} onPick={onPick} />)}
          {dw.length > 15 && <button type="button" onClick={() => setAllDw((v) => !v)} className="text-xs text-amber-300 hover:underline px-2 mt-1">{allDw ? "Show fewer" : `Show all ${dw.length}`}</button>}
          {d.partner_count.all > d.partners.length && allDw && <p className="text-xs text-slate-500 px-2 mt-1">Strongest {d.partners.length} shown.</p>}</section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- simulated draft: board and seat summaries

const shortName = (n) => (n || "?").split(" // ")[0];
// Where table pick `slot` sits for a seat: its Nth pick (1-based).
function slotFocus(order, slot) {
  const seat = order[slot];
  let n = 0;
  for (let i = 0; i <= slot; i += 1) if (order[i] === seat) n += 1;
  return { seat, pickNo: n };
}

function DraftBoard({ sim, byId, seats, viewSlot, changed, kept, onPick }) {
  const n = seats.length;
  const rounds = Math.ceil(sim.picks.length / n);
  const bySlot = sim.picks;
  const cell = (r, s) => r * n + (r % 2 === 0 ? s : n - 1 - s);
  const viewRef = useRef(null);
  useEffect(() => { viewRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [viewSlot]);
  return (
    <div className="overflow-auto max-h-[46vh] rounded-lg border border-slate-800 bg-slate-950" data-testid="brain-board">
      <table className="text-[11px] border-separate border-spacing-0 w-full">
        <thead className="sticky top-0 z-10 bg-slate-950">
          <tr><th className="px-1.5 py-1 text-slate-500 font-normal text-right w-7">#</th>
            {seats.map((s) => <th key={s.index} className="px-1.5 py-1 text-slate-300 font-semibold text-left min-w-[104px]">{s.player_name}</th>)}</tr>
        </thead>
        <tbody>
          {Array.from({ length: rounds }, (_, r) => (
            <tr key={r}>
              <td className="px-1.5 text-right text-slate-600 tabular-nums">{r + 1}</td>
              {seats.map((s, si) => {
                const slot = cell(r, si);
                const p = bySlot[slot];
                if (!p) return <td key={s.index} />;
                const c = byId[p.card_id];
                const here = slot === viewSlot;
                const ch = changed.has(slot);
                return (
                  <td key={s.index} className="p-0.5" ref={here ? viewRef : undefined}>
                    <button type="button" onClick={() => onPick(slot)} title={`Table pick ${slot + 1}: ${c?.name || "?"}${ch ? " (changed by the re-draft)" : ""}`}
                      data-testid={`brain-board-${slot}`}
                      className={`w-full text-left flex items-center gap-1 rounded px-1 py-0.5 border ${here ? "border-amber-400 bg-amber-400/15 text-amber-100" : ch ? "border-sky-400/70 bg-sky-400/10 text-slate-100" : "border-transparent hover:bg-slate-800/70 text-slate-300"} ${slot < kept ? "opacity-60" : ""}`}>
                      <span className="w-1.5 h-3 rounded-sm shrink-0" style={{ background: c ? colourOf(c) : "#334155" }} />
                      <span className="truncate max-w-[118px]">{shortName(c?.name)}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeatPips({ pair }) {
  return pair ? <span className="inline-flex gap-0.5">{[...pair].map((c) => <span key={c} className="w-2.5 h-2.5 rounded-full border border-white/20" style={{ background: MANA[c] }} title={COL_NAME[c]} />)}</span>
    : <span className="text-slate-500">open</span>;
}

function SeatSummary({ s, before, name, tuned }) {
  const decks = Object.entries(s.decks || {});
  const deckText = (d) => Object.keys(d || {}).slice(0, 2).map((t) => DECK_NAMES[t] || t).join(", ") || "no deck type";
  const moved = before && (before.pair !== s.pair || deckText(before.decks) !== deckText(s.decks));
  const delta = before ? s.avg_elo - before.avg_elo : 0;
  return (
    <div className={`rounded-lg border p-3 space-y-1.5 ${moved ? "border-sky-400/60 bg-sky-400/5" : "border-slate-800 bg-slate-900/40"}`}>
      <div className="flex items-center justify-between gap-2 text-sm font-semibold">
        <span className="flex items-center gap-2">{name}{tuned && <span className="text-[10px] font-normal px-1.5 rounded-full border border-amber-400/60 text-amber-300">new weights</span>}</span>
        <SeatPips pair={s.pair} />
      </div>
      <div className="text-xs text-slate-400 flex flex-wrap gap-x-3 gap-y-0.5 tabular-nums">
        <span>{s.on_colour}% on colour</span>
        <span>Elo {s.avg_elo}{before && delta !== 0 && <span className={delta > 0 ? "text-emerald-400" : "text-rose-400"}> {delta > 0 ? "+" : ""}{delta}</span>}</span>
        <span>{s.creatures} creatures</span>
      </div>
      <div className="text-xs text-slate-300">{decks.length ? decks.slice(0, 3).map(([t, v]) => `${DECK_NAMES[t] || t} ${Math.round(v * 100)}%`).join(" · ") : <span className="text-slate-500">No deck type</span>}</div>
      {s.combos.length > 0 && <div className="text-xs text-fuchsia-300">{s.combos.map((cb) => cb.map(shortName).join(" + ")).join("; ")}</div>}
      {moved && <div className="text-xs text-sky-300">Was {before.pair ? <SeatPips pair={before.pair} /> : "open"} · {deckText(before.decks)}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- page

export default function BotBrain() {
  const saved = load(STORE, {});
  const [mode, setMode] = useState(saved.mode || "cube");
  const [cubeId, setCubeId] = useState(saved.cubeId || PRESETS[1][1]);
  const [src, setSrc] = useState(null);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState("cards");
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(null);
  const [dossier, setDossier] = useState(null);
  const [dLoading, setDLoading] = useState(false);
  const [sim, setSim] = useState(null);
  const [prev, setPrev] = useState(null);          // the run before a re-draft, to show what changed
  const [simCfg, setSimCfg] = useState({ seats: 8, picks: 45, seed: Math.floor(Math.random() * 10000) });
  const [simming, setSimming] = useState(false);
  const [runs, setRuns] = useState(0);
  const [viewSlot, setViewSlot] = useState(0);
  const [focus, setFocus] = useState(null);
  const [labTuning, setLabTuning] = useState({});  // weights changed in the Lab panel
  const [tunedSeats, setTunedSeats] = useState(null); // null = new weights for every bot
  const [pools, setPools] = useState([]);
  const cubeCards = useRef(null);          // the resolved cube, to send again if the server forgot the pool

  const refreshPools = useCallback(() => api.get("/lab/pools").then(({ data }) => setPools(data.pools || [])).catch(() => {}), []);

  // Load a pool: a saved one by key (one read on the server), or build it (CubeCobra cube or VRD).
  const loadSource = useCallback(async ({ m = mode, id = cubeId, pool = null, refresh = false } = {}) => {
    setError(""); setSrc(null); setDossier(null); setSel(null); setSim(null); setPrev(null);
    try {
      let data = null;
      const saved = pool || (!refresh && pools.find((p) => (m === "vrd" ? p.vrd : !p.vrd && p.label === id.trim()))?.key);
      if (saved) {
        setStep("Loading the saved pool…");
        try { data = (await api.post("/lab/source", { pool: saved }, { timeout: 60000 })).data; }
        catch (e) { if (e.response?.status !== 404) throw e; }
      }
      if (!data) {
        let body;
        if (m === "vrd") { setStep("Building the VRD pool (every Vintage-legal card)…"); body = { vrd: true, refresh }; }
        else {
          const res = await resolveCube({ cubeCobra: id, onStep: setStep });
          cubeCards.current = res.cards;
          setStep("Reading CubeCobra links and combos for this cube… the first time can take 20 seconds");
          body = { cards: res.cards, label: id.trim(), refresh };
        }
        data = (await api.post("/lab/source", body, { timeout: 120000 })).data;
        refreshPools();
      }
      const isVrd = !!data.vrd;
      setMode(isVrd ? "vrd" : "cube");
      if (!isVrd && data.label) setCubeId(data.label);
      save(STORE, { mode: isVrd ? "vrd" : "cube", cubeId: isVrd ? id : data.label || id, pool: data.source });
      setSrc(data);
      const first = data.summary.connected[0]?.id || data.cards[0]?.id;
      if (first) setSel(first);
    } catch (e) {
      setError(e.message && !e.response ? e.message : stepError(m === "vrd" ? "Couldn't load the VRD pool" : "Couldn't load the cube", e));
    } finally { setStep(""); }
  }, [mode, cubeId, pools, refreshPools]);

  useEffect(() => {
    refreshPools();
    loadSource(saved.pool ? { pool: saved.pool } : {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Calls that need the pool on the server: if it was forgotten (restart), load it again once (the saved
  // copy first, which is one read, then the cards this page resolved).
  const withSource = useCallback(async (fn) => {
    try { return await fn(src.source); } catch (e) {
      if (e.response?.status !== 410) throw e;
      let data;
      try { data = (await api.post("/lab/source", { pool: src.source }, { timeout: 60000 })).data; }
      catch (e2) {
        if (e2.response?.status !== 404) throw e2;
        data = (await api.post("/lab/source", mode === "vrd" ? { vrd: true } : { cards: cubeCards.current || [], label: cubeId }, { timeout: 120000 })).data;
      }
      setSrc(data);
      return fn(data.source);
    }
  }, [src, mode, cubeId]);

  useEffect(() => {
    if (!src || !sel) return;
    let alive = true;
    setDLoading(true);
    withSource((source) => api.post("/lab/card", { source, card: sel }))
      .then(({ data }) => { if (alive) setDossier(data); })
      .catch((e) => { if (alive) setError(stepError("Couldn't load that card", e)); })
      .finally(() => { if (alive) setDLoading(false); });
    return () => { alive = false; };
  }, [sel, src?.source]); // eslint-disable-line react-hooks/exhaustive-deps

  const byId = useMemo(() => Object.fromEntries((src?.cards || []).map((c) => [c.id, c])), [src]);
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!src || !q) return [];
    return src.cards.filter((c) => c.name.toLowerCase().includes(q))
      .sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || (b.elo || 0) - (a.elo || 0)).slice(0, 40);
  }, [src, query]);
  const dossierRef = useRef(null);
  const pick = (id) => {
    setSel(id); setTab("cards");
    setTimeout(() => {
      const el = dossierRef.current;
      if (el) window.scrollTo({ top: Math.max(0, el.getBoundingClientRect().top + window.scrollY - 16), behavior: "smooth" });
    }, 50);
  };

  // Run the draft, or re-draft from table pick `from` (picks before it are kept) with the Lab's weights.
  const runDraft = async (from = null) => {
    setSimming(true); setError("");
    const fork = from != null && sim;
    const cfg = fork ? { seats: sim.seats.length, picks: sim.per_seat, seed: sim.seed } : simCfg;
    const body = { ...cfg, tuning: labTuning, tuned_seats: tunedSeats ? [...tunedSeats] : null, start: fork ? sim.picks.slice(0, from) : [] };
    try {
      const { data } = await withSource((source) => api.post("/lab/simulate", { source, ...body }, { timeout: 180000 }));
      const sameDraft = sim && sim.seed === cfg.seed && sim.order.length === data.order.length;
      setPrev(sameDraft ? sim : null);
      setSim({ ...data, seed: cfg.seed, tuning: body.tuning, tuned_seats: body.tuned_seats });
      setRuns((r) => r + 1);
      const at = fork ? Math.min(from, data.picks.length - 1) : 0;
      setFocus({ ...slotFocus(data.order, at), at });
    } catch (e) { setError(stepError("Couldn't run the draft", e)); } finally { setSimming(false); }
  };
  const labFetch = useCallback((body) => withSource((source) => api.post("/lab/view", { source, order: sim.order, picks: sim.picks, ...body }, { timeout: 60000 })), [withSource, sim]);
  const simSeats = useMemo(() => Array.from({ length: simCfg.seats }, (_, i) => ({ index: i, player_name: `Bot ${i + 1}` })), [simCfg.seats]);
  const simSeatsUsed = useMemo(() => (sim ? Array.from(new Set(sim.order)).sort((a, b) => a - b).map((i) => ({ index: i, player_name: `Bot ${i + 1}` })) : simSeats), [sim, simSeats]);
  const changed = useMemo(() => {
    const out = new Set();
    if (sim && prev) sim.picks.forEach((p, i) => { if (prev.picks[i]?.card_id !== p.card_id) out.add(i); });
    return out;
  }, [sim, prev]);
  const goSlot = (slot) => { if (!sim) return; const at = Math.max(0, Math.min(slot, sim.picks.length - 1)); setFocus({ ...slotFocus(sim.order, at), at }); };
  const viewPick = sim?.picks[viewSlot];
  const changedCount = Object.keys(labTuning).length;
  const toggleSeat = (i) => setTunedSeats((t) => {
    const next = new Set(t || []);
    if (next.has(i)) next.delete(i); else next.add(i);
    return next.size ? next : null;
  });

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100">
      <header className="border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <div className="flex items-center gap-4 text-sm"><Link to="/draft" className="text-slate-400 hover:text-white">Cube Draft</Link><Link to="/dashboard" className="text-slate-400 hover:text-white">My Decks</Link></div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-bold flex items-center gap-2"><Brain className="w-7 h-7 text-amber-400" /> Bot Brain</h1>
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">How the draft bots see a card pool: look up any card, or run an all-bot draft and step through what each bot was thinking at every pick.</p>
          </div>
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); loadSource({ m: mode, id: cubeId }); }} data-testid="brain-source">
            {pools.length > 0 && <>
              <label htmlFor="brain-pool" className="sr-only">Saved pools</label>
              <select id="brain-pool" value={pools.some((p) => p.key === src?.source) ? src.source : ""} data-testid="brain-pool"
                onChange={(e) => { if (e.target.value) loadSource({ pool: e.target.value }); }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm max-w-[220px]" title="Pools built before load instantly, with no CubeCobra or Scryfall lookups">
                <option value="">Saved pools…</option>
                {pools.map((p) => <option key={p.key} value={p.key}>{PRESETS.find(([, v]) => v === p.label)?.[0] || p.label} · {p.cards} cards{p.partial ? " (partial)" : ""}</option>)}
              </select>
            </>}
            <div className="inline-flex rounded-lg border border-slate-700 overflow-hidden text-sm">
              {[["cube", "Cube"], ["vrd", "VRD"]].map(([m, l]) => (
                <button key={m} type="button" onClick={() => { setMode(m); if (m === "vrd") loadSource({ m: "vrd" }); }} aria-pressed={mode === m}
                  className={`px-3 py-1.5 ${mode === m ? "bg-amber-400 text-stone-900 font-semibold" : "text-slate-300 hover:bg-slate-800"}`} data-testid={`brain-mode-${m}`}>{l}</button>
              ))}
            </div>
            {mode === "cube" && <>
              <label htmlFor="brain-preset" className="sr-only">Cube</label>
              <select id="brain-preset" value={PRESETS.some(([, v]) => v === cubeId) ? cubeId : ""} data-testid="brain-preset"
                onChange={(e) => { if (e.target.value) { setCubeId(e.target.value); loadSource({ m: "cube", id: e.target.value }); } }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm">
                {PRESETS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}
                <option value="">Other CubeCobra cube…</option>
              </select>
              <label htmlFor="brain-cube" className="sr-only">CubeCobra cube ID or link (join several with +)</label>
              <input id="brain-cube" value={cubeId} onChange={(e) => setCubeId(e.target.value)} placeholder="CubeCobra ID, or A + B"
                title="CubeCobra ID or link. Join several cubes with + to combine them (duplicates removed)."
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm w-56" />
              <button type="submit" className="px-3 py-1.5 rounded-lg border border-slate-700 text-sm text-slate-200 hover:text-amber-300 flex items-center gap-1.5" data-testid="brain-load"><Library className="w-4 h-4" /> Load</button>
            </>}
          </form>
        </div>

        {error && <p className="text-sm text-red-300" role="alert">{error}</p>}
        {step && <p className="text-sm text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> {step}</p>}

        {src && (
          <>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-slate-400">
              <span><span className="text-slate-100 font-semibold tabular-nums">{src.summary.cards}</span> cards</span>
              <span><span className="text-slate-100 font-semibold tabular-nums">{src.summary.with_partners}</span> with CubeCobra links</span>
              <span><span className="text-slate-100 font-semibold tabular-nums">{src.summary.combos}</span> combos</span>
              {src.label && <span title={src.built_at ? `Built ${new Date(src.built_at).toLocaleString()}` : undefined}>Saved as <span className="text-slate-200">{PRESETS.find(([, v]) => v === src.label)?.[0] || src.label}</span>{src.built_at && <> · built {new Date(src.built_at).toLocaleDateString()}</>}</span>}
              {src.partial && <span className="text-amber-300">Some CubeCobra data was still loading when this pool was built{src.vrd ? " (1,500 card pages, about 10–20 minutes the first time)" : ""}; rebuild it later for the full picture.</span>}
              <button type="button" onClick={() => loadSource({ m: src.vrd ? "vrd" : "cube", id: cubeId, refresh: true })} data-testid="brain-rebuild"
                title="Read the cube list, CubeCobra links and combos again, and save the new pool"
                className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 flex items-center gap-1"><RefreshCw className="w-3 h-3" /> Rebuild</button>
              <div className="ml-auto inline-flex rounded-lg border border-slate-700 overflow-hidden">
                {[["cards", "Cards", Search], ["sim", "Simulate a draft", Shuffle]].map(([t, l, Icon]) => (
                  <button key={t} type="button" onClick={() => setTab(t)} aria-pressed={tab === t} data-testid={`brain-tab-${t}`}
                    className={`px-3 py-1.5 flex items-center gap-1.5 ${tab === t ? "bg-slate-800 text-amber-300" : "text-slate-300 hover:bg-slate-900"}`}><Icon className="w-4 h-4" /> {l}</button>
                ))}
              </div>
            </div>

            {tab === "cards" ? (
              <div className="grid lg:grid-cols-[300px_minmax(0,1fr)] gap-6">
                <aside className="space-y-5 min-w-0">
                  <div className="relative">
                    <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input id="brain-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${src.summary.cards} cards…`} data-testid="brain-search"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm" />
                  </div>
                  {query.trim() ? (
                    <div>{results.length ? results.map((c) => <CardLink key={c.id} c={c} onPick={(id) => { pick(id); setQuery(""); }} />) : <p className="text-sm text-slate-500 px-2">No card by that name in this pool.</p>}</div>
                  ) : (
                    <>
                      <section><h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-1 px-2">Most connected</h3>
                        {src.summary.connected.slice(0, 12).map((c) => <CardLink key={c.id} c={c} onPick={pick} right={`${c.links} links`} />)}</section>
                      <section className="space-y-3"><h3 className="text-[11px] uppercase tracking-wider text-slate-500 px-2">Deck types</h3>
                        {src.summary.decks.filter((d) => d.key_count).map((d) => (
                          <div key={d.type} className="px-2 space-y-1">
                            <div className="text-sm font-semibold flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: DECK_COL[d.type] }} />{DECK_NAMES[d.type]}<span className="text-xs font-normal text-slate-500 tabular-nums">{d.key_count} key · {d.member_count} members</span></div>
                            <div className="text-xs text-slate-400 leading-relaxed">{d.keys.slice(0, 6).map((c, k) => <React.Fragment key={c.id}>{k > 0 && ", "}<button type="button" onClick={() => pick(c.id)} className="hover:text-amber-300">{c.name.split(" // ")[0]}</button></React.Fragment>)}{d.key_count > 6 && "…"}</div>
                          </div>
                        ))}</section>
                    </>
                  )}
                </aside>
                <section className="min-w-0 relative" ref={dossierRef}>
                  {dLoading && <Loader2 className="w-4 h-4 animate-spin text-amber-400 absolute right-0 top-0" />}
                  {dossier ? <Dossier d={dossier} card={byId[dossier.id]} onPick={pick} /> : !dLoading && <p className="text-sm text-slate-500">Search for a card to see how the bots read it.</p>}
                </section>
              </div>
            ) : (
              <div className="space-y-4">
                <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); runDraft(null); }} data-testid="brain-sim-form">
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Bots</span>
                    <select id="brain-seats" value={simCfg.seats} onChange={(e) => setSimCfg((c) => ({ ...c, seats: Number(e.target.value) }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5">
                      {Array.from({ length: 11 }, (_, i) => i + 2).map((n) => <option key={n} value={n}>{n}</option>)}
                    </select></label>
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Picks each</span>
                    <input id="brain-picks" type="number" min={5} max={60} value={simCfg.picks} onChange={(e) => setSimCfg((c) => ({ ...c, picks: Math.max(5, Math.min(60, Number(e.target.value) || 45)) }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 w-20" /></label>
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Seed</span>
                    <span className="flex gap-1"><input id="brain-seed" type="number" value={simCfg.seed} onChange={(e) => setSimCfg((c) => ({ ...c, seed: Number(e.target.value) || 0 }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 w-24" />
                      <button type="button" onClick={() => setSimCfg((c) => ({ ...c, seed: Math.floor(Math.random() * 10000) }))} className="px-2 rounded-lg border border-slate-700 text-slate-300 hover:text-amber-300" aria-label="New random seed"><Dices className="w-4 h-4" /></button></span></label>
                  <button type="submit" disabled={simming} className="px-4 py-2 rounded-lg bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-sm flex items-center gap-2 disabled:opacity-60" data-testid="brain-run">
                    {simming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} {sim ? "Run again" : "Run draft"}</button>
                  <p className="text-xs text-slate-500 basis-full sm:basis-auto sm:flex-1">The bots draft with the weights set in the panel below. Same seed and weights give the same draft, so you can rewind to any pick, change weights and re-draft from there. {mode === "vrd" && "VRD drafts take longer: the pool is three times the size of a cube."}</p>
                </form>
                {simming && <p className="text-sm text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> The bots are drafting… usually a few seconds.</p>}
                {sim ? (
                  <>
                    {/* Step through the table, rewind and re-draft */}
                    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 space-y-3" data-testid="brain-replay">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="flex items-center gap-1">
                          {[[ChevronsLeft, "First pick", () => goSlot(0)], [ChevronLeft, "Previous table pick", () => goSlot(viewSlot - 1)],
                            [ChevronRight, "Next table pick", () => goSlot(viewSlot + 1)], [ChevronsRight, "Last pick", () => goSlot(sim.picks.length - 1)]].map(([Icon, label, fn]) => (
                            <button key={label} type="button" onClick={fn} aria-label={label} title={label} className="p-1.5 rounded border border-slate-700 text-slate-300 hover:text-amber-300"><Icon className="w-4 h-4" /></button>
                          ))}
                        </div>
                        <span className="text-sm text-slate-300 tabular-nums">Table pick <span className="text-slate-100 font-semibold">{viewSlot + 1}</span> of {sim.picks.length}
                          {viewPick && <> · Bot {viewPick.seat_index + 1} took <span className="text-slate-100">{shortName(byId[viewPick.card_id]?.name)}</span></>}</span>
                        <span className="text-xs text-slate-500 ml-auto tabular-nums">{sim.seconds != null && `${sim.seconds}s`}{sim.kept > 0 && ` · first ${sim.kept} picks kept`}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <button type="button" disabled={simming} onClick={() => runDraft(viewSlot)} data-testid="brain-redraft"
                          className="px-3 py-1.5 rounded-lg bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-sm flex items-center gap-1.5 disabled:opacity-60">
                          <Undo2 className="w-4 h-4" /> Re-draft from pick {viewSlot + 1}</button>
                        <button type="button" disabled={simming} onClick={() => runDraft(0)} className="px-3 py-1.5 rounded-lg border border-slate-700 text-sm text-slate-200 hover:text-amber-300 disabled:opacity-60">Re-draft all (same seed)</button>
                        <span className="text-xs text-slate-400">{changedCount ? `${changedCount} weight${changedCount === 1 ? "" : "s"} changed in the panel below` : "Using the current weights: change some below first"}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        <span className="text-slate-500 mr-1">New weights for:</span>
                        <button type="button" onClick={() => setTunedSeats(null)} aria-pressed={!tunedSeats} className={`px-2 py-0.5 rounded-full border ${!tunedSeats ? "border-amber-400 text-amber-300" : "border-slate-700 text-slate-400"}`}>Every bot</button>
                        {simSeatsUsed.map((s) => (
                          <button key={s.index} type="button" onClick={() => toggleSeat(s.index)} aria-pressed={!!tunedSeats?.has(s.index)} data-testid={`brain-tuned-${s.index}`}
                            className={`px-2 py-0.5 rounded-full border tabular-nums ${tunedSeats?.has(s.index) ? "border-amber-400 text-amber-300" : "border-slate-700 text-slate-400"}`}>{s.index + 1}</button>
                        ))}
                        <span className="text-slate-500 ml-1">Pick a few seats to pit new weights against the current ones in the same draft.</span>
                      </div>
                      {prev && (
                        <p className="text-sm flex items-center gap-2 text-sky-300" data-testid="brain-diff"><GitCompare className="w-4 h-4" />
                          {changed.size ? `${changed.size} of ${sim.picks.length - sim.kept} re-drafted picks changed (outlined in blue).` : "Same picks as before: these weights change nothing from here."}
                          <button type="button" onClick={() => setPrev(null)} className="text-xs text-slate-400 hover:text-white underline">clear</button></p>
                      )}
                    </div>

                    <DraftBoard sim={sim} byId={byId} seats={simSeatsUsed} viewSlot={viewSlot} changed={changed} kept={sim.kept} onPick={goSlot} />

                    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="brain-sim-seats">
                      {sim.seats.map((s) => (
                        <SeatSummary key={s.seat} s={s} before={prev?.seats.find((x) => x.seat === s.seat)} name={`Bot ${s.seat + 1}`}
                          tuned={Object.keys(sim.tuning || {}).length > 0 && (!sim.tuned_seats || sim.tuned_seats.includes(s.seat))} />
                      ))}
                    </div>
                    <BotLab inline fetchView={labFetch} cubeById={byId} seats={simSeatsUsed} startSeat={0} reloadKey={runs} onClose={() => {}}
                      focus={focus} onSlot={setViewSlot} onTuning={setLabTuning} />
                  </>
                ) : !simming && <p className="text-sm text-slate-500">Run a draft to step through the bots' picks.</p>}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
