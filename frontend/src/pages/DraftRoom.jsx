import React, { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { buildExport } from "@/components/ExportDialog";
import { Sparkles, Loader2, Copy, Check, ListChecks, MessageSquare, X, LayoutGrid, Table2, Eye } from "lucide-react";
import { toast } from "sonner";

const GUEST_KEY = "grimoire_guest_deck";

function storeKey(sid) { return `grim_draft_${sid}`; }

const COLOR_ORDER = { W: 0, U: 1, B: 2, R: 3, G: 4 };
const TYPE_RANK = ["Creature", "Planeswalker", "Instant", "Sorcery", "Artifact", "Enchantment", "Battle", "Land"];
const SORTS = [{ k: "name", label: "Name" }, { k: "color", label: "Color" }, { k: "type", label: "Type" }, { k: "cmc", label: "CMC" }];
const cardCols = (c) => (c?.colors?.length ? c.colors : (c?.color_identity || []));
const colorKey = (c) => { const cols = cardCols(c); if (!cols.length) return 99; if (cols.length > 1) return 50 + cols.length; return COLOR_ORDER[cols[0]] ?? 90; };
const typeKey = (c) => { const t = c?.type_line || ""; const i = TYPE_RANK.findIndex((x) => t.includes(x)); return i < 0 ? 99 : i; };
const colorClass = (c) => {
  const cols = cardCols(c);
  if (!cols.length) return "bg-slate-600/80 text-slate-100";
  if (cols.length > 1) return "bg-gradient-to-r from-amber-500 to-yellow-600 text-stone-900";
  return { W: "bg-amber-50 text-stone-900", U: "bg-blue-700 text-white", B: "bg-stone-900 text-slate-200", R: "bg-red-700 text-white", G: "bg-green-700 text-white" }[cols[0]] || "bg-slate-600 text-white";
};

export default function DraftRoom() {
  const { shareId } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(null);
  const [state, setState] = useState(null);
  const [me, setMe] = useState(() => { try { return JSON.parse(localStorage.getItem(storeKey(shareId))) || null; } catch { return null; } });
  const [claimName, setClaimName] = useState("");
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);
  const [chatText, setChatText] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [hidePicked, setHidePicked] = useState(false);
  const [confirmCard, setConfirmCard] = useState(null);
  const [hoverCard, setHoverCard] = useState(null);
  const [view, setView] = useState("pick");
  const [deckSeat, setDeckSeat] = useState(null);
  const hostToken = useMemo(() => { try { return localStorage.getItem(`grim_draft_host_${shareId}`); } catch { return null; } }, [shareId]);

  useEffect(() => {
    api.get(`/drafts/${shareId}`).then(({ data }) => setDraft(data)).catch(() => { toast.error("Draft not found"); navigate("/draft"); });
  }, [shareId, navigate]);

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

  if (state.status === "cancelled") return (
    <div className="h-screen flex flex-col items-center justify-center bg-[#060a14] text-slate-100 gap-4 px-6 text-center" data-testid="draft-cancelled">
      <X className="w-10 h-10 text-red-400" />
      <p className="text-lg font-display font-semibold">This table was closed by the host.</p>
      <Button onClick={() => navigate("/draft")} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Back to drafts</Button>
    </div>
  );

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

  const cancelTable = async () => {
    if (!window.confirm("Close this table for everyone? This cannot be undone.")) return;
    try {
      await api.post(`/drafts/${shareId}/cancel`, { host_token: hostToken });
      localStorage.removeItem(`grim_draft_host_${shareId}`);
      toast.success("Table closed");
      navigate("/draft");
    } catch (e) { toast.error(e.response?.data?.detail || "Could not close table"); }
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

  const sendChat = async () => {
    if (!me) { toast.error("Claim a seat to chat"); return; }
    const text = chatText.trim();
    if (!text) return;
    setChatText("");
    try {
      const { data } = await api.post(`/drafts/${shareId}/chat`, { player_token: me.player_token, text });
      setState(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not send"); }
  };

  const seatsSorted = [...state.seats].sort((a, b) => a.index - b.index);
  const seatLabel = (seatIdx) => { const s = state.seats.find((x) => x.index === seatIdx); return `${s?.player_name || "Seat"} (Seat ${seatIdx + 1})`; };
  const seatPicks = (seatIdx) => (state.picks || []).filter((p) => p.seat_index === seatIdx).sort((a, b) => a.order - b.order).map((p) => cubeById[p.card_id]).filter(Boolean);
  const deckForSeat = (seatIdx) => {
    const cards = seatPicks(seatIdx);
    const merged = [];
    cards.forEach((c) => { const e = merged.find((x) => x.name === c.name); if (e) e.quantity++; else merged.push({ ...c, quantity: 1 }); });
    return { name: `${state.name} — ${seatLabel(seatIdx)}`, format: "kitchen", description: `Drafted from ${state.name}`, mainboard: merged, sideboard: [], commander: [] };
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
  const currentSeatName = state.current_seat_index != null ? state.seats.find((s) => s.index === state.current_seat_index)?.player_name : null;

  const comparator = (a, b) => {
    if (sortBy === "color") return colorKey(a) - colorKey(b) || a.name.localeCompare(b.name);
    if (sortBy === "type") return typeKey(a) - typeKey(b) || (a.cmc || 0) - (b.cmc || 0) || a.name.localeCompare(b.name);
    if (sortBy === "cmc") return (a.cmc || 0) - (b.cmc || 0) || a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  };
  const poolCards = (draft.cube || [])
    .filter((c) => (!query.trim() || c.name.toLowerCase().includes(query.toLowerCase())))
    .filter((c) => !hidePicked || !pickedIds.has(c.id))
    .slice()
    .sort(comparator);
  const availableCount = (draft.cube || []).filter((c) => !pickedIds.has(c.id)).length;

  const pickFeed = (state.picks || []).map((p) => {
    const seat = state.seats.find((s) => s.index === p.seat_index);
    return { ...p, player_name: seat?.player_name, card: cubeById[p.card_id] };
  }).reverse();

  const hoverIn = (c) => () => c && setHoverCard(c);
  const hoverOut = (c) => () => setHoverCard((h) => (h?.id === c?.id ? null : h));

  const viewTabs = (opts) => (
    <div className="flex items-center gap-1 rounded-full border border-slate-700 p-0.5" data-testid="view-tabs">
      {opts.map(([k, label, Icon]) => (
        <button key={k} data-testid={`view-${k}`} onClick={() => setView(k)}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-colors ${view === k ? "bg-amber-400 text-stone-900 font-semibold" : "text-slate-400 hover:text-slate-200"}`}>
          <Icon className="w-3.5 h-3.5" /> {label}
        </button>
      ))}
    </div>
  );

  const renderPickGrid = () => (
    <div>
      <div className="mb-3 flex items-center gap-3 flex-wrap">
        <Input data-testid="cube-filter" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter cards..." className="w-44 h-9 bg-slate-950 border-slate-700 text-slate-100" />
        <div className="flex items-center gap-1" data-testid="sort-controls">
          <span className="text-xs text-slate-500 mr-1">Sort</span>
          {SORTS.map((s) => (
            <button key={s.k} data-testid={`sort-${s.k}`} onClick={() => setSortBy(s.k)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${sortBy === s.k ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>{s.label}</button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none" data-testid="hide-picked-toggle">
          <input type="checkbox" checked={hidePicked} onChange={(e) => setHidePicked(e.target.checked)} className="accent-amber-400 w-3.5 h-3.5" /> Hide picked
        </label>
        <span className="text-xs text-slate-500 ml-auto">{availableCount} available</span>
      </div>
      <div className="max-h-[calc(100vh-280px)] overflow-y-auto pr-1 -mr-1">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3" data-testid="available-cards">
          {poolCards.map((c) => {
            const isPicked = pickedIds.has(c.id);
            const clickable = myTurn && !isPicked && !picking;
            return (
              <div key={c.id} data-testid={`pool-card-${c.id}`} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)}
                onClick={() => { if (clickable) setConfirmCard(c); }}
                className={`group relative rounded-lg overflow-hidden border transition-colors ${isPicked ? "border-slate-800 opacity-40 grayscale cursor-not-allowed" : clickable ? "border-slate-800 hover:border-amber-400/70 cursor-pointer" : "border-slate-800 cursor-default"}`}>
                <div className="aspect-[0.716] bg-slate-800 flex items-center justify-center">
                  {(c.image || c.art_crop) ? <img src={c.image || c.art_crop} alt={c.name} loading="lazy" className="w-full h-full object-cover" /> : <div className="p-2 text-center text-xs font-medium text-slate-200 leading-tight">{c.name}</div>}
                </div>
                {isPicked && <div className="absolute inset-0 flex items-center justify-center"><span data-testid={`picked-badge-${c.id}`} className="px-2 py-0.5 rounded bg-slate-950/80 text-[10px] uppercase tracking-wide text-slate-300 border border-slate-700">Picked</span></div>}
                {clickable && <div className="absolute inset-0 bg-amber-400/0 group-hover:bg-amber-400/15 transition-colors" />}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );

  const renderDraftTable = () => {
    const perSeat = seatsSorted.map((s) => (state.picks || []).filter((p) => p.seat_index === s.index).sort((a, b) => a.order - b.order));
    const maxRows = perSeat.reduce((m, a) => Math.max(m, a.length), 0);
    return (
      <div className="max-h-[calc(100vh-240px)] overflow-auto rounded-xl border border-slate-800" data-testid="draft-table">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="bg-[#0b111e]">
              <th className="px-2 py-2 text-left text-slate-500 w-10">#</th>
              <th className="w-8 bg-[#0b111e]"></th>
              {seatsSorted.map((s) => (
                <th key={s.index} className="px-3 py-2 text-left font-display text-slate-100 min-w-[160px] border-l border-slate-800">
                  {s.player_name || "—"}<div className="text-[10px] text-slate-500 font-normal">Seat {s.index + 1}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {maxRows === 0 ? (
              <tr><td colSpan={seatsSorted.length + 2} className="px-4 py-6 text-center text-sm text-slate-500">No picks yet.</td></tr>
            ) : Array.from({ length: maxRows }).map((_, r) => (
              <tr key={r} className="border-t border-slate-800/60">
                <td className="px-2 py-1 text-slate-500 tabular-nums">{r + 1}</td>
                <td className="px-1 text-slate-600 text-center">{r % 2 === 0 ? "→" : "←"}</td>
                {seatsSorted.map((s, ci) => {
                  const pk = perSeat[ci][r];
                  const card = pk ? cubeById[pk.card_id] : null;
                  return (
                    <td key={s.index} className="p-0.5 border-l border-slate-800/60">
                      {card ? (
                        <div data-testid={`table-cell-${s.index}-${r}`} onMouseEnter={hoverIn(card)} onMouseLeave={hoverOut(card)}
                          className={`px-3 py-1.5 rounded truncate cursor-default ${colorClass(card)}`}>{card.name}</div>
                      ) : <div className="px-3 py-1.5 text-slate-700">·</div>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const renderDecks = () => {
    const activeSeat = deckSeat != null ? deckSeat : (me?.seats?.[0] ?? seatsSorted[0]?.index ?? 0);
    const deck = deckForSeat(activeSeat);
    const total = deck.mainboard.reduce((n, c) => n + c.quantity, 0);
    return (
      <div data-testid="decks-view">
        <div className="flex items-center gap-2 flex-wrap mb-4">
          <span className="text-xs text-slate-500">View deck:</span>
          {seatsSorted.map((s) => {
            const mine = me?.seats?.includes(s.index);
            return (
              <button key={s.index} data-testid={`deck-seat-${s.index}`} onClick={() => setDeckSeat(s.index)}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${activeSeat === s.index ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>
                {s.player_name || "Seat"} <span className="opacity-60">S{s.index + 1}{mine ? " · you" : ""}</span>
              </button>
            );
          })}
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <div className="font-display font-semibold">{seatLabel(activeSeat)} · <span className="text-amber-400">{total}</span> cards</div>
            <div className="flex gap-2">
              <Button size="sm" data-testid="decks-export" variant="outline" onClick={() => exportSeat(activeSeat)} className="bg-slate-900 border-slate-700 text-slate-200">Export</Button>
              <Button size="sm" data-testid="decks-edit" onClick={() => editInBuilder(activeSeat)} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Edit in builder</Button>
            </div>
          </div>
          {deck.mainboard.length === 0 ? (
            <p className="text-sm text-slate-500">No cards drafted for this seat yet.</p>
          ) : (
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-0.5">
              {deck.mainboard.map((c, i) => (
                <div key={c.id || i} data-testid={`deck-card-${activeSeat}-${i}`} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)}
                  className="flex items-center gap-2 text-sm py-1 px-1 rounded border-b border-slate-800/40 cursor-default hover:bg-slate-800/40">
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${colorClass(c)}`} />
                  <span className="text-slate-500 tabular-nums w-5">{c.quantity}</span>
                  <span className="truncate text-slate-200">{c.name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderResults = () => (
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {seatsSorted.map((s) => (
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
  );

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
            <Button size="sm" variant="outline" data-testid="draft-copy-link" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Invite link copied"); }} className="bg-slate-900 border-slate-700 text-slate-200"><Copy className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Copy invite</span></Button>
            {hostToken && state.status !== "complete" && (
              <Button size="sm" variant="outline" data-testid="close-table" onClick={cancelTable} className="bg-slate-900 border-red-500/40 text-red-300 hover:bg-red-500/10"><X className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Close table</span></Button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Seats / lobby */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6" data-testid="seat-grid">
          {seatsSorted.map((s) => {
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

        <div className="grid lg:grid-cols-[1fr_340px] gap-6 items-start">
          <div className="min-w-0 space-y-6">
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
                    {myTurn ? `Your pick! · Seat ${state.current_seat_index + 1}` : `${currentSeatName || "…"}'s pick`} · {state.pick_index}/{state.order_len}
                  </div>
                  {viewTabs([["pick", "Pick", LayoutGrid], ["table", "Draft Table", Table2], ["decks", "Decks", Eye]])}
                </div>
                {view === "table" ? renderDraftTable() : view === "decks" ? renderDecks() : renderPickGrid()}
              </div>
            )}

            {state.status === "complete" && (
              <div data-testid="draft-complete">
                <div className="mb-4 flex items-center gap-3 flex-wrap">
                  <h2 className="font-display text-2xl font-bold">Draft complete 🎉</h2>
                  {viewTabs([["pick", "Results", ListChecks], ["table", "Draft Table", Table2], ["decks", "Decks", Eye]])}
                </div>
                {view === "table" ? renderDraftTable() : view === "decks" ? renderDecks() : renderResults()}
                <p className="text-xs text-slate-500 mt-4">Open any seat's deck in the builder to tweak and save it.</p>
              </div>
            )}
          </div>

          <aside className="space-y-4 lg:sticky lg:top-6 self-start" data-testid="draft-sidebar">
            {state.status !== "lobby" && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-2 h-[300px] flex items-center justify-center overflow-hidden" data-testid="card-preview">
                {hoverCard ? (
                  (hoverCard.image || hoverCard.art_crop)
                    ? <img src={hoverCard.image || hoverCard.art_crop} alt={hoverCard.name} className="max-h-full w-auto rounded-lg" />
                    : <div className="text-center text-sm text-slate-200 px-3">{hoverCard.name}</div>
                ) : (
                  <span className="text-xs text-slate-600 px-4 text-center">Hover a card to preview it here</span>
                )}
              </div>
            )}
            {pickFeed.length > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4" data-testid="pick-feed">
                <h3 className="font-display font-semibold text-sm mb-3 flex items-center gap-2"><ListChecks className="w-4 h-4 text-amber-400" /> Pick feed</h3>
                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                  {pickFeed.map((p) => (
                    <div key={p.order} data-testid={`pick-feed-item-${p.order}`} onMouseEnter={hoverIn(p.card)} onMouseLeave={hoverOut(p.card)}
                      className="flex items-center gap-2 text-xs rounded-md hover:bg-slate-800/60 p-1 cursor-default">
                      <div className="w-8 h-11 rounded bg-slate-800 overflow-hidden shrink-0 flex items-center justify-center">
                        {p.card && (p.card.image || p.card.art_crop) ? <img src={p.card.image || p.card.art_crop} alt={p.card.name} loading="lazy" className="w-full h-full object-cover" /> : <span className="text-[8px] text-slate-500 px-0.5 text-center leading-none">{p.card?.name?.slice(0, 10) || "?"}</span>}
                      </div>
                      <div className="min-w-0">
                        <div className="text-amber-400 font-semibold truncate">{(p.player_name || "Seat")} <span className="text-slate-500 font-normal">· S{p.seat_index + 1}</span></div>
                        <div className="text-slate-300 truncate">{p.card?.name || "a card"}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 flex flex-col" data-testid="chat-panel">
              <h3 className="font-display font-semibold text-sm mb-3 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-amber-400" /> Table chat</h3>
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1 mb-3" data-testid="chat-messages">
                {(state.messages || []).length === 0 ? (
                  <p className="text-xs text-slate-600">No messages yet. Say hello!</p>
                ) : (state.messages || []).map((m, i) => (
                  <div key={m.id || i} data-testid={`chat-message-${i}`} className="text-xs leading-relaxed">
                    <span className="text-amber-400 font-semibold">{m.name}</span>
                    <span className="text-slate-300 ml-1.5 break-words">{m.text}</span>
                  </div>
                ))}
              </div>
              {me ? (
                <div className="flex gap-2">
                  <Input data-testid="chat-input" value={chatText} onChange={(e) => setChatText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") sendChat(); }} placeholder="Message the table..." className="h-9 bg-slate-950 border-slate-700 text-slate-100 text-sm focus-visible:ring-amber-400" />
                  <Button data-testid="chat-send" onClick={sendChat} size="sm" className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0">Send</Button>
                </div>
              ) : (
                <p className="text-xs text-slate-600">Claim a seat to join the chat.</p>
              )}
            </div>
          </aside>
        </div>
      </main>

      {confirmCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="confirm-pick-dialog" onClick={() => setConfirmCard(null)}>
          <div className="bg-[#0b111e] border border-slate-700 rounded-2xl p-5 max-w-xs w-full text-center" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-lg font-bold mb-3">Draft this card?</h3>
            <div className="rounded-lg overflow-hidden border border-slate-800 mb-3">
              {(confirmCard.image || confirmCard.art_crop) ? <img src={confirmCard.image || confirmCard.art_crop} alt={confirmCard.name} className="w-full" /> : <div className="p-6 text-slate-200">{confirmCard.name}</div>}
            </div>
            <p className="text-sm text-slate-300 mb-4 truncate">{confirmCard.name}</p>
            <div className="flex gap-2">
              <Button data-testid="cancel-pick-btn" variant="outline" onClick={() => setConfirmCard(null)} className="flex-1 bg-slate-900 border-slate-700 text-slate-200">Cancel</Button>
              <Button data-testid="confirm-pick-btn" disabled={picking} onClick={async () => { const c = confirmCard; setConfirmCard(null); await pick(c); }} className="flex-1 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">{picking ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : "Confirm pick"}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
