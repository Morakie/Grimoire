import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { resolveCube, stepError } from "@/lib/cube";
import BotLab from "@/components/BotLab";
import { DECK_NAMES, deckName, deckCol } from "@/lib/deckTypes";
import { startEngine, poolBytes } from "@/lib/labEngine";
import { Sparkles, Loader2, Brain, Search, Shuffle, Dices, Play, Network, Library, RefreshCw, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, GitCompare, Zap, Cpu, Server, Square, Download, ClipboardCopy, Maximize2, Minimize2 } from "lucide-react";

// Bot Brain: how the draft bots think, outside any draft. Load a cube (CubeCobra) or the VRD pool, then
// look up any card (what the bots know about it and what it links to) or run an all-bot draft, turn the
// weights and watch the draft change. A built pool is saved on the server (one document); the page downloads
// it once, keeps it in this browser and runs the same bot code here (lib/labEngine.js), so turning knobs and
// re-drafting never call the server. If the in-browser engine can't start, the server runs the bots instead.

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
  if (d.key_of.length) return `A key card: owning it puts a bot into ${d.key_of.map((t) => deckName(t)).join(" and ")}. Bots not in that deck type count it at 55%, unless the deck type is still open early in the draft.`;
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
              <span className="text-slate-300">{deckName(t)}</span>
              <span className="relative h-2 rounded bg-slate-800 overflow-hidden"><span className="absolute inset-y-0 left-0 rounded" style={{ width: `${v * 100}%`, background: deckCol(t) }} /><span className="absolute -inset-y-0.5 left-1/2 w-px bg-slate-500" title="A bot counts a card as in from 50%" /></span>
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

function DraftBoard({ sim, base, byId, seats, viewSlot, changed, kept, onPick, full = false }) {
  const n = seats.length;
  const rounds = Math.ceil(sim.order.length / n);       // the whole board, filling in as picks stream in
  const bySlot = sim.picks;
  const cell = (r, s) => r * n + (r % 2 === 0 ? s : n - 1 - s);
  const viewRef = useRef(null);
  useEffect(() => { if (!full) viewRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [viewSlot, full]);
  return (
    <div className={`overflow-auto rounded-lg border border-slate-800 bg-slate-950 ${full ? "" : "max-h-[46vh]"}`} data-testid="brain-board">
      <table className={`${full ? "text-[10px] leading-tight" : "text-[11px]"} border-separate border-spacing-0 w-full`}>
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
                if (!p) return <td key={s.index} className="p-0.5"><span className="block rounded px-1 py-0.5 text-slate-700">·</span></td>;
                const c = byId[p.card_id];
                const here = slot === viewSlot;
                const ch = changed.has(slot);
                const was = ch && base?.picks[slot] ? byId[base.picks[slot].card_id]?.name : null;
                return (
                  <td key={s.index} className="p-0.5" ref={here ? viewRef : undefined}>
                    <button type="button" onClick={() => onPick(slot)} title={`Table pick ${slot + 1}: ${c?.name || "?"}${was ? ` (was ${was} with the current weights)` : ""}`}
                      data-testid={`brain-board-${slot}`}
                      className={`w-full text-left flex items-center gap-1 rounded px-1 ${full ? "py-0" : "py-0.5"} border ${here ? "border-amber-400 bg-amber-400/15 text-amber-100" : ch ? "border-sky-400/70 bg-sky-400/10 text-slate-100" : "border-transparent hover:bg-slate-800/70 text-slate-300"} ${slot < kept ? "opacity-60" : ""}`}>
                      <span className="w-1.5 h-3 rounded-sm shrink-0" style={{ background: c ? colourOf(c) : "#334155" }} />
                      <span className={`truncate ${full ? "max-w-[150px]" : "max-w-[118px]"}`}>{shortName(c?.name)}</span>
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

function Persona({ p }) {
  if (!p) return null;
  return <div className="text-[11px] text-slate-500" title="This bot's personality: its style, and the deck type it leans towards early (a nudge, dropped if the lane is taken)">
    {p.archetype}{p.lean ? <> · leans <span style={{ color: deckCol(p.lean) }}>{deckName(p.lean)}</span></> : " · no lean"}</div>;
}

function SeatSummary({ s, before, name, tuned }) {
  const decks = Object.entries(s.decks || {});
  const deckText = (d) => Object.keys(d || {}).slice(0, 2).map((t) => deckName(t)).join(", ") || "no deck type";
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
      <div className="text-xs text-slate-300">{decks.length ? decks.slice(0, 3).map(([t, v]) => `${deckName(t)} ${Math.round(v * 100)}%`).join(" · ") : <span className="text-slate-500">No deck type</span>}</div>
      <Persona p={s.persona} />
      {s.combos.length > 0 && <div className="text-xs text-fuchsia-300">{s.combos.map((cb) => cb.map(shortName).join(" + ")).join("; ")}</div>}
      {moved && <div className="text-xs text-sky-300">Was {before.pair ? <SeatPips pair={before.pair} /> : "open"} · {deckText(before.decks)}</div>}
    </div>
  );
}


// ---------------------------------------------------------------- lanes at a pick: who is in which deck type

function LanesStrip({ lanes, focusSeat, onSeat, personas }) {
  if (!lanes) return null;
  const types = Object.keys(DECK_NAMES).filter((t) => lanes.seats.some((s) => (s.decks[t] || 0) >= 0.25));
  const inLane = (t) => lanes.seats.filter((s) => (s.decks[t] || 0) >= 0.5).length;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 space-y-2" data-testid="brain-lanes">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">Lanes before table pick {lanes.slot + 1} <span className="normal-case tracking-normal">· a seat counts as in a deck type from 50%</span></div>
      {types.length === 0 ? <p className="text-sm text-slate-500">No seat leans towards a deck type yet.</p> : (
        <div className="overflow-x-auto">
          <table className="text-xs border-separate border-spacing-0.5">
            <thead><tr><th />
              {types.map((t) => {
                const n = inLane(t);
                return <th key={t} className="px-1 text-left font-normal min-w-[78px]"><span className="flex items-center gap-1 text-slate-300"><span className="w-2 h-2 rounded-full" style={{ background: deckCol(t) }} />{deckName(t)}</span>
                  <span className={`tabular-nums ${n >= 3 ? "text-rose-400 font-semibold" : n === 2 ? "text-amber-300" : "text-slate-500"}`}>{n} seat{n === 1 ? "" : "s"}{n >= 3 ? " · crowded" : ""}</span></th>;
              })}</tr></thead>
            <tbody>
              {lanes.seats.map((s) => (
                <tr key={s.seat} className={s.seat === focusSeat ? "bg-amber-400/10" : ""}>
                  <td className="pr-2 whitespace-nowrap"><button type="button" onClick={() => onSeat?.(s.seat)} className={`flex items-center gap-1.5 ${s.seat === focusSeat ? "text-amber-200" : "text-slate-300 hover:text-amber-300"}`}>Bot {s.seat + 1} <SeatPips pair={s.pair} />
                    {personas?.[s.seat]?.lean && <span className="text-[10px]" style={{ color: deckCol(personas[s.seat].lean) }} title="The deck type this bot leans towards early">leans {deckName(personas[s.seat].lean)}</span>}</button></td>
                  {types.map((t) => {
                    const v = s.decks[t] || 0;
                    return <td key={t} title={`${deckName(t)} ${Math.round(v * 100)}%`}><span className="relative block h-3.5 rounded bg-slate-800 overflow-hidden">
                      <span className="absolute inset-y-0 left-0" style={{ width: `${v * 100}%`, background: deckCol(t), opacity: v >= 0.5 ? 0.95 : 0.45 }} /></span></td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- a seat's synergy web at a pick

// The seat's cards on a ring (grouped by deck type), the cards it is weighing in the middle, and the CubeCobra
// links between them: hover a candidate to see which of the seat's cards pull it up.
function SeatWeb({ web, seatName, scores, took, onPick }) {
  const W = 760, H = 440;
  const [hover, setHover] = useState(null);
  const layout = useMemo(() => {
    if (!web) return null;
    const order = ["", ...Object.keys(DECK_NAMES)];
    const owned = web.nodes.filter((n) => !n.candidate).sort((a, b) => order.indexOf(a.deck) - order.indexOf(b.deck) || b.elo - a.elo);
    const cands = web.nodes.filter((n) => n.candidate);
    const pos = {};
    owned.forEach((n, k) => {
      const t = -Math.PI / 2 + (k / Math.max(owned.length, 1)) * Math.PI * 2;
      pos[n.id] = { ...n, x: W / 2 + Math.cos(t) * 300, y: H / 2 + Math.sin(t) * 172, left: Math.cos(t) < -0.05 };
    });
    cands.forEach((n, k) => {
      pos[n.id] = { ...n, x: W / 2, y: H / 2 - ((cands.length - 1) / 2 - k) * 34 };
    });
    const links = {};
    web.edges.forEach(([a, b, s]) => {
      [[a, b], [b, a]].forEach(([x, y]) => { if (pos[x]?.candidate && pos[y] && !pos[y].candidate) (links[x] = links[x] || []).push([y, s]); });
    });
    return { pos, owned, cands, links };
  }, [web]);
  if (!layout) return null;
  const { pos, owned, cands, links } = layout;
  const lit = hover ?? cands[0]?.id;
  return (
    <div className="space-y-2" data-testid="brain-web">
      <h3 className="text-[11px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5"><Network className="w-3.5 h-3.5" /> {seatName}'s synergy web at this pick</h3>
      <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px] h-auto block" role="img" aria-label={`${seatName}'s cards, the cards it is weighing, and how they link`}>
          {web.edges.map(([a, b, s], k) => {
            const pa = pos[a], pb = pos[b];
            if (!pa || !pb) return null;
            const toCand = pa.candidate || pb.candidate;
            const on = toCand && (a === lit || b === lit);
            if (pa.candidate && pb.candidate) return null;
            return <line key={k} x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y} stroke={on ? "#fbbf24" : toCand ? "#64748b" : "#38bdf8"}
              strokeOpacity={on ? 0.85 : toCand ? 0.06 : (s >= 1 ? 0.35 : 0.14)} strokeWidth={on ? (s >= 1 ? 2 : 1.2) : (s >= 1 ? 1.2 : 0.7)} />;
          })}
          {owned.map((n) => {
            const p = pos[n.id];
            const linked = (links[lit] || []).some(([y]) => y === n.id);
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer" onClick={() => onPick(n.id)}>
                <circle r={6} fill={colourOf(n)} stroke={n.deck ? deckCol(n.deck) : "#020617"} strokeWidth={n.deck ? 2.5 : 1} />
                <text x={p.left ? -10 : 10} y={4} textAnchor={p.left ? "end" : "start"} fontSize={10.5} fill={linked ? "#fde68a" : "#cbd5e1"}
                  style={{ paintOrder: "stroke", stroke: "#020617", strokeWidth: 3 }}>{shortName(n.name).slice(0, 18)}</text>
              </g>
            );
          })}
          {cands.map((n) => {
            const p = pos[n.id];
            const ls = links[n.id] || [];
            const strength = ls.reduce((t, [, s]) => t + s, 0);
            const on = n.id === lit;
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer" onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} onClick={() => onPick(n.id)}>
                <rect x={-104} y={-13} width={208} height={26} rx={6} fill={on ? "#422006" : "#0f172a"} stroke={n.id === took ? "#fbbf24" : on ? "#f59e0b" : "#334155"} strokeWidth={n.id === took ? 2 : 1} />
                <circle cx={-92} r={5} fill={colourOf(n)} />
                <text x={-82} y={4} fontSize={11} fill="#f1f5f9">{shortName(n.name).slice(0, 19)}</text>
                <text x={98} y={4} fontSize={10} textAnchor="end" fill={ls.length ? "#fbbf24" : "#64748b"}>{scores[n.id] != null ? `${scores[n.id].toFixed(2)} · ` : ""}{ls.length} link{ls.length === 1 ? "" : "s"}{strength ? ` (${strength.toFixed(1)})` : ""}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="text-xs text-slate-500">Ring: the seat's cards, grouped and outlined by deck type. Blue lines: links between its own cards (solid for "synergistic", faint for "often drafted with"). Middle: the cards it is weighing now, with score and how many of its cards they link to. Hover one to light up its links; tap any card to open it. The card taken has a gold border.</p>
    </div>
  );
}

// ---------------------------------------------------------------- export

// The draft as data (JSON) or as text to paste into a message: settings, weights, every seat's picks in order,
// what each seat ended up with, and the picks that differ from the current weights' draft.
function draftExport({ src, sim, base, byId, changed, engineVersion }) {
  const name = (id) => byId[id]?.name || id;
  const seats = Array.from(new Set(sim.order)).sort((a, b) => a - b);
  const summary = Object.fromEntries((sim.seats || []).map((x) => [x.seat, x]));
  const persona = (i) => sim.personas?.[i] || summary[i]?.persona || null;
  return {
    exported_at: new Date().toISOString(),
    pool: { label: src.label, key: src.source, cards: src.summary.cards, combos: src.summary.combos, built_at: src.built_at, partial: !!src.partial },
    engine: engineVersion || null,
    settings: { seats: seats.length, picks_each: sim.per_seat, seed: base?.seed ?? null, personalities: !!base?.cfg?.personas,
      weights: sim.tuning || {}, weights_from_pick: (sim.from || 0) + 1, weights_for_seats: sim.tuned_seats ? sim.tuned_seats.map((x) => x + 1) : "all" },
    seats: seats.map((i) => ({
      bot: i + 1, persona: persona(i),
      colours: summary[i]?.pair ?? null, deck_types: summary[i]?.decks ?? null, on_colour: summary[i]?.on_colour ?? null,
      avg_elo: summary[i]?.avg_elo ?? null, combos: summary[i]?.combos ?? [],
      picks: sim.picks.filter((p) => p.seat_index === i).map((p) => name(p.card_id)),
    })),
    changed_from_current_weights: [...changed].sort((a, b) => a - b).map((slot) => ({
      table_pick: slot + 1, bot: sim.picks[slot].seat_index + 1, took: name(sim.picks[slot].card_id), was: name(base.picks[slot]?.card_id),
    })),
  };
}

function exportText(x) {
  const lines = [`Bot Brain draft (bots ${x.engine ? x.engine.slice(0, 7) : "server"}): ${x.pool.label} (${x.pool.cards} cards, ${x.pool.combos} combos${x.pool.partial ? ", partial" : ""}), seed ${x.settings.seed}, ${x.settings.seats} bots x ${x.settings.picks_each}, personalities ${x.settings.personalities ? "on" : "off"}`];
  const w = Object.entries(x.settings.weights);
  lines.push(w.length ? `Weights changed: ${w.map(([k, v]) => `${k}=${v}`).join(", ")} (from pick ${x.settings.weights_from_pick}, seats: ${x.settings.weights_for_seats})` : "Weights: current defaults");
  x.seats.forEach((s) => {
    const decks = Object.entries(s.deck_types || {}).map(([t, v]) => `${deckName(t)} ${Math.round(v * 100)}%`).join(", ");
    const p = s.persona ? ` · ${s.persona.archetype}${s.persona.lean ? `, leans ${deckName(s.persona.lean)}` : ""}` : "";
    lines.push("", `Bot ${s.bot} [${s.colours || "open"}${decks ? ` · ${decks}` : ""}${s.avg_elo ? ` · Elo ${s.avg_elo}` : ""}${p}]`);
    lines.push(s.picks.map((n, i) => `${i + 1}. ${n.split(" // ")[0]}`).join(", "));
  });
  if (x.changed_from_current_weights.length) {
    lines.push("", "Changed picks (took / was with current weights):");
    x.changed_from_current_weights.slice(0, 80).forEach((c) => lines.push(`  #${c.table_pick} Bot ${c.bot}: ${c.took} / ${c.was}`));
  }
  return lines.join("\n");
}

// ---------------------------------------------------------------- page

const sameCfg = (a, b) => a && b && a.seats === b.seats && a.picks === b.picks && a.seed === b.seed && a.pool === b.pool && !!a.personas === !!b.personas;

export default function BotBrain() {
  const saved = load(STORE, {});
  const [mode, setMode] = useState(saved.mode || "cube");
  const [cubeId, setCubeId] = useState(saved.cubeId || PRESETS[1][1]);
  const [src, setSrc] = useState(null);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState(saved.tab || "cards");
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(null);
  const [dossier, setDossier] = useState(null);
  const [dLoading, setDLoading] = useState(false);
  const [pools, setPools] = useState(null);
  const [engineState, setEngineState] = useState("starting");   // starting | ready | failed
  // Drafts: `base` is the draft with the current (default) weights; `sim` is what the board shows: the base
  // draft, or the same draft with the Lab's weights from table pick `from` on. Same seed, so every difference
  // between the two comes from the weights.
  const [simCfg, setSimCfg] = useState({ seats: 8, picks: 45, seed: Math.floor(Math.random() * 10000), personas: saved.personas ?? true });
  const [base, setBase] = useState(null);
  const [sim, setSim] = useState(null);
  const [running, setRunning] = useState("");
  const [from, setFrom] = useState(0);
  const [live, setLive] = useState(saved.live ?? true);
  const [runs, setRuns] = useState(0);
  const [viewSlot, setViewSlot] = useState(0);
  const [focus, setFocus] = useState(null);
  const [labTuning, setLabTuning] = useState({});  // weights changed in the Lab panel
  const [tunedSeats, setTunedSeats] = useState(null); // null = new weights for every bot
  const [lanes, setLanes] = useState(null);
  const [labView, setLabView] = useState(null);
  const [fullBoard, setFullBoard] = useState(false);
  const [engineVersion, setEngineVersion] = useState("");
  const [exported, setExported] = useState("");
  const [web, setWeb] = useState(null);
  const cubeCards = useRef(null);          // the resolved cube, to send again if the server forgot the pool
  const engine = useRef(null);
  const runId = useRef(0);
  const simRef = useRef(null);
  simRef.current = sim;
  const local = !!src?.local;

  useEffect(() => { save(STORE, { ...load(STORE, {}), tab, live, personas: simCfg.personas }); }, [tab, live, simCfg.personas]);

  // The in-browser engine: started once per visit. If it can't start, the server runs the bots.
  useEffect(() => {
    try {
      engine.current = startEngine();
      engine.current.ready.then((v) => { setEngineState("ready"); setEngineVersion(v || ""); }, () => setEngineState("failed"));
    } catch { setEngineState("failed"); }
  }, []);

  const refreshPools = useCallback(() => api.get("/lab/pools").then(({ data }) => { setPools(data.pools || []); return data.pools || []; }).catch(() => { setPools([]); return []; }), []);

  // A saved pool into this browser's engine: its data from this browser if it has the latest build, else
  // downloaded once. Falls back to the server's copy if the engine can't start.
  const openPool = useCallback(async (meta) => {
    try {
      const { bytes, cached } = await poolBytes(meta, setStep);
      setStep(cached ? "Opening the pool from this browser…" : "Opening the pool…");
      await engine.current.ready;
      setStep("Reading the pool into the bot engine…");
      const data = await engine.current.call("load", bytes);
      return { ...data, source: meta.key, label: meta.label, built_at: meta.built_at, partial: meta.partial, vrd: meta.vrd, local: true, cached };
    } catch (e) {
      setEngineState("failed");
      console.warn("Bot Brain: running on the server instead:", e);
      setStep("Loading the saved pool on the server…");
      const { data } = await api.post("/lab/source", { pool: meta.key }, { timeout: 60000 });
      return data;
    }
  }, []);

  // Load a pool: a saved one (from this browser or downloaded once), or build it (CubeCobra cube or VRD).
  const loadSource = useCallback(async ({ m = mode, id = cubeId, pool = null, refresh = false, list = null } = {}) => {
    setError(""); setSrc(null); setDossier(null); setSel(null); setSim(null); setBase(null); setLanes(null); setWeb(null);
    runId.current += 1; setRunning("");
    try {
      const known = list || pools || await refreshPools();
      let meta = pool ? known.find((p) => p.key === pool) : (!refresh && known.find((p) => (m === "vrd" ? p.vrd : !p.vrd && p.label === id.trim())));
      let data = null;
      if (meta) data = await openPool(meta);
      else {
        let body;
        if (m === "vrd") { setStep("Building the VRD pool (every Vintage-legal card)…"); body = { vrd: true, refresh }; }
        else {
          const res = await resolveCube({ cubeCobra: id, onStep: setStep });
          cubeCards.current = res.cards;
          setStep("Reading CubeCobra links and combos for this cube… the first time can take 20 seconds");
          body = { cards: res.cards, label: id.trim(), refresh };
        }
        data = (await api.post("/lab/source", body, { timeout: 120000 })).data;
        const fresh = await refreshPools();
        meta = fresh.find((p) => p.key === data.source);
        if (meta && engineState !== "failed") data = await openPool(meta);
      }
      const isVrd = !!data.vrd;
      setMode(isVrd ? "vrd" : "cube");
      if (!isVrd && data.label) setCubeId(data.label);
      save(STORE, { ...load(STORE, {}), mode: isVrd ? "vrd" : "cube", cubeId: isVrd ? id : data.label || id, pool: data.source });
      setSrc(data);
      // The weights kept from last time, so the first draft already uses them.
      const kept = load(TUNING_STORE, {});
      const t = {};
      (data.knobs || []).forEach((k) => { if (kept[k.key] != null && Math.abs(kept[k.key] - k.default) > 1e-9) t[k.key] = kept[k.key]; });
      setLabTuning(t);
      const first = data.summary.connected[0]?.id || data.cards[0]?.id;
      if (first) setSel(first);
    } catch (e) {
      setError(e.message && !e.response ? e.message : stepError(m === "vrd" ? "Couldn't load the VRD pool" : "Couldn't load the cube", e));
    } finally { setStep(""); }
  }, [mode, cubeId, pools, refreshPools, openPool, engineState]);

  useEffect(() => {
    refreshPools().then((list) => loadSource(saved.pool && list.some((p) => p.key === saved.pool) ? { pool: saved.pool, list } : { list }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Server calls that need the pool on the server (only when the engine runs there).
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

  // One call to the bots: in this browser, or on the server.
  const ask = useCallback((op, body) => {
    if (local) return engine.current.call(op, body);
    const path = { card: "/lab/card", view: "/lab/view" }[op];
    if (!path) return Promise.resolve(null);
    return withSource((source) => api.post(path, op === "card" ? { source, card: body } : { source, ...body }, { timeout: 60000 })).then(({ data }) => data);
  }, [local, withSource]);

  useEffect(() => {
    if (!src || !sel) return;
    let alive = true;
    setDLoading(true);
    ask("card", sel)
      .then((data) => { if (alive) setDossier(data); })
      .catch((e) => { if (alive) setError(stepError("Couldn't load that card", e)); })
      .finally(() => { if (alive) setDLoading(false); });
    return () => { alive = false; };
  }, [sel, src?.source, ask]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // One draft: streamed pick by pick from this browser's engine, or in one go from the server.
  const draft = useCallback(async (cfg, id, show) => {
    if (local) {
      let run = null;
      await engine.current.run(cfg, (chunk) => {
        if (id !== runId.current) return;
        if (chunk.type === "start") run = { order: chunk.order, per_seat: chunk.per_seat, kept: chunk.kept, picks: chunk.picks, seats: null, personas: chunk.personas || null };
        else run = { ...run, picks: run.picks.concat(chunk.picks), seats: chunk.done ? chunk.seats : null };
        show(run);
      }, 4);
      return run;
    }
    const { data } = await withSource((source) => api.post("/lab/simulate", { source, ...cfg }, { timeout: 180000 }));
    if (id === runId.current) show(data);
    return data;
  }, [local, withSource]);

  const tuningKey = JSON.stringify([labTuning, tunedSeats ? [...tunedSeats].sort() : null, from]);
  const lastKey = useRef(tuningKey);
  const tuningKeyRef = useRef(tuningKey);
  tuningKeyRef.current = tuningKey;

  // Draft with the current settings: the default-weights draft first (once per seed), then, if the Lab has
  // changed weights, the same draft re-run with them from pick `from`.
  const go = useCallback(async (cfgIn = null) => {
    if (!src) return;
    const id = ++runId.current;
    lastKey.current = tuningKeyRef.current;     // a live re-draft still waiting would only repeat this one
    const cfg = { ...(cfgIn || (base ? { seats: base.seats_n, picks: base.picks_n, seed: base.seed, personas: base.cfg.personas } : simCfg)), pool: src.source };
    setError("");
    const started = performance.now();
    try {
      let b = base;
      if (!sameCfg(b?.cfg, cfg)) {
        setRunning("Drafting with the current weights…");
        setSim(null);
        const r = await draft({ seats: cfg.seats, picks: cfg.picks, seed: cfg.seed, personas: !!cfg.personas }, id, (run) => setSim({ ...run, tuning: {}, from: 0 }));
        if (id !== runId.current || !r) return;
        b = { ...r, cfg, seed: cfg.seed, seats_n: cfg.seats, picks_n: cfg.picks, seconds: (performance.now() - started) / 1000 };
        setBase(b);
        setSim({ ...b, tuning: {}, from: 0 });
        setFocus({ ...slotFocus(r.order, Math.min(viewSlot, r.picks.length - 1)), at: viewSlot });
      }
      if (!Object.keys(labTuning).length) {
        setSim({ ...b, tuning: {}, from: 0 }); setRunning(""); setRuns((n) => n + 1);
        return;
      }
      const at = Math.min(from, b.picks.length);
      setRunning(`Re-drafting from pick ${at + 1} with your weights…`);
      const t0 = performance.now();
      const body = { seats: cfg.seats, picks: cfg.picks, seed: cfg.seed, personas: !!cfg.personas, tuning: labTuning, tuned_seats: tunedSeats ? [...tunedSeats] : null, start: b.picks.slice(0, at) };
      const r = await draft(body, id, (run) => setSim({ ...run, tuning: labTuning, tuned_seats: body.tuned_seats, from: at }));
      if (id !== runId.current || !r) return;
      setSim({ ...r, tuning: labTuning, tuned_seats: body.tuned_seats, from: at, seconds: (performance.now() - t0) / 1000 });
      setRunning(""); setRuns((n) => n + 1);
    } catch (e) {
      if (id === runId.current) { setError(stepError("Couldn't run the draft", e)); setRunning(""); }
    }
  }, [src, base, simCfg, labTuning, tunedSeats, from, draft, viewSlot]);

  const stop = () => { runId.current += 1; setRunning(""); if (local) engine.current.stop(); };

  // Live: whenever the weights, the seats they apply to or the starting pick change, re-draft (after the
  // slider settles).
  useEffect(() => {
    if (!live || !base || tuningKey === lastKey.current) return undefined;
    const t = setTimeout(() => { if (lastKey.current !== tuningKey) { lastKey.current = tuningKey; go(); } }, local ? 450 : 900);
    return () => clearTimeout(t);
  }, [tuningKey, live, base, go, local]);
  useEffect(() => { lastKey.current = tuningKey; }, [runs]); // eslint-disable-line react-hooks/exhaustive-deps

  const labFetch = useCallback((body) => {
    const s = simRef.current;
    return ask("view", { order: s.order, picks: s.picks, ...body }).then((data) => ({ data }));
  }, [ask]);
  const simSeats = useMemo(() => Array.from({ length: simCfg.seats }, (_, i) => ({ index: i, player_name: `Bot ${i + 1}` })), [simCfg.seats]);
  const simSeatsUsed = useMemo(() => (sim ? Array.from(new Set(sim.order)).sort((a, b) => a - b).map((i) => ({ index: i, player_name: `Bot ${i + 1}` })) : simSeats), [sim?.order, simSeats]); // eslint-disable-line react-hooks/exhaustive-deps
  const tunedRun = sim && base && sim !== base && Object.keys(sim.tuning || {}).length > 0;
  const changed = useMemo(() => {
    const out = new Set();
    if (tunedRun) sim.picks.forEach((p, i) => { if (base.picks[i]?.card_id !== p.card_id) out.add(i); });
    return out;
  }, [sim, base, tunedRun]);
  const goSlot = (slot) => { if (!sim) return; const at = Math.max(0, Math.min(slot, sim.order.length - 1)); setFocus({ ...slotFocus(sim.order, at), at }); };
  const viewPick = sim?.picks[viewSlot];
  const changedCount = Object.keys(labTuning).length;
  const toggleSeat = (i) => setTunedSeats((t) => {
    const next = new Set(t || []);
    if (next.has(i)) next.delete(i); else next.add(i);
    return next.size ? next : null;
  });

  // Lanes and the synergy web follow the pick shown (in-browser engine only: they're cheap there).
  const doneKey = sim?.seats ? runs : -1;
  useEffect(() => {
    if (!local || !sim || !sim.seats) return;
    engine.current.call("lanes", { order: sim.order, picks: sim.picks, slot: viewSlot }).then(setLanes).catch(() => setLanes(null));
  }, [viewSlot, doneKey, local]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!local || !labView) { setWeb(null); return; }
    const cands = labView.rows.slice(0, 6).map((r) => r.card);
    if (labView.took && !cands.includes(labView.took.card)) cands.push(labView.took.card);
    engine.current.call("web", { owned: labView.seat_info.owned, candidates: cands }).then(setWeb).catch(() => setWeb(null));
  }, [labView, local]);
  const webScores = useMemo(() => {
    const out = {};
    (labView?.rows || []).forEach((r) => { out[r.card] = r.score; });
    if (labView?.took) out[labView.took.card] = labView.took.score;
    return out;
  }, [labView]);

  // A pool built while Spellbook or CubeCobra was still answering is saved again when the rest arrives (a newer
  // build of the same pool): offer it.
  const [poolUpdate, setPoolUpdate] = useState(null);
  useEffect(() => {
    setPoolUpdate(null);
    if (!src?.partial || !src.built_at) return undefined;
    let n = 0;
    const t = setInterval(async () => {
      n += 1;
      const list = await refreshPools();
      const newer = list.find((p) => p.key === src.source && p.built_at > src.built_at);
      if (newer || n >= 20) clearInterval(t);
      if (newer) setPoolUpdate(newer);
    }, 20000);
    return () => clearInterval(t);
  }, [src?.source, src?.built_at, src?.partial, refreshPools]);

  const where = local ? (src.cached ? "This browser · pool kept here" : "This browser") : engineState === "starting" ? "Server (the in-browser engine is starting)" : "Server";

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
            <p className="text-sm text-slate-400 mt-1 max-w-2xl">How the draft bots see a card pool: look up any card, or run an all-bot draft, turn the weights and watch the draft change.</p>
          </div>
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); loadSource({ m: mode, id: cubeId }); }} data-testid="brain-source">
            {pools?.length > 0 && <>
              <label htmlFor="brain-pool" className="sr-only">Saved pools</label>
              <select id="brain-pool" value={pools.some((p) => p.key === src?.source) ? src.source : ""} data-testid="brain-pool"
                onChange={(e) => { if (e.target.value) loadSource({ pool: e.target.value }); }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm max-w-[220px]" title="Pools built before: downloaded once, then kept in this browser">
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
              <span className={`flex items-center gap-1 ${local ? "text-emerald-400" : "text-slate-400"}`} title={local ? "The bots run in this browser: turning knobs and re-drafting don't call the server" : "The bots run on the server"} data-testid="brain-where">
                {local ? <Cpu className="w-3.5 h-3.5" /> : <Server className="w-3.5 h-3.5" />} {where}{local && engineVersion && <span className="text-slate-500" title="Bot logic version loaded when this page opened: reload the page to pick up newer bot changes"> · bots {engineVersion.slice(0, 7)}</span>}</span>
              {poolUpdate && <button type="button" onClick={() => loadSource({ pool: poolUpdate.key })} data-testid="brain-pool-update"
                className="text-xs px-2 py-1 rounded bg-emerald-500/15 border border-emerald-400/60 text-emerald-300 hover:bg-emerald-500/25">The rest of the combos arrived: load the updated pool</button>}
              {src.partial && !poolUpdate && <span className="text-amber-300">Some combos or CubeCobra links were still loading when this pool was built{src.vrd ? " (1,500 card pages, about 10–20 minutes the first time)" : ""}. Late combos are saved by themselves (this page offers the update when they land); missing links need a Rebuild later.</span>}
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
                            <div className="text-sm font-semibold flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: deckCol(d.type) }} />{deckName(d.type)}<span className="text-xs font-normal text-slate-500 tabular-nums">{d.key_count} key · {d.member_count} members</span></div>
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
                <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); go({ ...simCfg }); }} data-testid="brain-sim-form">
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Bots</span>
                    <select id="brain-seats" value={simCfg.seats} onChange={(e) => setSimCfg((c) => ({ ...c, seats: Number(e.target.value) }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5">
                      {Array.from({ length: 11 }, (_, i) => i + 2).map((n) => <option key={n} value={n}>{n}</option>)}
                    </select></label>
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Picks each</span>
                    <input id="brain-picks" type="number" min={5} max={60} value={simCfg.picks} onChange={(e) => setSimCfg((c) => ({ ...c, picks: Math.max(5, Math.min(60, Number(e.target.value) || 45)) }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 w-20" /></label>
                  <label className="text-sm"><span className="block text-[11px] uppercase tracking-wider text-slate-500 mb-1">Seed</span>
                    <span className="flex gap-1"><input id="brain-seed" type="number" value={simCfg.seed} onChange={(e) => setSimCfg((c) => ({ ...c, seed: Number(e.target.value) || 0 }))} className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 w-24" />
                      <button type="button" onClick={() => setSimCfg((c) => ({ ...c, seed: Math.floor(Math.random() * 10000) }))} className="px-2 rounded-lg border border-slate-700 text-slate-300 hover:text-amber-300" aria-label="New random seed"><Dices className="w-4 h-4" /></button></span></label>
                  <label className="text-sm flex items-center gap-2 pb-2 cursor-pointer" title="Each bot gets a random style and a different deck type to lean towards early, as at a real table. Off: every bot drafts the same way.">
                    <input type="checkbox" checked={!!simCfg.personas} onChange={(e) => setSimCfg((c) => ({ ...c, personas: e.target.checked }))} className="accent-amber-400" data-testid="brain-personas" />
                    Bot personalities</label>
                  <button type="submit" className="px-4 py-2 rounded-lg bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-sm flex items-center gap-2" data-testid="brain-run">
                    <Play className="w-4 h-4" /> {base ? "New draft" : "Run draft"}</button>
                  {running && <button type="button" onClick={stop} className="px-3 py-2 rounded-lg border border-slate-700 text-sm text-slate-200 hover:text-rose-300 flex items-center gap-1.5" data-testid="brain-stop"><Square className="w-3.5 h-3.5" /> Stop</button>}
                  <p className="text-xs text-slate-500 basis-full sm:basis-auto sm:flex-1">Same seed, same draft: every pick that changes after you move a weight is the weights' doing. {local ? "The bots draft in this browser; picks appear as they're made." : "The bots draft on the server; this can take a while on staging."}</p>
                </form>
                {running && <p className="text-sm text-slate-300 flex items-center gap-2" data-testid="brain-running"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> {running} {sim && <span className="text-slate-500 tabular-nums">{sim.picks.length} of {sim.order.length} picks</span>}</p>}
                {sim ? (
                  <>
                    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 space-y-3" data-testid="brain-replay">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="flex items-center gap-1">
                          {[[ChevronsLeft, "First pick", () => goSlot(0)], [ChevronLeft, "Previous table pick", () => goSlot(viewSlot - 1)],
                            [ChevronRight, "Next table pick", () => goSlot(viewSlot + 1)], [ChevronsRight, "Last pick", () => goSlot(sim.picks.length - 1)]].map(([Icon, label, fn]) => (
                            <button key={label} type="button" onClick={fn} aria-label={label} title={label} className="p-1.5 rounded border border-slate-700 text-slate-300 hover:text-amber-300"><Icon className="w-4 h-4" /></button>
                          ))}
                        </div>
                        <span className="text-sm text-slate-300 tabular-nums">Table pick <span className="text-slate-100 font-semibold">{viewSlot + 1}</span> of {sim.order.length}
                          {viewPick && <> · Bot {viewPick.seat_index + 1} took <span className="text-slate-100">{shortName(byId[viewPick.card_id]?.name)}</span></>}
                          {viewPick && changed.has(viewSlot) && base?.picks[viewSlot] && <span className="text-sky-300"> (was {shortName(byId[base.picks[viewSlot].card_id]?.name)})</span>}</span>
                        <span className="text-xs text-slate-500 ml-auto tabular-nums">{sim.seconds != null && `${sim.seconds.toFixed(1)}s`}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                        <label className="flex items-center gap-2 cursor-pointer" title="Re-draft by itself a moment after you move a weight">
                          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} className="accent-amber-400" data-testid="brain-live" />
                          <Zap className="w-4 h-4 text-amber-400" /> Live: re-draft when a weight moves</label>
                        {!live && <button type="button" onClick={() => go()} disabled={!!running} className="px-3 py-1.5 rounded-lg bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-sm disabled:opacity-60" data-testid="brain-apply">Re-draft with these weights</button>}
                        <span className="flex items-center gap-2">New weights from table pick
                          <span className="tabular-nums text-slate-100 font-semibold">{from + 1}</span>
                          <button type="button" onClick={() => setFrom(viewSlot)} disabled={from === viewSlot} className="text-xs px-2 py-0.5 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-40" data-testid="brain-from-here">From this pick</button>
                          <button type="button" onClick={() => setFrom(0)} disabled={from === 0} className="text-xs px-2 py-0.5 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-40">From the start</button></span>
                        <span className="text-xs text-slate-400">{changedCount ? `${changedCount} weight${changedCount === 1 ? "" : "s"} changed in the panel below` : "Move a weight in the panel below to see the draft change"}</span>
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
                      {tunedRun && (
                        <p className="text-sm flex items-center gap-2 text-sky-300" data-testid="brain-diff"><GitCompare className="w-4 h-4" />
                          {changed.size ? `${changed.size} of ${sim.picks.length - sim.from} picks from pick ${sim.from + 1} differ from the current weights' draft (outlined in blue).` : "Same picks as with the current weights so far."}</p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <button type="button" onClick={() => setFullBoard((v) => !v)} data-testid="brain-full-board"
                        className="px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 flex items-center gap-1">
                        {fullBoard ? <><Minimize2 className="w-3 h-3" /> Scrolling board</> : <><Maximize2 className="w-3 h-3" /> Whole board (for screenshots)</>}</button>
                      <button type="button" disabled={!sim.seats} onClick={() => {
                        const x = draftExport({ src, sim, base, byId, changed, engineVersion });
                        const url = URL.createObjectURL(new Blob([JSON.stringify(x, null, 1)], { type: "application/json" }));
                        const a = document.createElement("a");
                        a.href = url; a.download = `bot-brain-seed-${x.settings.seed}.json`; a.click();
                        setTimeout(() => URL.revokeObjectURL(url), 2000);
                      }} data-testid="brain-export" title="Download this draft (settings, weights, every pick, seat summaries) to attach to a message"
                        className="px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-40 flex items-center gap-1"><Download className="w-3 h-3" /> Export draft</button>
                      <button type="button" disabled={!sim.seats} onClick={async () => {
                        const text = exportText(draftExport({ src, sim, base, byId, changed, engineVersion }));
                        try { await navigator.clipboard.writeText(text); setExported("Copied: paste it into a message."); }
                        catch { setExported(text); }
                        setTimeout(() => setExported(""), 6000);
                      }} data-testid="brain-copy-text" title="Copy every seat's picks as text to paste into a message"
                        className="px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-40 flex items-center gap-1"><ClipboardCopy className="w-3 h-3" /> Copy as text</button>
                      {exported && (exported.startsWith("Copied") ? <span className="text-emerald-400">{exported}</span>
                        : <textarea readOnly value={exported} onFocus={(e) => e.target.select()} className="basis-full h-32 bg-slate-900 border border-slate-700 rounded p-2 text-slate-200" />)}
                    </div>
                    <DraftBoard sim={sim} base={tunedRun ? base : null} byId={byId} seats={simSeatsUsed} viewSlot={viewSlot} changed={changed} kept={sim.from || 0} onPick={goSlot} full={fullBoard} />

                    {local && <LanesStrip lanes={lanes} personas={sim.personas} focusSeat={sim.order[viewSlot]} onSeat={(s) => {
                      const slot = sim.order.findIndex((x, i) => i >= viewSlot && x === s);
                      goSlot(slot >= 0 ? slot : viewSlot);
                    }} />}

                    {sim.seats ? (
                      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="brain-sim-seats">
                        {sim.seats.map((s) => (
                          <SeatSummary key={s.seat} s={s} before={tunedRun ? base.seats.find((x) => x.seat === s.seat) : null} name={`Bot ${s.seat + 1}`}
                            tuned={tunedRun && (!sim.tuned_seats || sim.tuned_seats.includes(s.seat))} />
                        ))}
                      </div>
                    ) : <p className="text-sm text-slate-500">Seat summaries appear when the draft finishes.</p>}

                    <BotLab inline fetchView={labFetch} cubeById={byId} seats={simSeatsUsed} startSeat={null} reloadKey={runs} onClose={() => {}}
                      focus={focus} onSlot={setViewSlot} onTuning={setLabTuning} onView={setLabView} busy={running ? "re-drafting…" : ""} />

                    {local && web && labView && <SeatWeb web={web} seatName={`Bot ${labView.seat + 1}`} scores={webScores} took={labView.took?.card} onPick={pick} />}
                  </>
                ) : !running && <p className="text-sm text-slate-500">Run a draft to step through the bots' picks.</p>}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
