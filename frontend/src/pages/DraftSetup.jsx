import React, { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Loader2, Shuffle, Users, RefreshCw, Plus, ArrowRight } from "lucide-react";
import { toast } from "sonner";

function parseList(text) {
  const t = text.trim();
  if (t.startsWith("[") || t.startsWith("{")) {
    try {
      const j = JSON.parse(t);
      const arr = Array.isArray(j) ? j : (j.cards || j.mainboard || []);
      return arr.map((x) => (typeof x === "string" ? x : x.name)).filter(Boolean);
    } catch { /* fall through */ }
  }
  return t.split(/\r?\n/).map((ln) => {
    let s = ln.split(",")[0].trim();           // CSV: first column
    s = s.replace(/^\d+\s*[xX]?\s+/, "");       // leading "4 " / "4x "
    s = s.replace(/\s*\([^)]*\)\s*[^\s]*/g, "").trim();
    return s;
  }).filter((s) => s && !/^(name|quantity|count)$/i.test(s));
}

export default function DraftSetup() {
  const navigate = useNavigate();
  const formRef = useRef(null);
  const [showForm, setShowForm] = useState(false);
  const [lobbies, setLobbies] = useState([]);
  const [loadingLobbies, setLoadingLobbies] = useState(true);

  const [name, setName] = useState("Cube Draft");
  const [players, setPlayers] = useState(4);       // people
  const [bots, setBots] = useState(0);
  const [seatsEach, setSeatsEach] = useState(2);
  const [pickCap, setPickCap] = useState(45);
  const [doubleAfter, setDoubleAfter] = useState(0);
  const [cubeText, setCubeText] = useState("");
  const [cubeCobra, setCubeCobra] = useState("");
  const [loading, setLoading] = useState(false);

  const nPeople = Number(players) || 0;
  const nBots = Number(bots) || 0;
  const nEach = Number(seatsEach) || 0;
  const totalSeats = (nPeople + nBots) * nEach;
  const seatsOk = nPeople >= 1 && nBots >= 0 && nEach >= 1 && nPeople + nBots <= 12 && totalSeats <= 64;

  const loadLobbies = async () => {
    try {
      const { data } = await api.get("/drafts/open");
      setLobbies(data.drafts || []);
    } catch { /* silent */ }
    finally { setLoadingLobbies(false); }
  };

  useEffect(() => {
    loadLobbies();
    const iv = setInterval(loadLobbies, 5000);
    return () => clearInterval(iv);
  }, []);

  const revealForm = () => {
    setShowForm(true);
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setCubeText(String(r.result || ""));
    r.readAsText(f);
  };

  const create = async () => {
    if (!seatsOk) { toast.error("Need at least 1 player, at most 12 players + bots, and 64 seats in total"); return; }
    setLoading(true);
    try {
      let names = [];
      if (cubeCobra.trim()) {
        const { data } = await api.get("/cube/cubecobra", { params: { id: cubeCobra.trim() } });
        names = data.names || [];
      } else {
        names = parseList(cubeText);
      }
      if (!names.length) { toast.error("Add a cube list or a CubeCobra link"); setLoading(false); return; }
      const uniq = Array.from(new Set(names));
      const { data: col } = await api.post("/cards/collection", { names: uniq });
      if (!col.cards?.length) { toast.error("No cards resolved from that cube"); setLoading(false); return; }
      if (col.not_found?.length) toast(`${col.not_found.length} card(s) not found and skipped`);
      const { data: draft } = await api.post("/drafts", {
        name: name.trim() || "Cube Draft",
        num_players: nPeople + nBots,
        num_bots: nBots,
        num_seats: totalSeats,
        double_draft_after: Number(doubleAfter) || 0,
        pick_cap: Number(pickCap) || 45,
        cube: col.cards,
      });
      if (draft.host_token) localStorage.setItem(`grim_draft_host_${draft.share_id}`, draft.host_token);
      toast.success(`Draft created with ${col.cards.length} cards`);
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
            <p className="text-sm text-slate-400 mt-1">Rotisserie-style. Host a table, share the link, and players claim seats by name — no login needed.</p>
          </div>
          <Button data-testid="host-your-own" onClick={showForm ? () => formRef.current?.scrollIntoView({ behavior: "smooth" }) : revealForm} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold shrink-0">
            <Plus className="w-4 h-4 mr-1.5" /> Host your own draft
          </Button>
        </div>

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
                    <span className="text-[11px] px-2 py-0.5 rounded-full border border-amber-400/30 text-amber-300 shrink-0">lobby</span>
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

        {/* Create form */}
        {showForm && (
          <section ref={formRef} className="mt-10 scroll-mt-6">
            <h2 className="font-display text-xl font-bold">Host a new table</h2>
            <div className="mt-4 space-y-5 rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
              <div>
                <Label className="text-slate-300">Draft name</Label>
                <Input data-testid="draft-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
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
                <div>
                  <Label className="text-slate-300">Picks / seat</Label>
                  <Input data-testid="draft-cap" type="number" min={1} value={pickCap} onChange={(e) => setPickCap(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
                <div>
                  <Label className="text-slate-300">Double after</Label>
                  <Input data-testid="draft-double" type="number" min={0} value={doubleAfter} onChange={(e) => setDoubleAfter(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
                </div>
              </div>
              <p className="text-xs text-slate-500">
                {seatsOk
                  ? <><span className="text-slate-300" data-testid="draft-seat-summary">{nPeople} {nPeople === 1 ? "player" : "players"}{nBots ? ` + ${nBots} ${nBots === 1 ? "bot" : "bots"}` : ""} · {totalSeats} seats ({nEach} each).</span> </>
                  : <span className="text-red-400">Need at least 1 player, at most 12 players + bots, and 64 seats in total. </span>}
                Bots are seated automatically and pick on their own turns. “Double after” = single picks per seat before each turn grants 2 (0 = off). Boundary seats get 4 in a row during the double phase.
              </p>

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
