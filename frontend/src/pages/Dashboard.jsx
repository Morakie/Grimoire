import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Sparkles, Plus, MoreVertical, Copy, Trash2, Share2, Loader2, LogOut, Layers } from "lucide-react";
import { FORMATS, formatLabel, totalCount, MANA_COLORS } from "@/lib/mtg";
import { toast } from "sonner";

function colorIdentity(deck) {
  const set = new Set();
  [...deck.mainboard, ...deck.commander].forEach((c) => (c.color_identity || []).forEach((x) => set.add(x)));
  return ["W", "U", "B", "R", "G"].filter((c) => set.has(c));
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [decks, setDecks] = useState(null);
  const [newOpen, setNewOpen] = useState(false);
  const [name, setName] = useState("");
  const [format, setFormat] = useState("standard");
  const [creating, setCreating] = useState(false);
  const [deleteId, setDeleteId] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/decks");
      setDecks(data);
    } catch { setDecks([]); }
  };
  useEffect(() => { load(); }, []);

  const createDeck = async () => {
    if (!name.trim()) { toast.error("Name your deck"); return; }
    setCreating(true);
    try {
      const { data } = await api.post("/decks", { name: name.trim(), format, mainboard: [], sideboard: [], commander: [] });
      navigate(`/deck/${data.id}`);
    } catch { toast.error("Could not create deck"); }
    finally { setCreating(false); }
  };

  const clone = async (id) => {
    try {
      await api.post(`/decks/${id}/clone`);
      toast.success("Deck cloned");
      load();
    } catch { toast.error("Clone failed"); }
  };

  const confirmDelete = async () => {
    try {
      await api.delete(`/decks/${deleteId}`);
      toast.success("Deck deleted");
      setDeleteId(null);
      load();
    } catch { toast.error("Delete failed"); }
  };

  const copyShare = (shareId) => {
    navigator.clipboard.writeText(`${window.location.origin}/d/${shareId}`);
    toast.success("Share link copied");
  };

  return (
    <div className="min-h-screen bg-[#060a14] grim-grain text-slate-100">
      <header className="border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="logo">
            <Sparkles className="w-5 h-5 text-amber-400" />
            <span className="font-display text-lg font-bold">Grimoire</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-400 hidden sm:block">{user?.name}</span>
            <Button data-testid="logout-btn" variant="ghost" size="sm" onClick={() => { logout(); navigate("/"); }} className="text-slate-400 hover:text-white hover:bg-slate-800">
              <LogOut className="w-4 h-4 mr-1" /> Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-3xl font-bold">My Decks</h1>
            <p className="text-sm text-slate-400 mt-1">{decks ? `${decks.length} deck${decks.length === 1 ? "" : "s"}` : "Loading..."}</p>
          </div>
          <Button data-testid="new-deck-btn" onClick={() => { setName(""); setFormat("standard"); setNewOpen(true); }} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            <Plus className="w-4 h-4 mr-1" /> New Deck
          </Button>
        </div>

        {decks === null ? (
          <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>
        ) : decks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-800 py-20 flex flex-col items-center gap-3 text-slate-500" data-testid="empty-decks">
            <Layers className="w-12 h-12 text-slate-700" />
            <p>No decks yet. Create your first one.</p>
            <Button data-testid="empty-new-deck" onClick={() => setNewOpen(true)} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold mt-2">
              <Plus className="w-4 h-4 mr-1" /> New Deck
            </Button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="deck-grid">
            {decks.map((d) => {
              const ident = colorIdentity(d);
              const total = totalCount(d.mainboard) + totalCount(d.commander);
              const art = [...d.commander, ...d.mainboard].find((c) => c.art_crop)?.art_crop;
              return (
                <div key={d.id} className="group rounded-2xl border border-slate-800 bg-slate-900/50 overflow-hidden hover:border-amber-400/40 transition-colors" data-testid={`deck-card-${d.id}`}>
                  <div onClick={() => navigate(`/deck/${d.id}`)} className="h-28 bg-slate-800 cursor-pointer relative">
                    {art ? <img src={art} alt="" className="w-full h-full object-cover" /> : <div className="w-full h-full grim-grain" />}
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-900 to-transparent" />
                    <div className="absolute bottom-2 left-3 flex gap-1">
                      {ident.length ? ident.map((c) => <span key={c} className="w-4 h-4 rounded-full border border-black/30" style={{ background: MANA_COLORS[c].bg }} />) : <span className="w-4 h-4 rounded-full border border-black/30" style={{ background: MANA_COLORS.C.bg }} />}
                    </div>
                  </div>
                  <div className="p-4 flex items-start justify-between gap-2">
                    <div className="min-w-0 cursor-pointer" onClick={() => navigate(`/deck/${d.id}`)}>
                      <h3 className="font-display font-semibold truncate">{d.name}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">{formatLabel(d.format)} · {total} cards</p>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button data-testid={`deck-menu-${d.id}`} className="p-1.5 rounded hover:bg-slate-800 text-slate-400"><MoreVertical className="w-4 h-4" /></button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent className="bg-slate-900 border-slate-700 text-slate-200">
                        <DropdownMenuItem data-testid={`clone-${d.id}`} onClick={() => clone(d.id)} className="focus:bg-slate-800 cursor-pointer"><Copy className="w-4 h-4 mr-2" /> Clone</DropdownMenuItem>
                        <DropdownMenuItem data-testid={`share-${d.id}`} onClick={() => copyShare(d.share_id)} className="focus:bg-slate-800 cursor-pointer"><Share2 className="w-4 h-4 mr-2" /> Copy share link</DropdownMenuItem>
                        <DropdownMenuItem data-testid={`delete-${d.id}`} onClick={() => setDeleteId(d.id)} className="focus:bg-slate-800 cursor-pointer text-red-400"><Trash2 className="w-4 h-4 mr-2" /> Delete</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      <Dialog open={newOpen} onOpenChange={setNewOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100" data-testid="new-deck-dialog">
          <DialogHeader><DialogTitle className="font-display">New deck</DialogTitle></DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-slate-300">Deck name</Label>
              <Input data-testid="new-deck-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Mono-Red Aggro" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
            </div>
            <div>
              <Label className="text-slate-300">Format</Label>
              <Select value={format} onValueChange={setFormat}>
                <SelectTrigger data-testid="new-deck-format" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
                  {FORMATS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button data-testid="create-deck-submit" onClick={createDeck} disabled={creating} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create & build"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent className="bg-slate-900 border-slate-700 text-slate-100">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this deck?</AlertDialogTitle>
            <AlertDialogDescription className="text-slate-400">This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700">Cancel</AlertDialogCancel>
            <AlertDialogAction data-testid="confirm-delete" onClick={confirmDelete} className="bg-red-500 hover:bg-red-600 text-white">Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
