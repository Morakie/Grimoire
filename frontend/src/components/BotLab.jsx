import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, X, FlaskConical, ChevronLeft, ChevronRight, RotateCcw, Copy, ArrowUp, ArrowDown, User, SlidersHorizontal } from "lucide-react";

// Bot Lab: one pick of a rotisserie table as the bots' engine sees it, with every card's score split into
// its parts, plus sliders to try other weights. Data from POST /drafts/{id}/bot-lab. Tried weights only
// change this view (they are kept in this browser), never the live bots.

// Parts that add up to a card's score, in bar order. The total is then multiplied by colour fit and contention.
const PARTS = [
  ["rating", "Rating", "Card quality (CubeCobra Elo), after deck-type, support and saturation cuts", "#cbd5e1"],
  ["partners", "Drafted together", "How often real drafters put it with cards the bot owns", "#38bdf8"],
  ["plan", "Deck plan", "Fills a plan or package the bot has started, or a lane it's fighting for", "#fbbf24"],
  ["combo", "Combo", "Pieces of combo lines the bot is building", "#e879f9"],
  ["needs", "Deck needs", "Late-draft needs: interaction, creatures, cheap spells", "#34d399"],
  ["other", "Fixing / threats", "Dual lands, colour-pair style, a win condition", "#fb923c"],
  ["hate", "Sideboard", "Answers to a deck another seat is building (late only)", "#fb7185"],
];
const MULTS = [
  ["colour", "Colour fit", "Off-colour cards keep only part of their value"],
  ["contested", "Contention", "Below 1: likely to come back, so worth less now"],
  ["deck", "Deck type", "Narrow or key card outside the bot's deck type (inside Rating)"],
  ["saturated", "Saturated", "The bot already has enough cards doing this job (inside Rating)"],
];
const DECK_NAMES = { tolarian: "Tolarian", workshop: "Workshop", artifacts: "Artifacts", storm: "Storm", reanimator: "Reanimator", cheat: "Cheat", lands: "Lands", aggro: "Aggro" };
const PIP = { W: "bg-amber-50", U: "bg-blue-500", B: "bg-purple-500", R: "bg-red-500", G: "bg-green-500" };
const STORE = "grim_botlab_tuning";

function loadTuning() { try { return JSON.parse(localStorage.getItem(STORE) || "{}") || {}; } catch { return {}; } }
function saveTuning(t) { try { localStorage.setItem(STORE, JSON.stringify(t)); } catch { /* blocked */ } }
function ordinal(n) { const t = n % 100; return n + (t >= 11 && t <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th")); }
const fmt = (v, step) => (step >= 1 ? String(Math.round(v)) : v.toFixed(2));

function Pips({ colours }) {
  return <span className="inline-flex gap-0.5">{[...colours].map((c) => <span key={c} className={`w-2.5 h-2.5 rounded-full border border-white/20 ${PIP[c]}`} />)}</span>;
}

function ScoreBar({ parts, max }) {
  const mult = (parts.colour ?? 1) * (parts.contested ?? 1);
  return (
    <div className="h-3 rounded bg-slate-800 overflow-hidden flex" aria-hidden="true">
      {PARTS.map(([k, , , col]) => {
        const v = Math.max(0, (parts[k] || 0) * mult);
        return v > 0 ? <span key={k} style={{ width: `${(v / max) * 100}%`, background: col }} /> : null;
      })}
    </div>
  );
}

function Breakdown({ row }) {
  const p = row.parts || {};
  const mult = (p.colour ?? 1) * (p.contested ?? 1);
  const sum = PARTS.reduce((s, [k]) => s + (p[k] || 0), 0);
  return (
    <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-xs pt-2 pb-1">
      <div className="space-y-1">
        {PARTS.map(([k, label, help, col]) => (
          <div key={k} className="flex items-center gap-2" title={help}>
            <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: col }} />
            <span className="text-slate-300 flex-1">{label}</span>
            <span className={`tabular-nums ${Math.abs(p[k] || 0) < 0.005 ? "text-slate-600" : "text-slate-100"}`}>{(p[k] || 0).toFixed(3)}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 border-t border-slate-800 pt-1"><span className="w-2" /><span className="text-slate-400 flex-1">Sum</span><span className="tabular-nums text-slate-100">{sum.toFixed(3)}</span></div>
      </div>
      <div className="space-y-1">
        {MULTS.map(([k, label, help]) => (
          <div key={k} className="flex items-center gap-2" title={help}>
            <span className="text-slate-300 flex-1">{label} ×</span>
            <span className={`tabular-nums ${p[k] == null || p[k] >= 0.995 ? "text-slate-600" : "text-amber-300"}`}>{p[k] == null ? "1.00" : p[k].toFixed(2)}</span>
          </div>
        ))}
        {p.risk != null && <div className="flex items-center gap-2" title="Chance another seat takes it before this seat picks again"><span className="text-slate-300 flex-1">Taken before next turn</span><span className="tabular-nums text-slate-100">{Math.round(p.risk * 100)}%</span></div>}
        <div className="flex items-center gap-2 border-t border-slate-800 pt-1"><span className="text-slate-400 flex-1">Score = sum × {mult.toFixed(2)}</span><span className="tabular-nums text-amber-300 font-semibold">{row.score.toFixed(3)}</span></div>
      </div>
    </div>
  );
}

function Move({ row, tuned }) {
  if (!tuned) return null;
  if (row.base_rank == null || row.base_rank === row.rank) return <span className="w-9" />;
  const up = row.base_rank > row.rank;
  return (
    <span className={`w-9 text-[11px] tabular-nums flex items-center gap-0.5 ${up ? "text-emerald-400" : "text-rose-400"}`} title={`Was #${row.base_rank} with the current weights`}>
      {up ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}{Math.abs(row.base_rank - row.rank)}
    </span>
  );
}

function CardRow({ row, card, max, tuned, open, onToggle, took }) {
  const img = card && (card.art_crop || card.image);
  return (
    <li className={`rounded-lg border ${took ? "border-amber-400/50 bg-amber-400/5" : "border-slate-800 bg-slate-900/40"}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} data-testid={`bot-lab-row-${row.rank}`}
        className="w-full text-left px-2.5 py-2 flex items-center gap-2.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400 rounded-lg">
        <span className="w-6 text-right text-xs tabular-nums text-slate-500">#{row.rank}</span>
        <Move row={row} tuned={tuned} />
        <span className="w-10 h-7 rounded overflow-hidden bg-slate-800 shrink-0">{img && <img src={img} alt="" loading="lazy" className="w-full h-full object-cover" />}</span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm text-slate-100 truncate">{took && <User className="w-3.5 h-3.5 text-amber-400 shrink-0" />}{row.name}</span>
          <ScoreBar parts={row.parts || {}} max={max} />
        </span>
        <span className="w-12 text-right text-sm tabular-nums text-slate-200">{row.score.toFixed(2)}</span>
      </button>
      {open && <div className="px-3 pb-2"><Breakdown row={row} /></div>}
    </li>
  );
}

function Knob({ k, value, onChange }) {
  const changed = Math.abs(value - k.default) > 1e-9;
  const pos = ((k.default - k.min) / (k.max - k.min)) * 100;
  return (
    <label className="block" title={k.help}>
      <span className="flex items-baseline justify-between gap-2 text-xs">
        <span className={changed ? "text-amber-300" : "text-slate-300"}>{k.label}</span>
        <span className="tabular-nums text-slate-400">{fmt(value, k.step)}{changed && <span className="text-slate-600"> / {fmt(k.default, k.step)}</span>}</span>
      </span>
      <span className="relative block mt-1">
        <input id={`knob-${k.key}`} type="range" min={k.min} max={k.max} step={k.step} value={value}
          onChange={(e) => onChange(k.key, Number(e.target.value))} className="w-full accent-amber-400" data-testid={`bot-lab-knob-${k.key}`} />
        <span className="absolute -bottom-0.5 w-px h-1.5 bg-slate-500 pointer-events-none" style={{ left: `calc(${pos}% + ${(0.5 - pos / 100) * 14}px)` }} aria-hidden="true" />
      </span>
    </label>
  );
}

// `fetchView(body)` returns the POST response for {seat, pick_no, tuning} (a real table's /bot-lab, or a simulated
// draft's /lab/view). `inline` renders the panel in the page instead of as a pop-up; `reloadKey` forces a reload.
// `focus` ({seat, pickNo}) jumps to a pick from outside; `onSlot` hears which table pick is shown and
// `onTuning` the weights changed from the current ones (Bot Brain uses them to re-draft).
export default function BotLab({ fetchView, cubeById, seats, startSeat, onClose, inline = false, reloadKey = 0, focus = null, onSlot, onTuning }) {
  const [seat, setSeat] = useState(startSeat ?? seats[0]?.index ?? 0);
  const [pickNo, setPickNo] = useState(null);           // null = the seat's latest pick
  const [tuning, setTuning] = useState(loadTuning);
  const [data, setData] = useState(null);
  const [knobs, setKnobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);
  const [showKnobs, setShowKnobs] = useState(false);     // phones: weights panel folded
  const [copied, setCopied] = useState("");
  const req = useRef(0);

  const effective = useMemo(() => {
    const t = {};
    knobs.forEach((k) => { if (tuning[k.key] != null && Math.abs(tuning[k.key] - k.default) > 1e-9) t[k.key] = tuning[k.key]; });
    return t;
  }, [tuning, knobs]);
  const changedCount = Object.keys(effective).length;

  const load = useCallback((body) => {
    const id = ++req.current;
    setLoading(true); setError(null);
    fetchView(body)
      .then(({ data }) => { if (id !== req.current) return; setData(data); setKnobs(data.knobs || []); })
      .catch((e) => { if (id === req.current) setError(e.response?.data?.detail || "Couldn't load this pick. Try again in a moment."); })
      .finally(() => { if (id === req.current) setLoading(false); });
  }, [fetchView]);

  // Reload when the seat, pick or weights change (weights debounced while a slider is dragged).
  useEffect(() => {
    const t = setTimeout(() => load({ seat, pick_no: pickNo, tuning }), 220);
    return () => clearTimeout(t);
  }, [seat, pickNo, tuning, load, reloadKey]);
  useEffect(() => { if (startSeat != null) { setSeat(startSeat); setPickNo(null); } }, [startSeat, reloadKey]);
  useEffect(() => { if (focus) { setSeat(focus.seat); setPickNo(focus.pickNo); } }, [focus]);
  useEffect(() => { if (data && onSlot) onSlot(data.slot); }, [data, onSlot]);
  useEffect(() => { if (onTuning) onTuning(effective); }, [effective, onTuning]);
  useEffect(() => { saveTuning(tuning); }, [tuning]);
  useEffect(() => { setOpen(null); }, [seat, pickNo]);
  useEffect(() => {
    if (inline) return undefined;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, inline]);

  const slots = data?.seat_slots || [];
  const curNo = data?.pick_no ?? 1;
  const go = (n) => setPickNo(Math.min(Math.max(n, 1), slots.length || 1));
  const setKnob = (key, v) => setTuning((t) => ({ ...t, [key]: v }));
  const resetAll = () => setTuning({});
  const copy = async () => {
    const text = JSON.stringify(effective, null, 1);
    try { await navigator.clipboard.writeText(text); setCopied("Copied"); }
    catch { setCopied(text); }
    setTimeout(() => setCopied(""), 4000);
  };

  const rows = data?.rows || [];
  const took = data?.took;
  const tookInList = took && rows.some((r) => r.card === took.card);
  const max = Math.max(0.01, ...rows.map((r) => r.score), took ? took.score : 0);
  const tuned = changedCount > 0;
  const seatName = (i) => seats.find((s) => s.index === i)?.player_name || `Seat ${i + 1}`;
  const info = data?.seat_info;
  const groups = useMemo(() => knobs.reduce((m, k) => { (m[k.group] = m[k.group] || []).push(k); return m; }, {}), [knobs]);

  return (
    <div className={inline ? "" : "fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-2 sm:p-4 sm:pt-10"} data-testid="bot-lab" onClick={inline ? undefined : onClose}>
      <div className={`${inline ? "w-full lg:h-[80vh]" : "w-[min(99vw,1240px)] max-h-[94vh] shadow-2xl"} bg-[#0b111e] border border-slate-700 rounded-xl overflow-hidden flex flex-col`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-slate-800 shrink-0">
          <span className="font-display font-semibold flex items-center gap-2"><FlaskConical className="w-4 h-4 text-amber-400" /> Bot Lab</span>
          <span className="text-xs text-slate-500 hidden md:flex items-center gap-3">How the bots score each card at one pick. Weights you change here only affect this view.{!inline && <a href="/bots" className="text-amber-300 hover:underline whitespace-nowrap">Bot Brain</a>}</span>
          {inline ? <span /> : <button type="button" data-testid="bot-lab-close" onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>}
        </div>

        {/* Seat and pick */}
        <div className="px-4 py-3 border-b border-slate-800 flex flex-wrap items-center gap-x-4 gap-y-2 shrink-0">
          <label className="flex items-center gap-2 text-sm">
            <span className="text-[11px] uppercase tracking-wider text-slate-500">Seat</span>
            <select id="bot-lab-seat" value={seat} onChange={(e) => { setSeat(Number(e.target.value)); setPickNo(null); }} data-testid="bot-lab-seat"
              className="bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-slate-100">
              {seats.map((s) => <option key={s.index} value={s.index}>{s.index + 1}. {s.player_name || `Seat ${s.index + 1}`}</option>)}
            </select>
          </label>
          <div className="flex items-center gap-2 flex-1 min-w-[260px]">
            <button type="button" onClick={() => go(curNo - 1)} disabled={curNo <= 1} className="p-1 rounded border border-slate-700 text-slate-300 disabled:opacity-30" aria-label="Previous pick" data-testid="bot-lab-prev"><ChevronLeft className="w-4 h-4" /></button>
            <input id="bot-lab-pick" type="range" min={1} max={Math.max(1, slots.length)} value={curNo} onChange={(e) => go(Number(e.target.value))} className="flex-1 accent-amber-400" aria-label="Pick number" data-testid="bot-lab-pick" />
            <button type="button" onClick={() => go(curNo + 1)} disabled={curNo >= slots.length} className="p-1 rounded border border-slate-700 text-slate-300 disabled:opacity-30" aria-label="Next pick" data-testid="bot-lab-next"><ChevronRight className="w-4 h-4" /></button>
            <span className="text-sm text-slate-300 tabular-nums whitespace-nowrap">{ordinal(curNo)} pick{data && <span className="text-slate-500 hidden sm:inline"> · table pick {data.slot + 1}</span>}</span>
          </div>
          {loading && <Loader2 className="w-4 h-4 animate-spin text-amber-400" aria-label="Loading" />}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid lg:grid-cols-[minmax(0,1fr)_330px]">
          {/* Ranking */}
          <div className="lg:overflow-y-auto p-4 space-y-4 min-w-0">
            {error && <p className="text-sm text-red-300">{error}</p>}
            {!data && !error && <p className="text-sm text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> Rebuilding the table at that pick…</p>}
            {data && (
              <>
                <section className="flex flex-wrap gap-x-6 gap-y-2 text-sm" data-testid="bot-lab-seat-info">
                  <div><div className="text-[11px] uppercase tracking-wider text-slate-500">Colours</div>
                    <div className="flex items-center gap-2 mt-0.5 text-slate-200">{info.pair ? <><Pips colours={info.pair} />{info.splash && <><span className="text-slate-500">+</span><Pips colours={info.splash} /></>}</> : <span className="text-slate-400">Still open</span>}
                      <span className="text-slate-500 text-xs">{info.coloured_spells} coloured spells · {Math.round(info.commit * 100)}% committed</span></div></div>
                  <div className="min-w-0"><div className="text-[11px] uppercase tracking-wider text-slate-500">Deck types</div>
                    <div className="flex flex-wrap gap-1.5 mt-0.5">{Object.keys(info.decks).length ? Object.entries(info.decks).slice(0, 4).map(([t, v]) => (
                      <span key={t} className={`text-xs px-2 py-0.5 rounded-full border ${v >= 0.5 ? "border-amber-400/60 text-amber-200" : "border-slate-700 text-slate-400"}`}>{DECK_NAMES[t] || t} {Math.round(v * 100)}%</span>
                    )) : <span className="text-slate-400">None yet</span>}</div></div>
                  <div className="min-w-0 basis-full sm:basis-auto sm:flex-1"><div className="text-[11px] uppercase tracking-wider text-slate-500">{seatName(data.seat)} owns ({info.owned.length})</div>
                    <div className="flex gap-1 mt-1 overflow-x-auto pb-1">{info.owned.map((cid) => { const c = cubeById[cid]; const img = c && (c.art_crop || c.image); return (
                      <span key={cid} title={c?.name} className="w-9 h-6 rounded overflow-hidden bg-slate-800 shrink-0 text-[8px] text-slate-400 leading-none flex items-center justify-center">{img ? <img src={img} alt={c.name} loading="lazy" className="w-full h-full object-cover" /> : (c?.name || "?").slice(0, 8)}</span>); })}</div></div>
                </section>

                {took && (
                  <p className="text-sm text-slate-300">
                    <User className="inline w-3.5 h-3.5 text-amber-400 mr-1 -mt-0.5" />{seatName(data.seat)} took <span className="text-slate-100 font-medium">{took.name}</span>, the bot's <span className="text-amber-300 font-semibold tabular-nums">#{took.rank}</span> of {data.of}
                    {tuned && took.base_rank !== took.rank && <span className="text-slate-500"> (#{took.base_rank} with the current weights)</span>}.
                  </p>
                )}
                {data.next_pick && <p className="text-sm text-slate-400">This pick hasn't been made yet: the list is what a bot in this seat would take now.</p>}

                <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-400" aria-label="Score parts">
                  {PARTS.map(([k, label, help, col]) => <span key={k} title={help} className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: col }} />{label}</span>)}
                  <span className="text-slate-500">· bar length = final score (parts × colour fit × contention) · tap a card for numbers</span>
                </div>

                <ol className="space-y-1.5" data-testid="bot-lab-rows">
                  {rows.map((r) => <CardRow key={r.card} row={r} card={cubeById[r.card]} max={max} tuned={tuned} took={took && r.card === took.card}
                    open={open === r.card} onToggle={() => setOpen(open === r.card ? null : r.card)} />)}
                </ol>
                {took && !tookInList && (
                  <>
                    <p className="text-[11px] uppercase tracking-wider text-slate-500 pt-1">The card actually taken</p>
                    <ol><CardRow row={took} card={cubeById[took.card]} max={max} tuned={tuned} took open={open === took.card} onToggle={() => setOpen(open === took.card ? null : took.card)} /></ol>
                  </>
                )}
              </>
            )}
          </div>

          {/* Weights */}
          <aside className="border-t lg:border-t-0 lg:border-l border-slate-800 lg:overflow-y-auto p-4 space-y-4 min-w-0" data-testid="bot-lab-weights">
            <div className="flex items-center justify-between gap-2">
              <button type="button" onClick={() => setShowKnobs((v) => !v)} className="lg:pointer-events-none font-display font-semibold text-sm flex items-center gap-2" aria-expanded={showKnobs}>
                <SlidersHorizontal className="w-4 h-4 text-amber-400" /> Weights {changedCount > 0 && <span className="text-xs font-normal px-1.5 rounded-full bg-amber-400 text-stone-900 whitespace-nowrap">{changedCount} changed</span>}
              </button>
              <div className="flex gap-1.5">
                <button type="button" onClick={copy} disabled={!changedCount} className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-30 flex items-center gap-1" data-testid="bot-lab-copy"><Copy className="w-3 h-3" /> Copy</button>
                <button type="button" onClick={resetAll} disabled={!changedCount} className="text-xs px-2 py-1 rounded border border-slate-700 text-slate-300 hover:text-amber-300 disabled:opacity-30 flex items-center gap-1" data-testid="bot-lab-reset"><RotateCcw className="w-3 h-3" /> Reset</button>
              </div>
            </div>
            {copied && (copied === "Copied"
              ? <p className="text-xs text-emerald-400">Copied. Paste it into a message to change the bots for real.</p>
              : <textarea readOnly value={copied} onFocus={(e) => e.target.select()} className="w-full h-24 text-xs bg-slate-900 border border-slate-700 rounded p-2 text-slate-200" />)}
            <p className="text-xs text-slate-500">Arrows on each card show how far it moved compared with the current weights. The tick under a slider marks the current value.</p>
            <div className={`${showKnobs ? "block" : "hidden"} lg:block space-y-5`}>
              {Object.entries(groups).map(([g, ks]) => (
                <fieldset key={g} className="space-y-3">
                  <legend className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">{g}</legend>
                  {ks.map((k) => <Knob key={k.key} k={k} value={tuning[k.key] ?? k.default} onChange={setKnob} />)}
                </fieldset>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
