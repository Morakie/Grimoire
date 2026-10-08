import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { CheckCircle2, AlertTriangle, Loader2, Info } from "lucide-react";

// Only the fields the check needs, so the request stays small.
const slim = (c) => ({
  id: c.id, name: c.name, type_line: c.type_line || "", oracle_text: c.oracle_text || "",
  color_identity: c.color_identity || [], quantity: c.quantity || 1,
});

/**
 * Legality + bracket estimate for a Commander deck. Re-checks a moment after the list stops changing.
 * Returns { result, loading, error }.
 */
export function useCommanderCheck(deck, enabled) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const seq = useRef(0);

  const key = enabled && deck
    ? JSON.stringify([deck.commander.map((c) => [c.name, c.quantity]), deck.mainboard.map((c) => [c.name, c.quantity])])
    : "";

  useEffect(() => {
    if (!key) { setResult(null); return undefined; }
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.post("/commander/check", {
          commander: deck.commander.map(slim),
          mainboard: deck.mainboard.map(slim),
        });
        if (mine === seq.current) { setResult(data); setError(false); }
      } catch {
        if (mine === seq.current) setError(true);
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { result, loading, error };
}

/** Small pill for the board toolbar: legal tick (or issue count) and the bracket estimate. */
export function CommanderBadge({ check, onClick }) {
  const { result, loading } = check;
  if (!result) {
    return loading ? <span className="text-[11px] text-slate-500 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Checking deck</span> : null;
  }
  const n = result.issues.length;
  return (
    <button type="button" data-testid="commander-badge" onClick={onClick}
      className="flex items-center gap-2 h-8 px-2.5 rounded-md bg-slate-900 border border-slate-700 text-xs text-slate-200 hover:bg-slate-800">
      {n === 0
        ? <span className="flex items-center gap-1 text-green-400"><CheckCircle2 className="w-3.5 h-3.5" /> Legal</span>
        : <span className="flex items-center gap-1 text-amber-400"><AlertTriangle className="w-3.5 h-3.5" /> {n} issue{n === 1 ? "" : "s"}</span>}
      <span className="w-px h-4 bg-slate-700" />
      <span>Bracket <span className="font-semibold text-amber-300">{result.bracket.label}</span></span>
      {loading && <Loader2 className="w-3 h-3 animate-spin text-slate-500" />}
    </button>
  );
}

function CardList({ names }) {
  if (!names || !names.length) return null;
  return <div className="mt-1 text-[11px] text-slate-400 leading-relaxed">{names.join(" · ")}</div>;
}

function Row({ label, names, empty = "None" }) {
  return (
    <div className="px-3 py-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300">{label}</span>
        <span className="text-amber-400 font-semibold tabular-nums">{names.length || empty}</span>
      </div>
      <CardList names={names} />
    </div>
  );
}

/** Full panel for the analytics sidebar / sheet. */
export default function CommanderCheck({ check }) {
  const { result, loading, error } = check;
  if (!result) {
    return (
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-500 flex items-center gap-2" data-testid="commander-check">
        {error ? "Couldn't check the deck right now." : <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Checking deck…</>}
      </div>
    );
  }
  const { issues, bracket } = result;
  return (
    <div className="space-y-5" data-testid="commander-check">
      <div>
        <h4 className="text-xs uppercase tracking-wide text-slate-400 mb-2 font-semibold flex items-center gap-2">
          Commander Legality {loading && <Loader2 className="w-3 h-3 animate-spin" />}
        </h4>
        <div className="bg-slate-950 border border-slate-800 rounded-lg divide-y divide-slate-800/60">
          {issues.length === 0 ? (
            <div className="p-3 text-sm text-green-400 flex items-center gap-2" data-testid="commander-legal">
              <CheckCircle2 className="w-4 h-4" /> Legal Commander deck
            </div>
          ) : issues.map((i, idx) => (
            <div key={idx} className="px-3 py-2" data-testid={`commander-issue-${i.kind}`}>
              <div className="text-xs text-amber-300 flex gap-2"><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {i.text}</div>
              <CardList names={i.cards} />
            </div>
          ))}
        </div>
      </div>

      <div>
        <h4 className="text-xs uppercase tracking-wide text-slate-400 mb-2 font-semibold">Bracket Estimate</h4>
        <div className="bg-slate-950 border border-slate-800 rounded-lg">
          <div className="p-3 flex items-baseline gap-3 border-b border-slate-800/60" data-testid="bracket-estimate">
            <span className="text-3xl font-display font-bold text-amber-400">{bracket.label}</span>
            <span className="text-sm text-slate-200">{bracket.name}</span>
          </div>
          <div className="px-3 py-2 text-[11px] text-slate-400">{bracket.reasons.join("; ")}.</div>
          <div className="divide-y divide-slate-800/60 border-t border-slate-800/60">
            <Row label="Game Changers" names={result.game_changers} />
            <Row label="Two-card combos" names={result.combos.map((c) => c.join(" + "))} />
            <Row label="Mass land denial" names={result.mass_land_denial} />
            <Row label="Extra turns" names={result.extra_turns} />
            <Row label="Tutors" names={result.tutors} />
          </div>
          <div className="px-3 py-2 border-t border-slate-800/60 text-[11px] text-slate-500 flex gap-1.5">
            <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
            <span>
              {bracket.complete ? "" : "Some lookups failed, so this may be incomplete. "}
              An estimate from the card list. Bracket 5 (cEDH) and how fast your combos win depend on how the deck is built and played, so talk it over before the game.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
