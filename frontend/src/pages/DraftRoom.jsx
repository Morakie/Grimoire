import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ManaCost } from "@/components/ManaCost";
import { buildExport } from "@/components/ExportDialog";
import { Sparkles, Loader2, Copy, Check } from "lucide-react";
import { toast } from "sonner";

const GUEST_KEY = "grimoire_guest_deck";

function storeKey(sid) { return `grim_draft_${sid}`; }

export default function DraftRoom() {
  const { shareId } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(null);
  const [state, setState] = useState(null);
  const [me, setMe] = useState(() => { try { return JSON.parse(localStorage.getItem(storeKey(shareId))) || null; } catch { return null; } });
  const [claimName, setClaimName] = useState("");
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);

  // initial full load (includes cube)
  useEffect(() => {
    api.get(`/drafts/${shareId}`).then(({ data }) => setDraft(data)).catch(() => { toast.error("Draft not found"); navigate("/draft"); });
  }, [shareId, navigate]);

  // poll light state
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try { const { data } = await api.get(`/drafts/${shareId}/state`); if (active) setState(data); } catch {}
    };
    tick();
    const iv = setInterval(tick, 2000);
    return () => { active = false; clearInterval(iv); };
  }, [shareId]);

  const pickedIds = useMemo(() => new Set((state?.picked_ids) || (state?.picks || []).map((p) => p.card_id)), [state]);
  const cubeById = useMemo(() => { const m = {}; (draft?.cube || []).forEach((c) => (m[c.id] = c)); return m; }, [draft]);

  if (!draft || !state) return <div className="h-screen flex items-center justify-center bg-[#060a14]"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>;

  const claim = async () => {
    if (!claimName.trim()) { toast.error("Enter your name"); return; }
    try {
      const { data } = await api.post(`/drafts/${shareId}/claim`, { name: claimName.trim(), player_token: me?.player_token });
      localStorage.setItem(storeKey(shareId), JSON.stringify(data));
      setMe(data);
      toast.success(`Claimed seat(s): ${data.seats.map((s) => s + 1).join(", ")}`);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not claim"); }
  };

  const start = async () => {
    try { const { data } = await api.post(`/drafts/${shareId}/start`); setDraft((d) => ({ ...d, ...data })); toast.success("Draft started"); }
    catch (e) { toast.error(e.response?.data?.detail || "Cannot start"); }
  };

  const pick = async (card) => {
    if (!me) { toast.error("Claim a seat first"); return; }
    const seat = state.current_seat_index;
    if (!me.seats.includes(seat)) { toast.error("Not your turn"); return; }
    setPicking(true);
    try {
      const { data } = await api.post(`/drafts/${shareId}/pick`, { player_token: me.player_token, seat_index: seat, card_id: card.id });
      setState(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Pick failed"); }
    finally { setPicking(false); }
  };

  const seatPicks = (seatIdx) => (state.picks || []).filter((p) => p.seat_index === seatIdx).map((p) => cubeById[p.card_id]).filter(Boolean);
  const deckForSeat = (seatIdx) => {
    const cards = seatPicks(seatIdx);
    const merged = [];
    cards.forEach((c) => { const e = merged.find((x) => x.name === c.name); if (e) e.quantity++; else merged.push({ ...c, quantity: 1 }); });
    const seat = state.seats.find((s) => s.index === seatIdx);
    return { name: `${state.name} — ${seat?.player_name || "Seat"} (Seat ${seatIdx + 1})`, format: "kitchen", description: `Drafted from ${state.name}`, mainboard: merged, sideboard: [], commander: [] };
  };

  const editInBuilder = (seatIdx) => {
    const deck = { id: null, share_id: null, ...deckForSeat(seatIdx) };
    localStorage.setItem(GUEST_KEY, JSON.stringify(deck));
    navigate("/build");
  };
  const exportSeat = (seatIdx) => {
    navigator.clipboard.writeText(buildExport(deckForSeat(seatIdx)));
    toast.success("Deck copied to clipboard");
  };

  const shareUrl = `${window.location.origin}/draft/${shareId}`;
  const myTurn = me && state.current_seat_index != null && me.seats.includes(state.current_seat_index);
  const available = (draft.cube || []).filter((c) => !pickedIds.has(c.id) && (!query.trim() || c.name.toLowerCase().includes(query.toLowerCase())));
  const currentSeatName = state.current_seat_index != null ? state.seats.find((s) => s.index === state.current_seat_index)?.player_name : null;

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100 grim-grain">
      <header className="border-b border-slate-800 bg-[#070c17]">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-3 flex-wrap">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <span className="text-slate-500">/</span>
          <span className="font-display font-semibold truncate">{state.name}</span>
          <span className="text-xs px-2 py-0.5 rounded-full border border-slate-700 text-slate-300 capitalize">{state.status}</span>
          <div className="ml-auto flex items-center gap-2">
            <Input readOnly value={shareUrl} className="w-56 h-8 bg-slate-950 border-slate-700 text-slate-300 text-xs hidden sm:block" data-testid="draft-share-url" />
            <Button size="sm" variant="outline" data-testid="draft-copy-link" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Link copied"); }} className="bg-slate-900 border-slate-700 text-slate-200"><Copy className="w-4 h-4" /></Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Seats / lobby */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="seat-grid">
          {state.seats.map((s) => {
            const isCurrent = state.current_seat_index === s.index;
            const mine = me?.seats?.includes(s.index);
            return (
              <div key={s.index} data-testid={`seat-${s.index}`} className={`rounded-xl border p-3 ${isCurrent ? "border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.15)]" : "border-slate-800"} bg-slate-900/50`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Seat {s.index + 1}{mine ? " · you" : ""}</span>
                  <span className="text-xs text-amber-400 tabular-nums">{seatPicks(s.index).length}/{state.pick_cap}</span>
                </div>
                <div className="font-display font-semibold truncate">{s.player_name || <span className="text-slate-600">unclaimed</span>}</div>
                {isCurrent && <div className="text-[11px] text-amber-400 mt-1">On the clock</div>}
              </div>
            );
          })}
        </div>

        {state.status === "lobby" && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 max-w-md" data-testid="lobby-panel">
            <h2 className="font-display text-xl font-bold mb-2">Join the draft</h2>
            <p className="text-sm text-slate-400 mb-4">Enter your name to claim your seat(s). {state.seats_per_player} seat(s) each. {state.players.length}/{state.num_players} players in.</p>
            {!me ? (
              <div className="flex gap-2">
                <Input data-testid="claim-name" value={claimName} onChange={(e) => setClaimName(e.target.value)} placeholder="Your name" className="bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
                <Button data-testid="claim-submit" onClick={claim} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0">Claim seat</Button>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-green-400 text-sm"><Check className="w-4 h-4" /> You are <b>{me.name}</b> — seat(s) {me.seats.map((s) => s + 1).join(", ")}</div>
            )}
            <Button data-testid="start-draft" onClick={start} disabled={state.seats.some((s) => !s.player_name)} className="w-full mt-4 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold disabled:opacity-40">
              Start draft {state.seats.some((s) => !s.player_name) ? "(waiting for all seats)" : ""}
            </Button>
          </div>
        )}

        {state.status === "drafting" && (
          <div>
            <div className="mb-4 flex items-center gap-3 flex-wrap">
              <div className={`px-4 py-2 rounded-xl font-display font-semibold ${myTurn ? "bg-amber-400 text-stone-900" : "bg-slate-900 border border-slate-700 text-slate-200"}`} data-testid="turn-indicator">
                {myTurn ? "Your pick!" : `${currentSeatName || "…"}'s pick`} · {state.pick_index}/{state.order_len}
              </div>
              <Input data-testid="cube-filter" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter available cards..." className="w-64 h-9 bg-slate-950 border-slate-700 text-slate-100" />
              <span className="text-xs text-slate-500">{available.length} available</span>
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-8 gap-3" data-testid="available-cards">
              {available.slice(0, 160).map((c) => (
                <button key={c.id} data-testid={`pool-card-${c.id}`} disabled={!myTurn || picking} onClick={() => pick(c)}
                  className="group relative rounded-lg overflow-hidden border border-slate-800 hover:border-amber-400/60 disabled:opacity-60 disabled:cursor-not-allowed transition-colors">
                  <div className="aspect-[0.716] bg-slate-800 flex items-center justify-center">
                    {(c.image || c.art_crop) ? <img src={c.image || c.art_crop} alt={c.name} loading="lazy" className="w-full h-full object-cover" /> : <div className="p-2 text-center text-xs font-medium text-slate-200 leading-tight">{c.name}</div>}
                  </div>
                  {myTurn && <div className="absolute inset-0 bg-amber-400/0 group-hover:bg-amber-400/15 transition-colors" />}
                </button>
              ))}
            </div>
          </div>
        )}

        {state.status === "complete" && (
          <div data-testid="draft-complete">
            <h2 className="font-display text-2xl font-bold mb-4">Draft complete 🎉</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {state.seats.map((s) => (
                <div key={s.index} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4" data-testid={`result-seat-${s.index}`}>
                  <div className="font-display font-semibold">{s.player_name} · Seat {s.index + 1}</div>
                  <div className="text-xs text-slate-500 mb-3">{seatPicks(s.index).length} cards</div>
                  <div className="flex gap-2">
                    <Button size="sm" data-testid={`export-seat-${s.index}`} variant="outline" onClick={() => exportSeat(s.index)} className="bg-slate-900 border-slate-700 text-slate-200">Export</Button>
                    <Button size="sm" data-testid={`edit-seat-${s.index}`} onClick={() => editInBuilder(s.index)} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Edit in builder</Button>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-4">Editing opens the deck in the builder. Sign in there to save your changes.</p>
          </div>
        )}
      </main>
    </div>
  );
}
