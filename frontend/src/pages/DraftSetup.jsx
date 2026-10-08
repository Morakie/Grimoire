import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { resolveCube, readTextFile } from "@/lib/cube";
import CustomCardsPicker, { toCubeCustoms } from "@/components/CustomCardsPicker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Loader2, Shuffle, Users, RefreshCw, Plus, ArrowRight, Eye, Lock, KeyRound, Library, Info, Package, RotateCw } from "lucide-react";
import { toast } from "sonner";

export default function DraftSetup() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const formRef = useRef(null);
  const [showForm, setShowForm] = useState(false);
  const [lobbies, setLobbies] = useState([]);
  const [live, setLive] = useState([]);
  const [code, setCode] = useState("");
  const [finding, setFinding] = useState(false);
  const [isPrivate, setIsPrivate] = useState(false);
  const [loadingLobbies, setLoadingLobbies] = useState(true);

  const [name, setName] = useState("Cube Draft");
  const [players, setPlayers] = useState(4);       // people
  const [bots, setBots] = useState(0);
  const [seatsEach, setSeatsEach] = useState(1);
  const [doubleHelp, setDoubleHelp] = useState(false);
  const [mode, setMode] = useState("rotisserie");    // "rotisserie" | "packs"
  const [packCount, setPackCount] = useState(3);
  const [packSize, setPackSize] = useState(15);
  const [timerOn, setTimerOn] = useState(true);
  const [pickCap, setPickCap] = useState(45);
  const [doubleAfter, setDoubleAfter] = useState(0);
  const [cubeText, setCubeText] = useState("");
  const [cubeCobra, setCubeCobra] = useState("");
  const [loading, setLoading] = useState(false);
  const [customCards, setCustomCards] = useState([]);   // { id, name, image }
  // My Cubes (logged-in users): host from a saved cube, or save a new list while hosting.
  const [cubes, setCubes] = useState([]);
  const [cubeId, setCubeId] = useState("new");          // "new" or a saved cube id
  const [saveCube, setSaveCube] = useState(true);
  const [cubeName, setCubeName] = useState("");
  const savedCube = cubes.find((c) => c.id === cubeId);

  useEffect(() => {
    if (!user) return;
    api.get("/cubes").then(({ data }) => {
      setCubes(data.cubes || []);
      const wanted = params.get("cube");
      if (wanted && (data.cubes || []).some((c) => c.id === wanted)) {
        setCubeId(wanted);
        setShowForm(true);
        setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      }
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const nPeople = Number(players) || 0;
  const nBots = Number(bots) || 0;
  const nEach = Number(seatsEach) || 0;
  const totalSeats = (nPeople + nBots) * nEach;
  const seatsOk = nPeople >= 1 && nBots >= 0 && nEach >= 1 && nPeople + nBots <= 12 && totalSeats <= 64;

  const loadLobbies = async () => {
    try {
      const { data } = await api.get("/drafts/open");
      setLobbies(data.drafts || []);
      setLive(data.live || []);
    } catch { /* silent */ }
    finally { setLoadingLobbies(false); }
  };

  useEffect(() => {
    loadLobbies();
    const iv = setInterval(loadLobbies, 5000);
    return () => clearInterval(iv);
  }, []);

  const joinByCode = async (e) => {
    e.preventDefault();
    const c = code.trim();
    if (!c) return;
    setFinding(true);
    try {
      const { data } = await api.get(`/drafts/code/${encodeURIComponent(c)}`);
      navigate(`/draft/${data.share_id}`);
    } catch { toast.error("No table with that code"); }
    finally { setFinding(false); }
  };

  const revealForm = () => {
    setShowForm(true);
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (f) setCubeText(await readTextFile(f));
  };

  const create = async () => {
    if (!seatsOk) { toast.error("Need at least 1 player, at most 12 players + bots, and 64 seats in total"); return; }
    setLoading(true);
    try {
      const customs = toCubeCustoms(customCards);
      let cards;
      if (savedCube) {
        const { data } = await api.get(`/cubes/${savedCube.id}`);
        cards = data.cards || [];
      } else {
        if (!cubeCobra.trim() && !cubeText.trim() && !customs.length) { toast.error("Add a cube list, a CubeCobra link or custom cards"); setLoading(false); return; }
        const res = (cubeCobra.trim() || cubeText.trim()) ? await resolveCube({ cubeCobra, text: cubeText }) : { cards: [], notFound: [] };
        if (!res.cards.length && !customs.length) { toast.error("No cards resolved from that cube"); setLoading(false); return; }
        if (res.notFound.length) toast(`${res.notFound.length} card(s) not found and skipped`);
        cards = res.cards;
        if (user && saveCube) {
          try {
            const label = cubeName.trim() || name.trim() || "My Cube";
            await api.post("/cubes", { name: label, cubecobra_id: res.cubecobraId, cards: [...customs, ...cards] });
            toast.success(`Saved "${label}" to My Cubes`);
          } catch { toast.error("Couldn't save the cube, but the draft will still be created"); }
        }
      }
      // A saved cube already carries its own custom cards; extra uploads are added for this draft only.
      const col = { cards: savedCube ? [...cards.filter((c) => c.is_custom), ...cards.filter((c) => !c.is_custom)] : cards };
      const { data: draft } = await api.post("/drafts", {
        name: name.trim() || "Cube Draft",
        num_players: nPeople + nBots,
        num_bots: nBots,
        num_seats: totalSeats,
        double_draft_after: Number(doubleAfter) || 0,
        pick_cap: Number(pickCap) || 45,
        private: isPrivate,
        mode,
        ...(mode === "packs" ? { pack_count: Number(packCount) || 3, pack_size: Number(packSize) || 15, timer: timerOn ? "shrinking" : "off" } : {}),
        cube: [...customs, ...col.cards],
      });
      if (draft.host_token) localStorage.setItem(`grim_draft_host_${draft.share_id}`, draft.host_token);
      toast.success(`Draft created with ${col.cards.length + customs.length} cards`);
      navigate(`/draft/${draft.share_id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not create draft");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#060a14] grim-grain text-slate-100">
      <header className="border-b border-slate-800">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <Link to="/dashboard" className="text-sm text-slate-400 hover:text-white">My Decks</Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {/* Host your own — top */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="font-display text-3xl font-bold flex items-center gap-2"><Shuffle className="w-7 h-7 text-amber-400" /> Cube Draft</h1>
            <p className="text-sm text-slate-400 mt-1">Rotisserie or pack drafts. Host a table, share the link, and players claim seats by name. No login needed.</p>
          </div>
          <Button data-testid="host-your-own" onClick={showForm ? () => formRef.current?.scrollIntoView({ behavior: "smooth" }) : revealForm} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0">
            <Plus className="w-4 h-4 mr-1.5" /> Host your own draft
          </Button>
        </div>

        <form onSubmit={joinByCode} className="mt-6 flex items-center gap-2 max-w-sm" data-testid="join-by-code">
          <div className="relative flex-1">
            <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <Input data-testid="join-code-input" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="Have a table code?" maxLength={12}
              autoCapitalize="characters" autoComplete="off" spellCheck={false}
              className="pl-9 bg-slate-950 border-slate-700 text-slate-100 font-mono tracking-widest placeholder:font-sans placeholder:tracking-normal focus-visible:ring-amber-400" />
          </div>
          <Button type="submit" data-testid="join-code-submit" disabled={finding || !code.trim()} variant="outline" className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
            {finding ? <Loader2 className="w-4 h-4 animate-spin" /> : "Join"}
          </Button>
        </form>

        {/* Open tables */}
        <section className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-amber-400" />
              <h2 className="font-display text-lg font-bold">Open tables</h2>
            </div>
            <button data-testid="refresh-lobbies" onClick={loadLobbies} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-amber-300 transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${loadingLobbies ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>

          {loadingLobbies ? (
            <div className="text-sm text-slate-500" data-testid="lobbies-loading">Loading tables…</div>
          ) : lobbies.length === 0 ? (
            <div data-testid="lobbies-empty" className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center">
              <p className="text-sm text-slate-400">No open tables right now — be the first to host one.</p>
              <Button data-testid="empty-host-draft" onClick={revealForm} className="mt-4 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
                <Plus className="w-4 h-4 mr-1.5" /> Host your own draft
              </Button>
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="lobby-list">
              {lobbies.map((l) => (
                <div key={l.share_id} data-testid={`lobby-${l.share_id}`} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5 hover:border-amber-400/40 transition-colors flex flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display font-semibold truncate">{l.name}</h3>
                    <span className="text-[11px] px-2 py-0.5 rounded-full border border-amber-400/30 text-amber-300 shrink-0">{l.mode === "packs" ? "pack draft" : "rotisserie"}</span>
                  </div>
                  <div className="mt-2 text-xs text-slate-400 space-y-0.5">
                    <div>{l.players_joined}/{l.num_players} players joined</div>
                    <div>{l.seats_claimed}/{l.num_seats} seats claimed · {l.cube_size} cards</div>
                  </div>
                  <Button data-testid={`join-lobby-${l.share_id}`} onClick={() => navigate(`/draft/${l.share_id}`)} className="mt-4 w-full bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
                    Join table <ArrowRight className="w-4 h-4 ml-1.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </section>

        {live.length > 0 && (
          <section className="mt-10" data-testid="live-tables">
            <div className="flex items-center gap-2 mb-4">
              <Eye className="w-5 h-5 text-amber-400" />
              <h2 className="font-display text-lg font-bold">Drafting now</h2>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {live.map((l) => (
                <div key={l.share_id} data-testid={`live-${l.share_id}`} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5 flex flex-col">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display font-semibold truncate">{l.name}</h3>
                    <span className="text-[11px] px-2 py-0.5 rounded-full border border-green-400/30 text-green-300 shrink-0">live</span>
                  </div>
                  <div className="mt-2 text-xs text-slate-400">{l.players_joined} players · {l.num_seats} seats · {l.picks_made} picks made</div>
                  <Button data-testid={`watch-${l.share_id}`} variant="outline" onClick={() => navigate(`/draft/${l.share_id}`)} className="mt-4 w-full bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
                    <Eye className="w-4 h-4 mr-1.5" /> Watch
                  </Button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Create form */}
        {showForm && (
          <section ref={formRef} className="mt-10 scroll-mt-6">
            <h2 className="font-display text-xl font-bold">Host a new table</h2>
            <div className="mt-4 space-y-5 rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
              <div>
                <Label className="text-slate-300">Draft name</Label>
                <Input data-testid="draft-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
              </div>
              <div>
                <Label className="text-slate-300">Format</Label>
                <div className="mt-1.5 grid grid-cols-2 gap-2 max-w-md" role="radiogroup" data-testid="draft-mode">
                  {[["rotisserie", "Rotisserie", "Take turns picking from the whole cube", RotateCw], ["packs", "Pack draft", "Open packs, pick one, pass the rest", Package]].map(([k, label, desc, Icon]) => (
                    <button key={k} type="button" role="radio" aria-checked={mode === k} data-testid={`draft-mode-${k}`} onClick={() => setMode(k)}
                      className={`text-left rounded-lg border p-3 transition-colors ${mode === k ? "border-amber-400 bg-amber-400/10" : "border-slate-700 bg-slate-950 hover:border-slate-600"}`}>
                      <span className={`flex items-center gap-1.5 text-sm font-semibold ${mode === k ? "text-amber-300" : "text-slate-200"}`}><Icon className="w-4 h-4" /> {label}</span>
                      <span className="block text-[11px] text-slate-500 mt-0.5">{desc}</span>
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
                <div>
                  <Label className="text-slate-300">Players</Label>
                  <Input data-testid="draft-players" type="number" min={1} max={12} value={players} onChange={(e) => setPlayers(e.target.value)} className={`mt-1.5 bg-slate-950 border-slate-700 text-slate-100 ${seatsOk ? "" : "ring-1 ring-red-500"}`} />
                </div>
                <div>
                  <Label className="text-slate-300">Bots</Label>
                  <Input data-testid="draft-bots" type="number" min={0} max={11} value={bots} onChange={(e) => setBots(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                <div>
                  <Label className="text-slate-300">Seats each</Label>
                  <Input data-testid="draft-seats-each" type="number" min={1} value={seatsEach} onChange={(e) => setSeatsEach(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                {mode === "packs" ? (<>
                <div>
                  <Label className="text-slate-300">Packs each</Label>
                  <Input data-testid="draft-pack-count" type="number" min={1} max={6} value={packCount} onChange={(e) => setPackCount(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                <div>
                  <Label className="text-slate-300">Cards / pack</Label>
                  <Input data-testid="draft-pack-size" type="number" min={3} max={20} value={packSize} onChange={(e) => setPackSize(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                </>) : (<>
                <div>
                  <Label className="text-slate-300">Picks / seat</Label>
                  <Input data-testid="draft-cap" type="number" min={1} value={pickCap} onChange={(e) => setPickCap(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                <div>
                  <div className="relative flex items-center gap-1.5">
                    <Label className="text-slate-300">Double after</Label>
                    <button type="button" data-testid="draft-double-info" aria-label="What is Double after?" aria-expanded={doubleHelp}
                      title="Picks are doubled after this pick number"
                      onClick={() => setDoubleHelp((v) => !v)} onBlur={() => setDoubleHelp(false)}
                      className="text-slate-500 hover:text-amber-300 focus-visible:text-amber-300 outline-none">
                      <Info className="w-3.5 h-3.5" />
                    </button>
                    {doubleHelp && (
                      <div role="tooltip" data-testid="draft-double-help"
                        className="absolute right-0 sm:right-auto sm:left-0 top-6 z-20 w-64 rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs text-slate-300 shadow-xl leading-relaxed">
                        Picks are doubled after pick #{Number(doubleAfter) > 0 ? Number(doubleAfter) : "N"}. Each seat makes that many single picks, then every turn takes <span className="text-amber-300">2 cards</span>. The seats at each end of the table get 4 in a row as the order turns around. <span className="text-slate-400">0 = never double.</span>
                      </div>
                    )}
                  </div>
                  <Input data-testid="draft-double" type="number" min={0} value={doubleAfter} onChange={(e) => setDoubleAfter(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                </>)}
              </div>
              <p className="text-xs text-slate-500">
                {seatsOk
                  ? <><span className="text-slate-300" data-testid="draft-seat-summary">{nPeople} {nPeople === 1 ? "player" : "players"}{nBots ? ` + ${nBots} ${nBots === 1 ? "bot" : "bots"}` : ""} · {totalSeats} seats ({nEach} each).</span> </>
                  : <span className="text-red-400">Need at least 1 player, at most 12 players + bots, and 64 seats in total. </span>}
                {mode === "packs"
                  ? <>Everyone picks at once and passes left, right, left. Needs <span className="text-slate-300" data-testid="pack-cards-needed">{totalSeats * (Number(packCount) || 0) * (Number(packSize) || 0)}</span> cards from the cube.</>
                  : <>Bots are seated automatically and pick on their own turns.{Number(doubleAfter) > 0 ? ` Picks double after pick #${Number(doubleAfter)}.` : ""}</>}
              </p>
              {mode === "packs" && (
                <label className="flex items-start gap-3 cursor-pointer" data-testid="draft-timer">
                  <input type="checkbox" checked={timerOn} onChange={(e) => setTimerOn(e.target.checked)} className="mt-1 w-4 h-4 accent-amber-400" data-testid="draft-timer-toggle" />
                  <span>
                    <span className="text-sm text-slate-200">Pick timer</span>
                    <span className="block text-xs text-slate-500 mt-0.5">Shrinks as the pack gets smaller: about 80 seconds for a full 15-card pack, down to 10 for the last card. When it runs out, the best card for your deck is picked for you.</span>
                  </span>
                </label>
              )}

              {user && cubes.length > 0 && (
                <div data-testid="saved-cube-picker">
                  <Label className="text-slate-300 flex items-center gap-1.5"><Library className="w-3.5 h-3.5 text-amber-400" /> Cube</Label>
                  <Select value={cubeId} onValueChange={setCubeId}>
                    <SelectTrigger data-testid="saved-cube-select" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
                      <SelectItem value="new">New list (CubeCobra link or paste)</SelectItem>
                      {cubes.map((c) => <SelectItem key={c.id} value={c.id}>{c.name} · {c.card_count} cards</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {savedCube && (
                    <p className="text-xs text-slate-500 mt-1.5" data-testid="saved-cube-summary">
                      {savedCube.card_count} cards{savedCube.custom_count ? `, ${savedCube.custom_count} custom` : ""}. Manage it under My Decks → Cubes.
                    </p>
                  )}
                </div>
              )}

              {!savedCube && (<>
              <div>
                <Label className="text-slate-300">CubeCobra link or ID</Label>
                <Input data-testid="draft-cubecobra" value={cubeCobra} onChange={(e) => setCubeCobra(e.target.value)} placeholder="https://cubecobra.com/cube/overview/xxxx" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
              </div>
              <div className="text-center text-xs text-slate-600">— or paste / upload a list (txt, csv, json) —</div>
              <div>
                <Textarea data-testid="draft-cube-text" value={cubeText} onChange={(e) => setCubeText(e.target.value)} placeholder={"Sol Ring\nLightning Bolt\nCounterspell\n..."} className="min-h-[160px] bg-slate-950 border-slate-700 text-slate-100 font-mono text-sm focus-visible:ring-amber-400" />
                <label className="inline-flex items-center gap-2 text-sm text-slate-300 mt-2 cursor-pointer hover:text-white">
                  Upload file <input type="file" accept=".txt,.csv,.json" onChange={onFile} className="hidden" data-testid="draft-cube-file" />
                </label>
              </div>
              {user ? (
                <div className="flex items-center gap-3 flex-wrap" data-testid="save-cube">
                  <label className="flex items-center gap-2 text-sm text-slate-200 cursor-pointer">
                    <input type="checkbox" checked={saveCube} onChange={(e) => setSaveCube(e.target.checked)} className="w-4 h-4 accent-amber-400" data-testid="save-cube-toggle" />
                    Save to My Cubes as
                  </label>
                  <Input data-testid="save-cube-name" value={cubeName} onChange={(e) => setCubeName(e.target.value)} placeholder={name.trim() || "My Cube"} disabled={!saveCube} maxLength={120}
                    className="h-8 w-56 bg-slate-950 border-slate-700 text-slate-100 text-sm disabled:opacity-50" />
                </div>
              ) : (
                <p className="text-xs text-slate-500"><Link to="/login" className="text-amber-400 hover:underline">Log in</Link> to save cubes for next time.</p>
              )}
              </>)}

              <label className="flex items-start gap-3 cursor-pointer" data-testid="draft-private">
                <input type="checkbox" checked={isPrivate} onChange={(e) => setIsPrivate(e.target.checked)} className="mt-1 w-4 h-4 accent-amber-400" data-testid="draft-private-toggle" />
                <span>
                  <span className="text-sm text-slate-200 flex items-center gap-1.5"><Lock className="w-3.5 h-3.5 text-amber-400" /> Private table</span>
                  <span className="block text-xs text-slate-500 mt-0.5">Hidden from Open tables and Drafting now. Players join with the invite link or the table code.</span>
                </span>
              </label>

              <div data-testid="custom-cards">
                <Label className="text-slate-300">Custom cards (optional)</Label>
                <p className="text-xs text-slate-500 mt-1">Upload card images (your own designs, proxies, inside jokes). They join the pool as tokens, sit at the top of the draft, and bots leave them alone.{savedCube ? " These are added to this draft only; the saved cube keeps its own." : ""}</p>
                <CustomCardsPicker value={customCards} onChange={setCustomCards} />
              </div>

              <Button data-testid="draft-create-submit" onClick={create} disabled={loading} className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create draft & get link"}
              </Button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
