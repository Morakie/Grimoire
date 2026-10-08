import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Loader2, Copy, X, Volume2, VolumeX, Bot, Lightbulb, Eye, ArrowLeft, ArrowRight, Timer, Package, Layers, MessageSquare, Hand } from "lucide-react";
import { toast } from "sonner";

const COLOR_ORDER = { W: 0, U: 1, B: 2, R: 3, G: 4 };
const cardCols = (c) => (c?.colors?.length ? c.colors : (c?.color_identity || []));
const colorKey = (c) => { const cols = cardCols(c); if (!cols.length) return 99; if (cols.length > 1) return 50 + cols.length; return COLOR_ORDER[cols[0]] ?? 90; };
const PIP = { W: "#f6f0d8", U: "#2f7fd1", B: "#4b3a63", R: "#e05a47", G: "#3f9b52" };

/**
 * Live view of a pack draft for the picking phase. The lobby and the end-of-draft results are shared
 * with rotisserie drafts and live in DraftRoom; this component gets the polled state from there.
 */
export default function PackDraftView({ shareId, draft, state, setState, me, hostToken, muted, onToggleMute, onBeep, onCancel, shareUrl }) {
  const cubeById = useMemo(() => { const m = {}; (draft?.cube || []).forEach((c) => (m[c.id] = c)); return m; }, [draft]);
  const my = state.my || {};
  const mySeats = me?.seats || [];
  const readySeats = mySeats.filter((s) => (my[String(s)]?.pack || []).length > 0);
  const [activeSeat, setActiveSeat] = useState(null);
  const seat = readySeats.includes(activeSeat) ? activeSeat : (readySeats[0] ?? mySeats[0] ?? null);
  const mine = seat != null ? my[String(seat)] : null;
  const pack = (mine?.pack || []).map((id) => cubeById[id]).filter(Boolean);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [hints, setHints] = useState(() => localStorage.getItem("grim_draft_hints") !== "off");
  const [suggestions, setSuggestions] = useState([]);
  const [panel, setPanel] = useState("picks");          // phones: "picks" | "chat"
  const [chatText, setChatText] = useState("");
  const [, setTick] = useState(0);
  const offsetRef = useRef(0);
  const prevReady = useRef(false);
  const packKey = (mine?.pack || []).join(",");

  // Correct for the difference between this device's clock and the server's.
  useEffect(() => {
    if (state.server_time) offsetRef.current = new Date(state.server_time).getTime() - Date.now();
  }, [state.server_time]);
  useEffect(() => { const iv = setInterval(() => setTick((t) => t + 1), 250); return () => clearInterval(iv); }, []);

  // A new pack arrived: clear the selection, beep if we were waiting.
  useEffect(() => {
    setSelected(null);
    const ready = readySeats.length > 0;
    if (ready && !prevReady.current && !muted) onBeep();
    prevReady.current = ready;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [packKey]);

  useEffect(() => {
    setSuggestions([]);
    if (!hints || seat == null || !pack.length || !me) return undefined;
    let alive = true;
    api.get(`/drafts/${shareId}/suggestions`, { params: { seat }, headers: { "X-Player-Token": me.player_token } })
      .then(({ data }) => { if (alive) setSuggestions(data.suggestions || []); }).catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hints, seat, packKey, shareId]);

  const remaining = mine?.deadline ? Math.max(0, (new Date(mine.deadline).getTime() - (Date.now() + offsetRef.current)) / 1000) : null;
  const pv = state.packs || {};
  const pickNo = mine && pack.length ? (pv.pack_size - pack.length + 1) : null;
  const seats = [...(state.seats || [])].sort((a, b) => a.index - b.index);
  const botSeats = new Set((state.players || []).filter((p) => p.is_bot).flatMap((p) => p.seats));
  const seatStatus = Object.fromEntries((pv.seats || []).map((s) => [s.seat, s]));
  const myPicks = (mine?.picks || []).map((id) => cubeById[id]).filter(Boolean);
  const allMyPicks = mySeats.flatMap((s) => (my[String(s)]?.picks || [])).map((id) => cubeById[id]).filter(Boolean);
  const colourCounts = Object.fromEntries(Object.keys(PIP).map((c) => [c, myPicks.filter((p) => cardCols(p).includes(c)).length]));

  const pick = async (card) => {
    if (!me || seat == null || busy || !card) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/drafts/${shareId}/pick`, { player_token: me.player_token, seat_index: seat, card_id: card.id });
      setState(data);
      setSelected(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Pick failed");
    } finally { setBusy(false); }
  };

  const hostPick = async (s) => {
    try { const { data } = await api.post(`/drafts/${shareId}/packs/autopick`, { host_token: hostToken, seat_index: s }); setState((st) => ({ ...st, ...data })); }
    catch (e) { toast.error(e.response?.data?.detail || "Couldn't pick for that seat"); }
  };

  const sendChat = async () => {
    const text = chatText.trim();
    if (!text || !me) return;
    setChatText("");
    try { const { data } = await api.post(`/drafts/${shareId}/chat`, { player_token: me.player_token, text }); setState((st) => ({ ...st, messages: data.messages })); }
    catch (e) { toast.error(e.response?.data?.detail || "Could not send"); }
  };

  const toggleHints = () => setHints((h) => { localStorage.setItem("grim_draft_hints", h ? "off" : "on"); return !h; });
  const passDir = pv.direction === "right" ? "right" : "left";
  const neighbour = (s, dir) => (s + (dir === "left" ? -1 : 1) + state.num_seats) % state.num_seats;   // who passes to s
  const fromSeat = seat != null ? neighbour(seat, passDir) : null;
  const fromName = fromSeat != null ? (state.seats.find((x) => x.index === fromSeat)?.player_name || `Seat ${fromSeat + 1}`) : "";
  const urgent = remaining != null && remaining <= 10;

  const timerPill = remaining != null && pack.length > 0 && (
    <span data-testid="pick-timer" className={`flex items-center gap-1 tabular-nums font-semibold px-2.5 py-1 rounded-full border ${urgent ? "border-red-400/60 text-red-300 bg-red-500/10" : "border-amber-400/40 text-amber-300"}`}>
      <Timer className="w-3.5 h-3.5" /> {Math.ceil(remaining)}s
    </span>
  );

  const sortedPicks = [...myPicks].sort((a, b) => colorKey(a) - colorKey(b) || (a.cmc || 0) - (b.cmc || 0));

  const picksPanel = (
    <div className="space-y-3" data-testid="my-picks">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-display font-semibold uppercase tracking-wide text-slate-300">Your picks <span className="text-slate-500">({allMyPicks.length})</span></h3>
        <div className="flex items-center gap-1.5">
          {Object.entries(colourCounts).filter(([, n]) => n).map(([c, n]) => (
            <span key={c} className="flex items-center gap-0.5 text-[11px] text-slate-400 tabular-nums"><span className="w-2.5 h-2.5 rounded-full border border-black/30" style={{ background: PIP[c] }} />{n}</span>
          ))}
        </div>
      </div>
      {sortedPicks.length === 0 ? <p className="text-xs text-slate-500">Nothing yet.</p> : (
        <ul className="space-y-0.5 max-h-[50vh] overflow-y-auto pr-1">
          {sortedPicks.map((c) => (
            <li key={c.id} className="flex items-center gap-2 text-[13px] text-slate-200">
              <span className="flex gap-0.5 shrink-0">{(cardCols(c).length ? cardCols(c) : ["C"]).map((x, i) => <span key={i} className="w-2 h-2 rounded-full" style={{ background: PIP[x] || "#9aa7b4" }} />)}</span>
              <span className="truncate">{c.name}</span>
              <span className="ml-auto text-[11px] text-slate-500 tabular-nums">{Math.round(c.cmc || 0)}</span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-slate-500">Other players' picks stay hidden until the draft ends.</p>
    </div>
  );

  const chatPanel = (
    <div className="space-y-2" data-testid="pack-chat">
      <h3 className="text-xs font-display font-semibold uppercase tracking-wide text-slate-300 flex items-center gap-1.5"><MessageSquare className="w-3.5 h-3.5 text-amber-400" /> Table chat</h3>
      <div className="max-h-56 overflow-y-auto space-y-1 text-[13px]">
        {(state.messages || []).length === 0 && <p className="text-xs text-slate-500">No messages yet.</p>}
        {(state.messages || []).map((m, i) => <div key={i}><span className="text-amber-300">{m.player_name || m.name}:</span> <span className="text-slate-300">{m.text}</span></div>)}
      </div>
      {me ? (
        <form onSubmit={(e) => { e.preventDefault(); sendChat(); }} className="flex gap-2">
          <Input value={chatText} onChange={(e) => setChatText(e.target.value)} maxLength={500} placeholder="Say something" className="h-8 bg-slate-950 border-slate-700 text-sm" data-testid="pack-chat-input" />
          <Button type="submit" size="sm" className="bg-amber-400 hover:bg-amber-500 text-stone-900">Send</Button>
        </form>
      ) : <p className="text-xs text-slate-500">Only players can chat.</p>}
    </div>
  );

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100 grim-grain">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-[#070c17]">
        <div className="max-w-7xl 2xl:max-w-[1760px] mx-auto px-3 sm:px-6 py-3 flex items-center gap-2 sm:gap-3 flex-wrap">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold hidden sm:inline">Grimoire</span></Link>
          <span className="text-slate-500">/</span>
          <span className="font-display font-semibold truncate min-w-0 max-w-[40vw] sm:max-w-none">{state.name}</span>
          <span className="text-xs px-2 py-0.5 rounded-full border border-slate-700 text-slate-300 flex items-center gap-1"><Package className="w-3 h-3" /> Pack draft</span>
          {!me && <span data-testid="spectating-badge" className="text-xs px-2 py-0.5 rounded-full border border-sky-400/30 text-sky-300 flex items-center gap-1"><Eye className="w-3 h-3" /> Watching</span>}
          <div className="ml-auto flex items-center gap-2">
            <Button size="sm" variant="outline" data-testid="mute-toggle" onClick={onToggleMute} title={muted ? "Unmute new-pack alert" : "Mute new-pack alert"} className="bg-slate-900 border-slate-700 text-slate-300">{muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}</Button>
            <Button size="sm" variant="outline" data-testid="draft-copy-link" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Link copied"); }} className="bg-slate-900 border-slate-700 text-slate-200"><Copy className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Copy link</span></Button>
            {hostToken && <Button size="sm" variant="outline" data-testid="close-table" onClick={onCancel} className="bg-slate-900 border-red-500/40 text-red-300 hover:bg-red-500/10"><X className="w-4 h-4 sm:mr-1.5" /><span className="hidden sm:inline">Close table</span></Button>}
          </div>
        </div>
      </header>

      <main className="max-w-7xl 2xl:max-w-[1760px] mx-auto px-3 sm:px-6 py-4 sm:py-6 pb-28 lg:pb-6">
        {/* Round + direction */}
        <div className="flex items-center gap-3 flex-wrap mb-4" data-testid="pack-round">
          <h1 className="font-display text-xl sm:text-2xl font-bold">Pack {pv.round} of {pv.rounds}</h1>
          <span className="text-sm text-slate-400 flex items-center gap-1">
            Passing {passDir} {passDir === "left" ? <ArrowLeft className="w-4 h-4" /> : <ArrowRight className="w-4 h-4" />}
          </span>
          {pickNo && <span className="text-sm text-slate-400">· Pick {pickNo} of {pv.pack_size}</span>}
          <span className="ml-auto hidden lg:flex">{timerPill}</span>
        </div>

        {/* Seats: who's holding packs */}
        <div className="flex gap-2 overflow-x-auto -mx-3 px-3 pb-1 mb-5 sm:mx-0 sm:px-0" data-testid="pack-seats">
          {seats.map((s) => {
            const st = seatStatus[s.index] || {};
            const isMine = mySeats.includes(s.index);
            return (
              <div key={s.index} data-testid={`pack-seat-${s.index}`}
                className={`min-w-[132px] shrink-0 rounded-xl border p-2.5 bg-slate-900/50 ${isMine ? "border-amber-400/60" : "border-slate-800"}`}>
                <div className="flex items-center justify-between text-[11px] text-slate-500">
                  <span>Seat {s.index + 1}{isMine ? " · you" : ""}</span>
                  <span className="tabular-nums text-amber-400">{st.picks || 0}/{state.pick_cap}</span>
                </div>
                <div className="font-display font-semibold truncate flex items-center gap-1 text-sm">
                  {botSeats.has(s.index) && <Bot className="w-3.5 h-3.5 text-amber-400 shrink-0" />} {s.player_name}
                </div>
                <div className="flex items-center gap-1 mt-1 h-3" title={`${st.waiting || 0} pack(s) waiting`}>
                  {Array.from({ length: Math.min(st.waiting || 0, 6) }).map((_, i) => <Package key={i} className={`w-3 h-3 ${i === 0 ? "text-amber-400" : "text-slate-500"}`} />)}
                  {!st.waiting && <span className="text-[10px] text-slate-600">waiting for a pack</span>}
                </div>
                {hostToken && !isMine && !botSeats.has(s.index) && st.waiting > 0 && (
                  <button type="button" onClick={() => hostPick(s.index)} data-testid={`host-pick-${s.index}`} className="mt-1 text-[10px] text-slate-400 hover:text-amber-300 flex items-center gap-1"><Hand className="w-3 h-3" /> Pick for them</button>
                )}
              </div>
            );
          })}
        </div>

        <div className="grid gap-6 items-start lg:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[minmax(0,1fr)_380px]">
          <section className="min-w-0" data-testid="current-pack">
            {readySeats.length > 1 && (
              <div className="flex gap-1 mb-3">
                {readySeats.map((s) => (
                  <button key={s} onClick={() => setActiveSeat(s)} className={`text-xs px-3 py-1 rounded-full border ${s === seat ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400"}`}>Seat {s + 1}</button>
                ))}
              </div>
            )}
            {!me ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-8 text-center text-sm text-slate-400">
                You're watching. Packs and picks are hidden until the draft ends.
              </div>
            ) : pack.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-10 text-center" data-testid="waiting-for-pack">
                <Loader2 className="w-6 h-6 text-amber-400 animate-spin mx-auto mb-3" />
                <p className="text-sm text-slate-300">Waiting for {fromName} to pass you a pack…</p>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs text-slate-500">{pack.length} cards · tap a card, then Pick (or double-click)</span>
                  <button type="button" data-testid="hints-toggle" onClick={toggleHints}
                    className={`ml-auto text-xs px-2.5 py-1 rounded-full border flex items-center gap-1 ${hints ? "border-amber-400 text-amber-300 bg-amber-400/10" : "border-slate-700 text-slate-400"}`}>
                    <Lightbulb className="w-3.5 h-3.5" /> Hints
                  </button>
                </div>
                <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-5 2xl:grid-cols-6 gap-2 sm:gap-3" data-testid="pack-cards">
                  {pack.map((c) => {
                    const sel = selected?.id === c.id;
                    const hint = hints && suggestions.includes(c.id);
                    return (
                      <button key={c.id} type="button" data-testid={`pack-card-${c.id}`} onClick={() => setSelected(c)} onDoubleClick={() => pick(c)}
                        className={`relative rounded-lg overflow-hidden border text-left transition-transform ${sel ? "border-amber-400 ring-2 ring-amber-400 -translate-y-1" : "border-slate-800 hover:border-slate-600"}`}>
                        <div className="aspect-[0.716] bg-slate-800">
                          {c.image ? <img src={c.image} alt={c.name} loading="lazy" className="w-full h-full object-cover" />
                            : <div className="w-full h-full flex items-center justify-center p-2 text-center text-xs text-slate-300">{c.name}</div>}
                        </div>
                        {hint && <span className="absolute top-1 left-1 bg-amber-400 text-stone-900 rounded-full p-1" title="Suggested pick"><Lightbulb className="w-3 h-3" /></span>}
                        {c.is_custom && <span className="absolute top-1 right-1 text-[10px] px-1.5 py-0.5 rounded bg-black/80 text-amber-300">custom</span>}
                      </button>
                    );
                  })}
                </div>
                <div className="hidden lg:flex items-center gap-3 mt-4">
                  <Button data-testid="confirm-pick" onClick={() => pick(selected)} disabled={!selected || busy} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : selected ? `Pick ${selected.name}` : "Choose a card"}
                  </Button>
                  {(mine?.waiting || 0) > 1 && <span className="text-xs text-slate-400">{mine.waiting - 1} more pack{mine.waiting > 2 ? "s" : ""} waiting after this one</span>}
                </div>
              </>
            )}
          </section>

          <aside className="hidden lg:block space-y-6 lg:sticky lg:top-20 self-start rounded-xl border border-slate-800 bg-[#0b111e] p-4">
            {me && picksPanel}
            {chatPanel}
          </aside>
        </div>

        {/* Phones: picks / chat under the pack */}
        <div className="lg:hidden mt-6 rounded-xl border border-slate-800 bg-[#0b111e] p-4">
          <div className="flex gap-1 mb-3">
            {[["picks", "Your picks", Layers], ["chat", "Chat", MessageSquare]].map(([k, label, Icon]) => (
              <button key={k} onClick={() => setPanel(k)} className={`flex items-center gap-1 text-xs px-3 py-1 rounded-full border ${panel === k ? "border-amber-400 text-amber-300" : "border-slate-700 text-slate-400"}`}><Icon className="w-3.5 h-3.5" /> {label}</button>
            ))}
          </div>
          {panel === "picks" && me ? picksPanel : chatPanel}
        </div>
      </main>

      {/* Phones: sticky pick bar */}
      {me && pack.length > 0 && (
        <div className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-slate-800 bg-[#070c17]/95 backdrop-blur px-3 py-2.5 flex items-center gap-2" data-testid="mobile-pick-bar">
          {timerPill}
          <span className="flex-1 min-w-0 truncate text-sm text-slate-300">{selected ? selected.name : "Tap a card"}</span>
          <Button data-testid="mobile-confirm-pick" onClick={() => pick(selected)} disabled={!selected || busy} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Pick"}
          </Button>
        </div>
      )}
    </div>
  );
}
