import React, { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Loader2, Shuffle, Users, RefreshCw, Plus, ArrowRight, ImagePlus, X } from "lucide-react";
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

// Shrink an uploaded image to card size (488 px wide, like Scryfall's "normal" image) as a JPEG
// data URL, so a custom card adds roughly 50 KB to the draft instead of a multi-MB photo.
function resizeImage(file, width = 488) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, width / img.width);
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Not an image")); };
    img.src = url;
  });
}

const fileBaseName = (f) => f.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();

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
  const [customCards, setCustomCards] = useState([]);   // { id, name, image }

  const addCustomFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    const room = 30 - customCards.length;
    if (files.length > room) toast(`Only ${Math.max(room, 0)} more custom card(s) fit (30 max)`);
    const added = [];
    for (const f of files.slice(0, Math.max(room, 0))) {
      try {
        const image = await resizeImage(f);
        added.push({ id: Math.random().toString(36).slice(2, 10), name: fileBaseName(f) || "Custom card", image });
      } catch { toast.error(`${f.name} isn't an image`); }
    }
    setCustomCards((cs) => [...cs, ...added]);
  };
  const renameCustom = (id, name) => setCustomCards((cs) => cs.map((c) => (c.id === id ? { ...c, name } : c)));
  const removeCustom = (id) => setCustomCards((cs) => cs.filter((c) => c.id !== id));

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
      if (!names.length && !customCards.length) { toast.error("Add a cube list, a CubeCobra link or custom cards"); setLoading(false); return; }
      const uniq = Array.from(new Set(names));
      const col = uniq.length ? (await api.post("/cards/collection", { names: uniq })).data : { cards: [] };
      if (!col.cards?.length && !customCards.length) { toast.error("No cards resolved from that cube"); setLoading(false); return; }
      if (col.not_found?.length) toast(`${col.not_found.length} card(s) not found and skipped`);
      const customs = customCards.map((c) => ({ id: `custom-${c.id}`, name: c.name.trim() || "Custom card", image: c.image, is_custom: true }));
      const { data: draft } = await api.post("/drafts", {
        name: name.trim() || "Cube Draft",
        num_players: nPeople + nBots,
        num_bots: nBots,
        num_seats: totalSeats,
        double_draft_after: Number(doubleAfter) || 0,
        pick_cap: Number(pickCap) || 45,
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

              <div data-testid="custom-cards">
                <Label className="text-slate-300">Custom cards (optional)</Label>
                <p className="text-xs text-slate-500 mt-1">Upload card images (your own designs, proxies, inside jokes). They join the pool as tokens, sit at the top of the draft, and bots leave them alone.</p>
                {customCards.length > 0 && (
                  <div className="mt-3 grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-6 gap-3">
                    {customCards.map((c) => (
                      <div key={c.id} className="relative" data-testid={`custom-card-${c.id}`}>
                        <div className="aspect-[0.716] rounded-lg overflow-hidden border border-slate-700 bg-slate-800">
                          <img src={c.image} alt={c.name} className="w-full h-full object-cover" />
                        </div>
                        <button type="button" onClick={() => removeCustom(c.id)} title="Remove" data-testid={`custom-remove-${c.id}`}
                          className="absolute top-1 right-1 w-6 h-6 rounded bg-black/80 text-white hover:bg-red-500 flex items-center justify-center"><X className="w-3.5 h-3.5" /></button>
                        <Input value={c.name} onChange={(e) => renameCustom(c.id, e.target.value)} maxLength={80} aria-label="Card name"
                          className="mt-1.5 h-8 text-xs bg-slate-950 border-slate-700 text-slate-100" />
                      </div>
                    ))}
                  </div>
                )}
                <label className="mt-3 inline-flex items-center gap-2 text-sm px-3 h-9 rounded-md border border-slate-700 bg-slate-950 text-slate-300 cursor-pointer hover:text-white hover:border-slate-600">
                  <ImagePlus className="w-4 h-4" /> Add card images
                  <input type="file" accept="image/*" multiple onChange={addCustomFiles} className="hidden" data-testid="custom-card-file" />
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
