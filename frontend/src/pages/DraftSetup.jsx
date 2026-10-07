import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Sparkles, Loader2, Shuffle } from "lucide-react";
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
  const [name, setName] = useState("Cube Draft");
  const [players, setPlayers] = useState(4);
  const [seats, setSeats] = useState(8);
  const [pickCap, setPickCap] = useState(45);
  const [doubleAfter, setDoubleAfter] = useState(0);
  const [cubeText, setCubeText] = useState("");
  const [cubeCobra, setCubeCobra] = useState("");
  const [loading, setLoading] = useState(false);

  const seatsOk = players > 0 && seats % players === 0;

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setCubeText(String(r.result || ""));
    r.readAsText(f);
  };

  const create = async () => {
    if (!seatsOk) { toast.error("Seats must divide evenly among players"); return; }
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
        num_players: Number(players),
        num_seats: Number(seats),
        double_draft_after: Number(doubleAfter) || 0,
        pick_cap: Number(pickCap) || 45,
        cube: col.cards,
      });
      toast.success(`Draft created with ${col.cards.length} cards`);
      navigate(`/draft/${draft.share_id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not create draft");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-[#060a14] grim-grain text-slate-100">
      <header className="border-b border-slate-800">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2"><Sparkles className="w-5 h-5 text-amber-400" /><span className="font-display text-lg font-bold">Grimoire</span></Link>
          <Link to="/dashboard" className="text-sm text-slate-400 hover:text-white">My Decks</Link>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-10">
        <h1 className="font-display text-3xl font-bold flex items-center gap-2"><Shuffle className="w-7 h-7 text-amber-400" /> New Cube Draft</h1>
        <p className="text-sm text-slate-400 mt-1">Rotisserie-style. No login needed — players claim a seat by name. Seats split evenly across players.</p>

        <div className="mt-8 space-y-5 rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
          <div>
            <Label className="text-slate-300">Draft name</Label>
            <Input data-testid="draft-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <Label className="text-slate-300">Players</Label>
              <Input data-testid="draft-players" type="number" min={1} max={8} value={players} onChange={(e) => setPlayers(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100" />
            </div>
            <div>
              <Label className="text-slate-300">Seats</Label>
              <Input data-testid="draft-seats" type="number" min={players} value={seats} onChange={(e) => setSeats(e.target.value)} className={`mt-1.5 bg-slate-950 border-slate-700 text-slate-100 ${seatsOk ? "" : "ring-1 ring-red-500"}`} />
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
            {seatsOk ? `${seats / players} seat(s) per player.` : "Seats must divide evenly by players."} “Double after” = single picks per seat before each turn grants 2 (0 = off). Boundary seats get 4 in a row during the double phase.
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
      </main>
    </div>
  );
}
