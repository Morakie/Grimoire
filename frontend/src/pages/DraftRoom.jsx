import React, { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { buildExport } from "@/components/ExportDialog";
import { Sparkles, Loader2, Copy, Check, ListChecks, MessageSquare, X, LayoutGrid, Table2, Eye, Volume2, VolumeX, Bookmark, BookmarkPlus, BookmarkCheck, ArrowUp, ArrowDown, Undo2, Bot, Plus, PartyPopper, Lightbulb, Lock } from "lucide-react";
import { toast } from "sonner";

const GUEST_KEY = "grimoire_guest_deck";
// Touch screens have no hover: cards open a tap preview instead and queue buttons are always visible.
const canHover = () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia("(hover: hover)").matches;

function storeKey(sid) { return `grim_draft_${sid}`; }

const COLOR_ORDER = { W: 0, U: 1, B: 2, R: 3, G: 4 };
const TYPE_RANK = ["Creature", "Planeswalker", "Instant", "Sorcery", "Artifact", "Enchantment", "Battle", "Land"];
// Desktop card sizes: columns in the card pool at large widths.
const CARD_SIZES = [
  { k: "s", label: "S", cols: "lg:grid-cols-6 2xl:grid-cols-7" },
  { k: "m", label: "M", cols: "lg:grid-cols-5" },
  { k: "l", label: "L", cols: "lg:grid-cols-4" },
];
const SORTS = [{ k: "elo", label: "Rank" }, { k: "name", label: "Name" }, { k: "color", label: "Color" }, { k: "type", label: "Type" }, { k: "cmc", label: "CMC" }];
const cardCols = (c) => (c?.colors?.length ? c.colors : (c?.color_identity || []));
const colorKey = (c) => { const cols = cardCols(c); if (!cols.length) return 99; if (cols.length > 1) return 50 + cols.length; return COLOR_ORDER[cols[0]] ?? 90; };
const typeKey = (c) => { const t = c?.type_line || ""; const i = TYPE_RANK.findIndex((x) => t.includes(x)); return i < 0 ? 99 : i; };
const colorClass = (c) => {
  const cols = cardCols(c);
  if (!cols.length) return "bg-slate-600/80 text-slate-100";
  if (cols.length > 1) return "bg-gradient-to-r from-amber-500 to-yellow-600 text-stone-900";
  return { W: "bg-amber-50 text-stone-900", U: "bg-blue-700 text-white", B: "bg-stone-900 text-slate-200", R: "bg-red-700 text-white", G: "bg-green-700 text-white" }[cols[0]] || "bg-slate-600 text-white";
};

function playBeep() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    [880, 1320].forEach((freq, i) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination); o.type = "sine"; o.frequency.value = freq;
      const t = now + i * 0.18;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.28, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      o.start(t); o.stop(t + 0.18);
    });
    setTimeout(() => ctx.close(), 600);
  } catch { /* ignore */ }
}

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
  const [sortBy, setSortBy] = useState("elo");
  const [hidePicked, setHidePicked] = useState(false);
  const [confirmCard, setConfirmCard] = useState(null);
  const [hoverCard, setHoverCard] = useState(null);
  const [reassignPick, setReassignPick] = useState(null);
  const [reassignQuery, setReassignQuery] = useState("");
  const [view, setView] = useState("pick");
  const [deckSeat, setDeckSeat] = useState(null);
  const [showMiniTable, setShowMiniTable] = useState(false);
  const [sheet, setSheet] = useState(null);            // mobile bottom sheet: "queue" | "feed" | "chat"
  const [previewCard, setPreviewCard] = useState(null); // mobile tap-to-preview
  const seatStripRef = useRef(null);
  const [hints, setHints] = useState(() => localStorage.getItem("grim_draft_hints") !== "off");
  const [suggestions, setSuggestions] = useState([]);
  const [cardSize, setCardSize] = useState(() => localStorage.getItem("grim_draft_card_size") || "m");
  const [muted, setMuted] = useState(() => localStorage.getItem("grim_draft_muted") === "true");
  const [queue, setQueue] = useState(() => { try { return JSON.parse(localStorage.getItem(`grim_draft_queue_${shareId}`)) || []; } catch { return []; } });
  const hostToken = useMemo(() => { try { return localStorage.getItem(`grim_draft_host_${shareId}`); } catch { return null; } }, [shareId]);
  const prevTurnRef = useRef(false);
  const autoPickRef = useRef(() => {});
  const inFlightRef = useRef(false);

  useEffect(() => {
    api.get(`/drafts/${shareId}`).then(({ data }) => setDraft(data)).catch(() => { toast.error("Draft not found"); navigate("/draft"); });
  }, [shareId, navigate]);

  // Poll every 2s, or every second while a bot is on the clock (its pick lands on the next poll).
  const botOnClock = !!(state && state.status === "drafting" && state.current_seat_index != null
    && (state.players || []).some((p) => p.is_bot && p.seats.includes(state.current_seat_index)));
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try { const { data } = await api.get(`/drafts/${shareId}/state`); if (active) setState(data); } catch {}
    };
    tick();
    const iv = setInterval(tick, botOnClock ? 1000 : 2000);
    return () => { active = false; clearInterval(iv); };
  }, [shareId, botOnClock]);

  useEffect(() => { localStorage.setItem(`grim_draft_queue_${shareId}`, JSON.stringify(queue)); }, [queue, shareId]);

  const pickedIds = useMemo(() => new Set((state?.picked_ids) || (state?.picks || []).map((p) => p.card_id)), [state]);
  const cubeById = useMemo(() => { const m = {}; (draft?.cube || []).forEach((c) => (m[c.id] = c)); return m; }, [draft]);

  // Drop any queued card that has been drafted (by anyone) so auto-pick falls through to the next one.
  useEffect(() => { setQueue((q) => q.filter((id) => !pickedIds.has(id))); }, [pickedIds]);

  // Beep + auto-pick when it becomes your turn.
  useEffect(() => {
    const now = !!(state && me && state.status === "drafting" && state.current_seat_index != null && me.seats.includes(state.current_seat_index));
    if (now && !prevTurnRef.current && !muted) playBeep();
    prevTurnRef.current = now;
  }, [state, me, muted]);

  // Auto-pick from the queue whenever it's our turn — re-runs on every state/queue change so
  // it keeps picking across consecutive turns, wheel-backs and multi-seat players.
  useEffect(() => { if (state && me) autoPickRef.current(); }, [state, me, queue]);

  // Seats are shuffled when the draft starts: keep our stored seat list in sync with the server's.
  useEffect(() => {
    if (!me || !state) return;
    const p = (state.players || []).find((x) => x.id === me.player_id);
    if (p && JSON.stringify(p.seats) !== JSON.stringify(me.seats)) {
      const next = { ...me, seats: p.seats };
      localStorage.setItem(storeKey(shareId), JSON.stringify(next));
      setMe(next);
    }
  }, [state, me, shareId]);

  // Pick suggestions (same engine as the bots) when it's our turn and hints are on.
  const turnSeat = state && me && state.status === "drafting" && state.current_seat_index != null
    && me.seats.includes(state.current_seat_index) ? state.current_seat_index : null;
  const pickNo = state?.pick_index;
  useEffect(() => {
    setSuggestions([]);
    if (!hints || turnSeat == null) return;
    let active = true;
    api.get(`/drafts/${shareId}/suggestions`, { params: { seat: turnSeat } })
      .then(({ data }) => { if (active) setSuggestions(data.suggestions || []); })
      .catch(() => {});
    return () => { active = false; };
  }, [hints, turnSeat, pickNo, shareId]);

  // Phones: keep the seat on the clock centred in the sideways-scrolling seat strip.
  const clockSeat = state?.current_seat_index;
  useEffect(() => {
    const strip = seatStripRef.current;
    if (!strip || clockSeat == null || strip.scrollWidth <= strip.clientWidth) return;
    const el = strip.querySelector(`[data-testid="seat-${clockSeat}"]`);
    if (el) strip.scrollLeft = el.offsetLeft - strip.clientWidth / 2 + el.clientWidth / 2;
  }, [clockSeat]);

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

  const addBot = async () => {
    try { const { data } = await api.post(`/drafts/${shareId}/bots`, { host_token: hostToken }); setState((s) => ({ ...s, ...data })); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not add a bot"); }
  };

  const removeBot = async (playerId) => {
    try { const { data } = await api.post(`/drafts/${shareId}/bots/remove`, { host_token: hostToken, player_id: playerId }); setState((s) => ({ ...s, ...data })); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not remove the bot"); }
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
    inFlightRef.current = true;
    setPicking(true);
    try {
      const { data } = await api.post(`/drafts/${shareId}/pick`, { player_token: me.player_token, seat_index: seat, card_id: card.id });
      setState(data);
    } catch (e) { toast.error(e.response?.data?.detail || "Pick failed"); }
    finally { setPicking(false); inFlightRef.current = false; }
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

  const toggleQueue = (id) => setQueue((q) => (q.includes(id) ? q.filter((x) => x !== id) : [...q, id]));
  const removeFromQueue = (id) => setQueue((q) => q.filter((x) => x !== id));
  const moveQueue = (id, dir) => setQueue((q) => { const i = q.indexOf(id); const j = i + dir; if (i < 0 || j < 0 || j >= q.length) return q; const n = [...q]; [n[i], n[j]] = [n[j], n[i]]; return n; });
  const toggleMute = () => setMuted((m) => { localStorage.setItem("grim_draft_muted", (!m).toString()); return !m; });

  const undoPick = async () => {
    try { const { data } = await api.post(`/drafts/${shareId}/undo`, { host_token: hostToken }); setState(data); toast.success("Last pick undone"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not undo"); }
  };
  const doReassign = async (cardId) => {
    try { const { data } = await api.post(`/drafts/${shareId}/reassign`, { host_token: hostToken, order: reassignPick.order, card_id: cardId }); setState(data); setReassignPick(null); setReassignQuery(""); toast.success("Pick reassigned"); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not reassign"); }
  };

  const seatsSorted = [...state.seats].sort((a, b) => a.index - b.index);
  const isBotSeat = (seatIdx) => (state.players || []).some((p) => p.is_bot && p.seats.includes(seatIdx));
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

  // Auto-pick the top still-available queued card whenever it's our turn.
  autoPickRef.current = () => {
    if (inFlightRef.current) return;
    if (!(state.status === "drafting" && me && state.current_seat_index != null && me.seats.includes(state.current_seat_index))) return;
    const next = queue.map((id) => cubeById[id]).find((c) => c && !pickedIds.has(c.id));
    if (next) { toast.success(`Auto-picked ${next.name} from your queue`); pick(next); }
  };

  const comparator = (a, b) => {
    // Custom (uploaded) cards always sit at the top of the pool, whatever the sort.
    const custom = (b.is_custom ? 1 : 0) - (a.is_custom ? 1 : 0);
    if (custom) return custom;
    if (sortBy === "elo") return (b.elo || 0) - (a.elo || 0) || a.name.localeCompare(b.name);
    if (sortBy === "color") return colorKey(a) - colorKey(b) || typeKey(a) - typeKey(b) || (a.cmc || 0) - (b.cmc || 0) || a.name.localeCompare(b.name);
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

  const hoverable = canHover();
  const tapPreview = (c) => (!hoverable && c ? () => setPreviewCard(c) : undefined);
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
        <Input data-testid="cube-filter" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter cards..." className="w-full sm:w-44 h-9 bg-slate-950 border-slate-700 text-slate-100" />
        <div className="flex items-center gap-1" data-testid="sort-controls">
          <span className="text-xs text-slate-500 mr-1">Sort</span>
          {SORTS.map((s) => (
            <button key={s.k} data-testid={`sort-${s.k}`} onClick={() => setSortBy(s.k)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${sortBy === s.k ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>{s.label}</button>
          ))}
        </div>
        <button data-testid="toggle-hints" onClick={() => setHints((h) => { localStorage.setItem("grim_draft_hints", h ? "off" : "on"); return !h; })}
          title={hints ? "Hide pick suggestions" : "Show pick suggestions on your turn"}
          className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border transition-colors ${hints ? "border-amber-400/60 text-amber-300" : "border-slate-700 text-slate-500 hover:text-slate-300"}`}>
          <Lightbulb className="w-3.5 h-3.5" /> Hints
        </button>
        <div className="hidden lg:flex items-center gap-1" data-testid="card-size-controls">
          <span className="text-xs text-slate-500 mr-1">Size</span>
          {CARD_SIZES.map((z) => (
            <button key={z.k} data-testid={`card-size-${z.k}`} onClick={() => { setCardSize(z.k); localStorage.setItem("grim_draft_card_size", z.k); }}
              className={`text-xs w-7 py-1 rounded-full border transition-colors ${cardSize === z.k ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>{z.label}</button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer select-none" data-testid="hide-picked-toggle">
          <input type="checkbox" checked={hidePicked} onChange={(e) => setHidePicked(e.target.checked)} className="accent-amber-400 w-3.5 h-3.5" /> Hide picked
        </label>
        <span className="text-xs text-slate-500 ml-auto">{availableCount} available</span>
      </div>
      {hints && myTurn && suggestions.some((id) => cubeById[id] && !pickedIds.has(id)) && (
        <div className="mb-3 flex items-center gap-2 flex-wrap" data-testid="pick-suggestions">
          <span className="flex items-center gap-1 text-xs text-slate-500"><Lightbulb className="w-3.5 h-3.5 text-amber-400" /> Suggested</span>
          {suggestions.map((id) => cubeById[id]).filter((c) => c && !pickedIds.has(c.id)).map((c) => (
            <button key={c.id} data-testid={`suggestion-${c.id}`} onClick={() => setConfirmCard(c)} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)}
              className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-slate-700 bg-slate-900/60 text-slate-200 hover:border-amber-400/70 hover:text-amber-200 max-w-[60vw] sm:max-w-[220px]">
              <span className={`w-2 h-2 rounded-full shrink-0 ${colorClass(c)}`} /><span className="truncate">{c.name}</span>
            </button>
          ))}
        </div>
      )}
      <div className="lg:max-h-[calc(100vh-280px)] lg:overflow-y-auto lg:pr-1 lg:-mr-1">
        <div className={`grid grid-cols-3 sm:grid-cols-4 ${(CARD_SIZES.find((z) => z.k === cardSize) || CARD_SIZES[1]).cols} gap-2 sm:gap-3`} data-testid="available-cards">
          {poolCards.map((c) => {
            const isPicked = pickedIds.has(c.id);
            const clickable = myTurn && !isPicked && !picking;
            const queued = queue.includes(c.id);
            return (
              <div key={c.id} data-testid={`pool-card-${c.id}`} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)}
                onClick={() => { if (clickable) setConfirmCard(c); else if (!hoverable) setPreviewCard(c); }}
                className={`group relative rounded-lg overflow-hidden border transition-colors ${isPicked ? "border-slate-800 opacity-40 grayscale cursor-not-allowed" : clickable ? "border-slate-800 hover:border-amber-400/70 cursor-pointer" : "border-slate-800 cursor-default"}`}>
                <div className="aspect-[0.716] bg-slate-800 flex items-center justify-center">
                  {(c.image || c.art_crop) ? <img src={c.image || c.art_crop} alt={c.name} loading="lazy" className="w-full h-full object-cover" /> : <div className="p-2 text-center text-xs font-medium text-slate-200 leading-tight">{c.name}</div>}
                </div>
                {isPicked ? (
                  <div className="absolute inset-0 flex items-center justify-center"><span data-testid={`picked-badge-${c.id}`} className="px-2 py-0.5 rounded bg-slate-950/80 text-[10px] uppercase tracking-wide text-slate-300 border border-slate-700">Picked</span></div>
                ) : (
                  <button data-testid={`queue-${c.id}`} onClick={(e) => { e.stopPropagation(); toggleQueue(c.id); }}
                    title={queued ? "Remove from queue" : "Queue for later"}
                    className={`absolute top-1 right-1 ${hoverable ? "w-6 h-6" : "w-8 h-8"} rounded flex items-center justify-center transition-opacity ${queued ? "bg-amber-400 text-stone-900" : `bg-black/70 text-slate-200 ${hoverable ? "opacity-0 group-hover:opacity-100" : ""} hover:bg-amber-400 hover:text-stone-900`}`}>
                    {queued ? <BookmarkCheck className="w-3.5 h-3.5" /> : <BookmarkPlus className="w-3.5 h-3.5" />}
                  </button>
                )}
                {clickable && <div className="absolute inset-0 bg-amber-400/0 group-hover:bg-amber-400/15 transition-colors pointer-events-none" />}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );

  // fit=true squeezes every seat into the available width (Table Peek popout); the main view keeps
  // readable columns and scrolls sideways instead.
  const renderDraftTable = (compact = false, fit = false) => {
    const perSeat = seatsSorted.map((s) => (state.picks || []).filter((p) => p.seat_index === s.index).sort((a, b) => a.order - b.order));
    const maxRows = perSeat.reduce((m, a) => Math.max(m, a.length), 0);
    const dense = compact || (fit && seatsSorted.length > 4);
    const cell = compact ? "px-1.5 py-0.5 text-[10px]" : dense ? "px-1.5 py-1 text-xs" : "px-2 sm:px-3 py-1.5 text-xs sm:text-sm";
    return (
      <div className={`${compact ? "max-h-[44vh]" : "max-h-[70vh] lg:max-h-[calc(100vh-240px)]"} overflow-auto rounded-xl border border-slate-800`} data-testid={compact ? "mini-draft-table" : "draft-table"}>
        <table className={`w-full border-collapse ${fit ? "table-fixed" : ""}`}>
          {fit && <colgroup><col className="w-8" /><col className="w-5" />{seatsSorted.map((s) => <col key={s.index} />)}</colgroup>}
          <thead className="sticky top-0 z-10">
            <tr className="bg-[#0b111e]">
              <th className="px-2 py-1.5 text-left text-slate-500 w-8 text-xs sticky left-0 z-10 bg-[#0b111e]">#</th>
              <th className="w-6 bg-[#0b111e]"></th>
              {seatsSorted.map((s) => (
                <th key={s.index} title={s.player_name || ""} className={`${dense ? "px-1.5" : "px-3"} py-1.5 text-left font-display text-slate-100 border-l border-slate-800 truncate ${dense ? "text-[11px]" : "text-xs sm:text-sm min-w-[112px] sm:min-w-[160px]"} ${compact ? "min-w-[96px]" : ""}`}>
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
                <td className="px-2 py-0.5 text-slate-500 tabular-nums text-xs sticky left-0 bg-[#0b111e]">{r + 1}</td>
                <td className="px-1 text-slate-600 text-center text-xs">{r % 2 === 0 ? "→" : "←"}</td>
                {seatsSorted.map((s, ci) => {
                  const pk = perSeat[ci][r];
                  const card = pk ? cubeById[pk.card_id] : null;
                  return (
                    <td key={s.index} className="p-0.5 border-l border-slate-800/60">
                      {card ? (
                        <div data-testid={compact ? undefined : `table-cell-${s.index}-${r}`} onMouseEnter={hoverIn(card)} onMouseLeave={hoverOut(card)}
                          onClick={hostToken ? () => setReassignPick({ order: pk.order, seat_index: s.index, card }) : tapPreview(card)}
                          title={card.name} className={`rounded truncate ${cell} ${colorClass(card)} ${hostToken ? "cursor-pointer hover:ring-2 hover:ring-amber-300" : "cursor-default"}`}>{card.name}</div>
                      ) : <div className={`${cell} text-slate-700`}>·</div>}
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
                <div key={c.id || i} data-testid={`deck-card-${activeSeat}-${i}`} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)} onClick={tapPreview(c)}
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

  const renderQueueList = () => (
    <>
                {queue.length === 0 ? (
                  <p className="text-[11px] text-slate-600 px-1 py-2">Bookmark cards in the pool to queue them. Auto-picks your top available card the moment it's your turn.</p>
                ) : (
                  <div className="space-y-1">
                    {queue.map((id, i) => { const c = cubeById[id]; if (!c) return null; const taken = pickedIds.has(id);
                      return (
                        <div key={id} data-testid={`queue-item-${id}`} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)} className={`flex items-center gap-1 text-xs rounded p-1 hover:bg-slate-800/60 ${taken ? "opacity-40" : ""}`}>
                          <span className="text-slate-500 w-4 tabular-nums shrink-0">{i + 1}</span>
                          <span className="flex-1 truncate text-slate-200">{c.name}{taken && <span className="text-red-400 ml-1">(taken)</span>}</span>
                          <button data-testid={`queue-up-${id}`} onClick={() => moveQueue(id, -1)} disabled={i === 0} className="p-0.5 text-slate-500 hover:text-amber-300 disabled:opacity-20"><ArrowUp className="w-3.5 h-3.5" /></button>
                          <button data-testid={`queue-down-${id}`} onClick={() => moveQueue(id, 1)} disabled={i === queue.length - 1} className="p-0.5 text-slate-500 hover:text-amber-300 disabled:opacity-20"><ArrowDown className="w-3.5 h-3.5" /></button>
                          <button data-testid={`queue-remove-${id}`} onClick={() => removeFromQueue(id)} className="p-0.5 text-slate-500 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
                        </div>
                      );
                    })}
                  </div>
                )}
    </>
  );
  const renderFeedList = () => (
                <div className="space-y-1.5">
                  {pickFeed.map((p) => (
                    <div key={p.order} data-testid={`pick-feed-item-${p.order}`} onMouseEnter={hoverIn(p.card)} onMouseLeave={hoverOut(p.card)} onClick={tapPreview(p.card)}
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
  );
  const renderChatBody = (tall = false) => (
    <>
              <div className={`space-y-2 ${tall ? "max-h-[50vh]" : "max-h-64"} overflow-y-auto pr-1 mb-3`} data-testid="chat-messages">
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
    </>
  );

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
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-[#070c17]">
        <div className="max-w-7xl 2xl:max-w-[1760px] mx-auto px-3 sm:px-6 py-3 flex items-center gap-2 sm:gap-3 flex-wrap">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <span className="text-slate-500">/</span>
          <span className="font-display font-semibold truncate min-w-0 max-w-[40vw] sm:max-w-none">{state.name}</span>
          <span className="text-xs px-2 py-0.5 rounded-full border border-slate-700 text-slate-300 capitalize">{state.status}</span>
          {!me && state.status !== "lobby" && (
            <span data-testid="spectating-badge" className="text-xs px-2 py-0.5 rounded-full border border-sky-400/30 text-sky-300 flex items-center gap-1"><Eye className="w-3 h-3" /> Watching</span>
          )}
          <div className="ml-auto flex items-center gap-2">
            {state.status === "drafting" && (
              <Button size="sm" variant="outline" data-testid="mute-toggle" onClick={toggleMute} title={muted ? "Unmute turn alert" : "Mute turn alert"} className="bg-slate-900 border-slate-700 text-slate-300">{muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}</Button>
            )}
            <Input readOnly value={shareUrl} className="w-56 h-8 bg-slate-950 border-slate-700 text-slate-300 text-xs hidden sm:block" data-testid="draft-share-url" />
            <Button size="sm" variant="outline" data-testid="draft-copy-link" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Invite link copied"); }} className="bg-slate-900 border-slate-700 text-slate-200"><Copy className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Copy invite</span></Button>
            {hostToken && (state.status === "drafting" || state.status === "complete") && (state.picks?.length > 0) && (
              <Button size="sm" variant="outline" data-testid="undo-pick" onClick={undoPick} title="Undo last pick (host)" className="bg-slate-900 border-amber-400/40 text-amber-300 hover:bg-amber-400/10"><Undo2 className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Undo pick</span></Button>
            )}
            {hostToken && state.status !== "complete" && (
              <Button size="sm" variant="outline" data-testid="close-table" onClick={cancelTable} className="bg-slate-900 border-red-500/40 text-red-300 hover:bg-red-500/10"><X className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Close table</span></Button>
            )}
          </div>
        </div>
      </header>

      <main className={`max-w-7xl 2xl:max-w-[1760px] mx-auto px-3 sm:px-6 py-4 sm:py-6 ${state.status !== "lobby" ? "pb-28 lg:pb-6" : ""}`}>
        <div ref={seatStripRef} className="relative flex gap-2 overflow-x-auto -mx-3 px-3 pb-1 mb-4 sm:mx-0 sm:px-0 sm:pb-0 sm:mb-6 sm:grid sm:grid-cols-2 lg:grid-cols-4 sm:gap-3 sm:overflow-visible" data-testid="seat-grid">
          {seatsSorted.map((s) => {
            const isCurrent = state.current_seat_index === s.index;
            const mine = me?.seats?.includes(s.index);
            const last = seatPicks(s.index).slice(-1)[0];
            return (
              <div key={s.index} data-testid={`seat-${s.index}`} className={`rounded-xl border p-2.5 sm:p-3 min-w-[148px] shrink-0 sm:min-w-0 ${isCurrent ? "border-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.15)]" : "border-slate-800"} bg-slate-900/50`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Seat {s.index + 1}{mine ? " · you" : ""}</span>
                  <span className="text-xs text-amber-400 tabular-nums">{seatPicks(s.index).length}/{state.pick_cap}</span>
                </div>
                <div className="font-display font-semibold truncate flex items-center gap-1.5">
                  {isBotSeat(s.index) && <Bot className="w-3.5 h-3.5 text-amber-400 shrink-0" aria-label="Bot" />}
                  {s.player_name || <span className="text-slate-600">unclaimed</span>}
                </div>
                {isCurrent && <div className="text-[11px] text-amber-400 mt-0.5">On the clock</div>}
                <div className="text-[11px] text-slate-500 mt-0.5 truncate" data-testid={`seat-last-${s.index}`}>{last ? <>Last: <span className="text-slate-400">{last.name}</span></> : "No picks yet"}</div>
              </div>
            );
          })}
        </div>

        <div className={`grid gap-6 items-start ${state.status === "drafting" ? "lg:grid-cols-[220px_minmax(0,1fr)_340px] 2xl:grid-cols-[260px_minmax(0,1fr)_420px]" : "lg:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_420px]"}`}>
          {state.status === "drafting" && (
            <aside className="hidden lg:flex lg:sticky lg:top-20 self-start flex-col max-h-[calc(100vh-110px)] bg-[#0b111e] border border-slate-800 rounded-lg" data-testid="queue-panel">
              <div className="flex items-center gap-1.5 px-3 py-2 border-b border-slate-800 shrink-0">
                <Bookmark className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-display font-semibold">Pick queue</span>
                <span className="text-xs text-slate-500">({queue.length})</span>
              </div>
              <div className="overflow-y-auto p-2">
                {renderQueueList()}
              </div>
            </aside>
          )}
          <div className="min-w-0 space-y-6">
            {state.status === "lobby" && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 max-w-md" data-testid="lobby-panel">
                <h2 className="font-display text-xl font-bold mb-2">Join the draft</h2>
                <p className="text-sm text-slate-400 mb-4">Enter your name to claim your seat(s). {state.seats_per_player} seat(s) each. {state.players.length}/{state.num_players} players in.</p>
                <div className="mb-4 rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1.5">Invite players</div>
                  <div className="flex items-center gap-2">
                    <Input readOnly value={shareUrl} data-testid="lobby-share-url" className="h-8 bg-slate-900 border-slate-700 text-slate-300 text-xs" />
                    <Button size="sm" data-testid="lobby-copy-link" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Invite link copied"); }} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0"><Copy className="w-4 h-4" /></Button>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1.5 flex items-center gap-1.5 flex-wrap">
                    Table code: <span className="text-amber-400 font-mono text-sm tracking-widest" data-testid="lobby-code">{state.join_code || shareId}</span>
                    {state.join_code && <button type="button" data-testid="lobby-copy-code" onClick={() => { navigator.clipboard.writeText(state.join_code); toast.success("Code copied"); }} className="text-slate-500 hover:text-amber-300" title="Copy code"><Copy className="w-3 h-3" /></button>}
                    {state.private && <span className="ml-auto flex items-center gap-1 text-slate-400"><Lock className="w-3 h-3" /> Private</span>}
                  </div>
                </div>
                <div className="mb-4" data-testid="lobby-players">
                  <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-1.5">Players</div>
                  <ul className="space-y-1">
                    {state.players.map((p) => (
                      <li key={p.id} className="flex items-center gap-2 text-sm text-slate-200" data-testid={`lobby-player-${p.id}`}>
                        {p.is_bot && <Bot className="w-3.5 h-3.5 text-amber-400" aria-label="Bot" />}
                        <span className="truncate">{p.name}</span>
                        <span className="text-[11px] text-slate-500">seat {p.seats.map((s) => s + 1).join(", ")}</span>
                        {p.is_bot && hostToken && (
                          <button data-testid={`remove-bot-${p.id}`} onClick={() => removeBot(p.id)} title="Remove bot" className="ml-auto text-slate-500 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
                        )}
                      </li>
                    ))}
                    {state.players.length === 0 && <li className="text-sm text-slate-600">No one yet</li>}
                  </ul>
                  {hostToken && state.players.length < state.num_players && (
                    <Button size="sm" variant="outline" data-testid="add-bot" onClick={addBot}
                      className="mt-2 bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
                      <Plus className="w-3.5 h-3.5 mr-1" /> Add bot
                    </Button>
                  )}
                </div>
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
                  <div className={`hidden lg:block px-4 py-2 rounded-xl font-display font-semibold ${myTurn ? "bg-amber-400 text-stone-900" : "bg-slate-900 border border-slate-700 text-slate-200"}`} data-testid="turn-indicator">
                    {myTurn ? `Your pick! · Seat ${state.current_seat_index + 1}` : `${currentSeatName || "…"}'s pick`} · {state.pick_index}/{state.order_len}
                  </div>
                  {viewTabs([["pick", "Pick", LayoutGrid], ["table", "Draft Table", Table2], ["decks", "Decks", Eye]])}
                  <button data-testid="toggle-mini-table" onClick={() => setShowMiniTable((v) => !v)} className="hidden lg:flex text-xs px-3 py-1.5 rounded-full border border-slate-700 text-slate-300 hover:text-amber-300 items-center gap-1.5"><Table2 className="w-3.5 h-3.5" /> {showMiniTable ? "Hide peek" : "Table peek"}</button>
                </div>
                {view === "table" ? renderDraftTable() : view === "decks" ? renderDecks() : renderPickGrid()}
              </div>
            )}

            {state.status === "complete" && (
              <div data-testid="draft-complete">
                <div className="mb-4 flex items-center gap-3 flex-wrap">
                  <h2 className="font-display text-2xl font-bold flex items-center gap-2">Draft complete <PartyPopper className="w-6 h-6 text-amber-400" /></h2>
                  {viewTabs([["pick", "Results", ListChecks], ["table", "Draft Table", Table2], ["decks", "Decks", Eye]])}
                </div>
                {view === "table" ? renderDraftTable() : view === "decks" ? renderDecks() : renderResults()}
                <p className="text-xs text-slate-500 mt-4">Open any seat's deck in the builder to tweak and save it.</p>
              </div>
            )}
          </div>

          <aside className={`space-y-4 lg:sticky lg:top-20 self-start ${state.status === "lobby" ? "" : "hidden lg:block"}`} data-testid="draft-sidebar">
            {state.status !== "lobby" && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-2 h-[300px] 2xl:h-[440px] flex items-center justify-center overflow-hidden" data-testid="card-preview">
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
                <div className="max-h-72 overflow-y-auto pr-1">{renderFeedList()}</div>
              </div>
            )}

            <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 flex flex-col" data-testid="chat-panel">
              <h3 className="font-display font-semibold text-sm mb-3 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-amber-400" /> Table chat</h3>
              {renderChatBody()}
            </div>
          </aside>
        </div>
      </main>

      {state.status !== "lobby" && (
        <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-slate-800 bg-[#070c17]/95 backdrop-blur pb-[env(safe-area-inset-bottom)]" data-testid="mobile-bar">
          {state.status === "drafting" && (
            <div className={`text-center text-xs font-display font-semibold py-1 ${myTurn ? "bg-amber-400 text-stone-900" : "text-slate-300"}`} data-testid="mobile-turn">
              {myTurn ? `Your pick! · Seat ${state.current_seat_index + 1}` : `${currentSeatName || "…"}'s pick`} · {state.pick_index}/{state.order_len}
            </div>
          )}
          <div className="flex">
            {[
              ...(state.status === "drafting" ? [["queue", `Queue${queue.length ? ` (${queue.length})` : ""}`, Bookmark]] : []),
              ["feed", "Picks", ListChecks],
              ["chat", `Chat${(state.messages || []).length ? ` (${state.messages.length})` : ""}`, MessageSquare],
            ].map(([k, label, Icon]) => (
              <button key={k} data-testid={`mobile-${k}`} onClick={() => setSheet(k)} className="flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] text-slate-300 active:text-amber-300">
                <Icon className="w-5 h-5 text-amber-400" /> {label}
              </button>
            ))}
            <button data-testid="mobile-peek" onClick={() => setShowMiniTable(true)} className="flex-1 flex flex-col items-center gap-0.5 py-2 text-[11px] text-slate-300 active:text-amber-300">
              <Table2 className="w-5 h-5 text-amber-400" /> Peek
            </button>
          </div>
        </nav>
      )}

      {sheet && (
        <div className="lg:hidden fixed inset-0 z-50 bg-black/60 flex items-end" data-testid="mobile-sheet" onClick={() => setSheet(null)}>
          <div className="w-full max-h-[80vh] bg-[#0b111e] border-t border-slate-700 rounded-t-2xl flex flex-col pb-[env(safe-area-inset-bottom)]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 shrink-0">
              <span className="font-display font-semibold text-sm">{{ queue: "Pick queue", feed: "Pick feed", chat: "Table chat" }[sheet]}</span>
              <button data-testid="mobile-sheet-close" onClick={() => setSheet(null)} className="p-1 text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <div className="overflow-y-auto p-3">
              {sheet === "queue" && renderQueueList()}
              {sheet === "feed" && (pickFeed.length ? renderFeedList() : <p className="text-xs text-slate-600">No picks yet.</p>)}
              {sheet === "chat" && renderChatBody(true)}
            </div>
          </div>
        </div>
      )}

      {previewCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" data-testid="card-preview-dialog" onClick={() => setPreviewCard(null)}>
          <div className="w-full max-w-xs" onClick={(e) => e.stopPropagation()}>
            {(previewCard.image || previewCard.art_crop)
              ? <img src={previewCard.image || previewCard.art_crop} alt={previewCard.name} className="w-full rounded-xl" />
              : <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-center text-slate-200">{previewCard.name}</div>}
            <div className="flex gap-2 mt-3">
              {state.status === "drafting" && !pickedIds.has(previewCard.id) && cubeById[previewCard.id] && (
                <Button data-testid="preview-queue" variant="outline" onClick={() => toggleQueue(previewCard.id)} className="flex-1 bg-slate-900 border-slate-700 text-slate-200">
                  {queue.includes(previewCard.id) ? <><BookmarkCheck className="w-4 h-4 mr-1.5 text-amber-400" /> Queued</> : <><BookmarkPlus className="w-4 h-4 mr-1.5" /> Queue</>}
                </Button>
              )}
              <Button data-testid="preview-close" onClick={() => setPreviewCard(null)} className="flex-1 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Close</Button>
            </div>
          </div>
        </div>
      )}

      {showMiniTable && state.status !== "lobby" && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-start justify-center p-4 pt-20" data-testid="mini-table" onClick={() => setShowMiniTable(false)}>
          <div className="w-[min(98vw,1400px)] max-h-[86vh] bg-[#0b111e] border border-amber-400/40 rounded-xl shadow-2xl overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-800 shrink-0">
              <span className="text-sm font-display font-semibold flex items-center gap-2"><Table2 className="w-4 h-4 text-amber-400" /> Draft table — quick glance</span>
              <button data-testid="mini-table-close" onClick={() => setShowMiniTable(false)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <div className="overflow-auto p-3">{renderDraftTable(false, window.innerWidth >= 768)}</div>
          </div>
        </div>
      )}

      {reassignPick && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" data-testid="reassign-dialog" onClick={() => setReassignPick(null)}>
          <div className="bg-[#0b111e] border border-slate-700 rounded-2xl p-4 w-full max-w-md max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-display font-bold text-sm">Reassign pick #{reassignPick.order + 1} · {seatLabel(reassignPick.seat_index)}</h3>
              <button onClick={() => setReassignPick(null)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-slate-500 mb-2">Currently <span className="text-slate-300">{reassignPick.card?.name}</span>. Pick a still-available card to swap it to.</p>
            <Input data-testid="reassign-filter" value={reassignQuery} onChange={(e) => setReassignQuery(e.target.value)} placeholder="Filter cards..." className="h-9 bg-slate-950 border-slate-700 text-slate-100 mb-2" />
            <div className="overflow-y-auto space-y-0.5">
              {(draft.cube || []).filter((c) => (!pickedIds.has(c.id) || c.id === reassignPick.card?.id) && (!reassignQuery.trim() || c.name.toLowerCase().includes(reassignQuery.toLowerCase()))).slice(0, 200).map((c) => (
                <button key={c.id} data-testid={`reassign-option-${c.id}`} onClick={() => doReassign(c.id)} onMouseEnter={hoverIn(c)} onMouseLeave={hoverOut(c)}
                  className={`w-full flex items-center gap-2 text-left text-sm px-2 py-1.5 rounded hover:bg-amber-400/10 ${c.id === reassignPick.card?.id ? "text-amber-300" : "text-slate-200"}`}>
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${colorClass(c)}`} /><span className="truncate">{c.name}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

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
