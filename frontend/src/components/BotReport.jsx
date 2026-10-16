import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, X, Bot, User, ArrowRight } from "lucide-react";

// Bot report: how the bots' engine ranks each player's real pick (rotisserie cube tables).
// Data from GET /drafts/{id}/bot-report; card details come from the draft's own cube.

const PART_LABELS = [
  ["rating", "Rating"], ["plan", "Plan / package"], ["combo", "Combo"], ["partners", "Drafted-with"],
  ["needs", "Deck needs"], ["hate", "Sideboard answer"], ["other", "Other"], ["colour", "Colour fit ×"], ["contested", "Contention ×"],
];

function Stat({ label, value, hint }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 min-w-[6.5rem]" title={hint}>
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="font-display text-lg font-semibold text-slate-100 tabular-nums">{value}</div>
    </div>
  );
}

function pct(v) { return v == null ? "–" : `${v}%`; }
function ordinal(n) { const t = n % 100; return n + (t >= 11 && t <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th")); }

function StatsRow({ name, s }) {
  return (
    <tr className="border-t border-slate-800">
      <td className="py-1.5 pr-3 text-slate-200">{name}</td>
      <td className="py-1.5 px-2 text-right tabular-nums text-slate-400">{s.picks || 0}</td>
      <td className="py-1.5 px-2 text-right tabular-nums text-slate-200">{s.picks ? s.median_rank : "–"}</td>
      <td className="py-1.5 px-2 text-right tabular-nums">{pct(s.top1)}</td>
      <td className="py-1.5 px-2 text-right tabular-nums text-amber-300">{pct(s.top3)}</td>
      <td className="py-1.5 px-2 text-right tabular-nums">{pct(s.top10)}</td>
      <td className="py-1.5 pl-2 text-right tabular-nums text-slate-400">{pct(s.outside_top20)}</td>
    </tr>
  );
}

function StatsTable({ rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[480px]">
        <thead>
          <tr className="text-[11px] uppercase tracking-wider text-slate-500">
            <th className="text-left font-semibold pb-1.5"> </th>
            <th className="text-right font-semibold pb-1.5 px-2">Picks</th>
            <th className="text-right font-semibold pb-1.5 px-2" title="Middle rank of the player's pick in the bot's list">Median rank</th>
            <th className="text-right font-semibold pb-1.5 px-2">Bot #1</th>
            <th className="text-right font-semibold pb-1.5 px-2">Top 3</th>
            <th className="text-right font-semibold pb-1.5 px-2">Top 10</th>
            <th className="text-right font-semibold pb-1.5 pl-2">Past 20</th>
          </tr>
        </thead>
        <tbody>{rows.map(([name, s]) => <StatsRow key={name} name={name} s={s} />)}</tbody>
      </table>
    </div>
  );
}

function Parts({ parts }) {
  if (!parts) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1.5">
      {PART_LABELS.filter(([k]) => parts[k] != null && (k === "colour" || k === "contested" ? parts[k] < 0.99 : Math.abs(parts[k]) >= 0.01)).map(([k, label]) => (
        <span key={k} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 tabular-nums">{label} {parts[k].toFixed(2)}</span>
      ))}
    </div>
  );
}

function CardTile({ card, caption, parts, icon: Icon, accent }) {
  return (
    <figure className="w-36 shrink-0">
      <div className={`rounded-lg overflow-hidden border ${accent ? "border-amber-400/60" : "border-slate-700"} bg-slate-900 aspect-[0.716] flex items-center justify-center`}>
        {card && (card.image || card.art_crop)
          ? <img src={card.image || card.art_crop} alt={card.name} className="w-full h-full object-cover" loading="lazy" />
          : <span className="text-xs text-slate-300 p-2 text-center">{card?.name || "Unknown card"}</span>}
      </div>
      <figcaption className="mt-1 text-xs text-slate-300 flex items-center gap-1"><Icon className="w-3 h-3 shrink-0 text-slate-500" /> {caption}</figcaption>
      <Parts parts={parts} />
    </figure>
  );
}

export default function BotReport({ shareId, cubeById, seats, pickCount, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setData(null); setError(null);
    api.get(`/drafts/${shareId}/bot-report`, { timeout: 120000 })
      .then(({ data }) => { if (alive) setData(data); })
      .catch((e) => { if (alive) setError(e.response?.data?.detail || "Couldn't build the report. Try again in a moment."); });
    return () => { alive = false; };
  }, [shareId, pickCount]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const seatName = (i) => seats.find((s) => s.index === i)?.player_name || `Seat ${i + 1}`;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-start justify-center p-4 pt-10 sm:pt-16" data-testid="bot-report" onClick={onClose}>
      <div className="w-[min(98vw,1100px)] max-h-[88vh] bg-[#0b111e] border border-slate-700 rounded-xl shadow-2xl overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
          <span className="font-display font-semibold flex items-center gap-2"><Bot className="w-4 h-4 text-amber-400" /> Bot report</span>
          <button type="button" data-testid="bot-report-close" onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <div className="overflow-y-auto p-4 space-y-6">
          <p className="text-sm text-slate-400 max-w-3xl">
            For each pick, where the player's card ranked in the bots' list at that moment, using the current engine.
            Each seat's first {data?.skip_first ?? 5} picks are left out, before any lane or plan exists.
          </p>
          {error ? (
            <p className="text-sm text-red-300">{error}</p>
          ) : !data ? (
            <p className="text-sm text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin text-amber-400" /> Replaying the draft… (a full table takes a few seconds)</p>
          ) : (
            <>
              <section className="flex flex-wrap gap-2" data-testid="bot-report-summary">
                <Stat label="Picks compared" value={data.overall.picks} />
                <Stat label="Median rank" value={data.overall.picks ? data.overall.median_rank : "–"} hint="Middle rank of the player's pick in the bot's list" />
                <Stat label="Bot's #1" value={pct(data.overall.top1)} />
                <Stat label="Top 3" value={pct(data.overall.top3)} />
                <Stat label="Top 5" value={pct(data.overall.top5)} />
                <Stat label="Top 10" value={pct(data.overall.top10)} />
                <Stat label="Past 20" value={pct(data.overall.outside_top20)} hint="The bot ranked the player's pick lower than 20th" />
              </section>

              <section>
                <h3 className="font-display font-semibold mb-2">By draft phase</h3>
                <StatsTable rows={[["Early", data.by_phase.early], ["Middle", data.by_phase.middle], ["Late", data.by_phase.late]]} />
              </section>

              <section>
                <h3 className="font-display font-semibold mb-2">By seat</h3>
                <StatsTable rows={Object.entries(data.by_seat).map(([i, s]) => [`${Number(i) + 1}. ${s.name}`, s])} />
              </section>

              <section>
                <h3 className="font-display font-semibold mb-1">Biggest disagreements</h3>
                <p className="text-xs text-slate-500 mb-3">Picks the bot ranked far down, or where it strongly preferred another card. Numbers under each card are the parts of the bot's score.</p>
                <ol className="space-y-4" data-testid="bot-report-disagreements">
                  {data.disagreements.map((d) => {
                    const took = cubeById[d.card];
                    const bot = d.bot_top[0];
                    return (
                      <li key={d.order} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                        <div className="text-sm text-slate-300 mb-2">
                          <span className="text-slate-500 tabular-nums">Pick {d.order + 1}</span> · <span className="text-slate-100">{seatName(d.seat)}</span>'s {ordinal(d.pick_no)} pick ·
                          {" "}bot ranked it <span className="text-amber-300 font-semibold tabular-nums">#{d.rank}</span> of {d.of}
                        </div>
                        <div className="flex items-start gap-3 overflow-x-auto pb-1">
                          <CardTile card={took} caption={`Took · #${d.rank}`} parts={d.card_parts} icon={User} />
                          <ArrowRight className="w-5 h-5 text-slate-600 mt-24 shrink-0" aria-hidden="true" />
                          {d.bot_top.map((b, i) => (
                            <CardTile key={b.card} card={cubeById[b.card]} caption={`Bot #${i + 1} · ${b.score.toFixed(2)}`} parts={b.parts} icon={Bot} accent={i === 0} />
                          ))}
                        </div>
                        {bot && <div className="text-[11px] text-slate-500 mt-1">Score gap to the bot's #1: <span className="tabular-nums">{d.gap.toFixed(2)}</span></div>}
                      </li>
                    );
                  })}
                </ol>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
