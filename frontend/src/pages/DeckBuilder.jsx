import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import CardSearchPanel from "@/components/CardSearchPanel";
import DeckWorkspace from "@/components/DeckWorkspace";
import DeckStats from "@/components/DeckStats";
import PrintingsDialog from "@/components/PrintingsDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ArrowLeft, Share2, Save, Loader2, Check, Copy, BarChart3 } from "lucide-react";
import { FORMATS, maxCopies, isBasicLand } from "@/lib/mtg";
import { useAuth } from "@/context/AuthContext";
import AuthDialog from "@/components/AuthDialog";
import { toast } from "sonner";

const GUEST_KEY = "grimoire_guest_deck";

const CATEGORIES = [
  { key: "mainboard", label: "Mainboard" },
  { key: "sideboard", label: "Sideboard" },
  { key: "commander", label: "Commander" },
];

export default function DeckBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const guest = !id;
  const [deck, setDeck] = useState(null);
  const [target, setTarget] = useState("mainboard");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [printingCtx, setPrintingCtx] = useState(null);
  const [mobileTab, setMobileTab] = useState("deck");
  const skipSave = useRef(true);
  const saveTimer = useRef(null);

  useEffect(() => {
    if (!id) {
      const saved = localStorage.getItem(GUEST_KEY);
      const base = saved
        ? JSON.parse(saved)
        : { id: null, name: "Untitled Deck", format: "standard", description: "", mainboard: [], sideboard: [], commander: [], share_id: null };
      setDeck(base);
      skipSave.current = true;
      return;
    }
    api.get(`/decks/${id}`)
      .then(({ data }) => { setDeck(data); skipSave.current = true; })
      .catch(() => { toast.error("Deck not found"); navigate("/dashboard"); });
  }, [id, navigate]);

  const showCommander = deck?.format === "commander";

  // Autosave
  useEffect(() => {
    if (!deck) return;
    if (skipSave.current) { skipSave.current = false; return; }
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => persist(deck, true), 1200);
    return () => saveTimer.current && clearTimeout(saveTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck]);

  const persist = async (d, silent = false) => {
    if (guest) {
      localStorage.setItem(GUEST_KEY, JSON.stringify(d));
      setSavedAt(Date.now());
      return;
    }
    setSaving(true);
    try {
      await api.put(`/decks/${id}`, {
        name: d.name, format: d.format, description: d.description || "",
        mainboard: d.mainboard, sideboard: d.sideboard, commander: d.commander,
      });
      setSavedAt(Date.now());
      if (!silent) toast.success("Deck saved");
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const createFromGuest = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/decks", {
        name: deck.name, format: deck.format, description: deck.description || "",
        mainboard: deck.mainboard, sideboard: deck.sideboard, commander: deck.commander,
      });
      localStorage.removeItem(GUEST_KEY);
      toast.success("Deck saved to your account");
      navigate(`/deck/${data.id}`);
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const handleSave = () => {
    if (guest) {
      if (!user) { setAuthOpen(true); return; }
      createFromGuest();
      return;
    }
    persist(deck);
  };

  const onAuthSuccess = () => { setAuthOpen(false); createFromGuest(); };

  const addCard = (card) => {
    setDeck((prev) => {
      const list = [...prev[target]];
      const idx = list.findIndex((c) => c.name === card.name);
      if (idx >= 0) {
        const ex = list[idx];
        const max = maxCopies(card, prev.format);
        const next = isBasicLand(card) ? ex.quantity + 1 : Math.min(ex.quantity + 1, max);
        list[idx] = { ...ex, quantity: next };
      } else {
        list.push({ ...card, quantity: 1 });
      }
      return { ...prev, [target]: list };
    });
  };

  const changeQty = (category, cardId, delta) => {
    setDeck((prev) => {
      let list = [...prev[category]];
      const idx = list.findIndex((c) => c.id === cardId);
      if (idx < 0) return prev;
      const card = list[idx];
      const max = maxCopies(card, prev.format);
      let next = card.quantity + delta;
      if (next <= 0) { list = list.filter((c) => c.id !== cardId); }
      else { next = isBasicLand(card) ? next : Math.min(next, max); list[idx] = { ...card, quantity: next }; }
      return { ...prev, [category]: list };
    });
  };

  const removeCard = (category, cardId) => {
    setDeck((prev) => ({ ...prev, [category]: prev[category].filter((c) => c.id !== cardId) }));
  };

  const reorder = (category, newList) => {
    setDeck((prev) => ({ ...prev, [category]: newList }));
  };

  const selectPrinting = (newCard) => {
    if (!printingCtx) return;
    const { category, card } = printingCtx;
    setDeck((prev) => ({
      ...prev,
      [category]: prev[category].map((c) => (c.id === card.id ? { ...newCard, quantity: c.quantity } : c)),
    }));
  };

  const findCategoryOf = (cardId) => {
    for (const cat of ["mainboard", "sideboard", "commander"]) {
      if (deck[cat].some((c) => c.id === cardId)) return cat;
    }
    return "mainboard";
  };

  const openPrintings = (card) => setPrintingCtx({ category: findCategoryOf(card.id), card });

  if (!deck) {
    return <div className="h-screen flex items-center justify-center bg-[#060a14]"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>;
  }

  const targets = CATEGORIES.filter((c) => c.key !== "commander" || showCommander);
  const analyticsCards = [...deck.mainboard, ...deck.commander];
  const shareUrl = `${window.location.origin}/d/${deck.share_id}`;

  return (
    <div className="h-screen flex flex-col bg-[#060a14] text-slate-100 overflow-hidden">
      {/* Header */}
      <header className="border-b border-slate-800 bg-[#070c17] shrink-0">
        <div className="px-4 py-3 flex items-center gap-3 flex-wrap">
          <Button data-testid="back-btn" variant="ghost" size="icon" onClick={() => navigate(user ? "/dashboard" : "/")} className="text-slate-400 hover:text-white hover:bg-slate-800 shrink-0">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <Input data-testid="deck-name-input" value={deck.name} onChange={(e) => setDeck({ ...deck, name: e.target.value })}
            className="w-48 sm:w-64 bg-transparent border-transparent hover:border-slate-700 focus-visible:border-slate-700 focus-visible:ring-0 text-lg font-display font-semibold px-2" />
          <Select value={deck.format} onValueChange={(v) => setDeck({ ...deck, format: v })}>
            <SelectTrigger data-testid="deck-format-select" className="w-44 h-9 bg-slate-900 border-slate-700 text-slate-200 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
              {FORMATS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-slate-500 hidden sm:flex items-center gap-1">
              {saving ? <><Loader2 className="w-3 h-3 animate-spin" /> Saving</> : savedAt ? <><Check className="w-3 h-3 text-green-400" /> {guest ? "Saved locally" : "Saved"}</> : (guest ? <span className="text-amber-400/80">Draft · not saved</span> : null)}
            </span>
            <Sheet>
              <SheetTrigger asChild>
                <Button data-testid="mobile-stats-btn" variant="outline" size="sm" className="xl:hidden bg-slate-900 border-slate-700 text-slate-200"><BarChart3 className="w-4 h-4" /></Button>
              </SheetTrigger>
              <SheetContent side="right" className="bg-[#070c17] border-slate-800 text-slate-100 overflow-y-auto w-[340px]">
                <SheetHeader><SheetTitle className="text-slate-100 font-display">Analytics</SheetTitle></SheetHeader>
                <div className="mt-4"><DeckStats cards={analyticsCards} /></div>
              </SheetContent>
            </Sheet>
            <Button data-testid="share-btn" variant="outline" size="sm" onClick={() => (guest ? handleSave() : setShareOpen(true))} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
              <Share2 className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Share</span>
            </Button>
            <Button data-testid="save-btn" size="sm" onClick={handleSave} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
              <Save className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Save</span>
            </Button>
          </div>
        </div>
        {/* Add target + mobile tabs */}
        <div className="px-4 pb-3 flex items-center gap-3 flex-wrap">
          <span className="text-xs text-slate-500">Add to:</span>
          <div className="flex rounded-lg border border-slate-700 overflow-hidden">
            {targets.map((t) => (
              <button key={t.key} data-testid={`target-${t.key}`} onClick={() => setTarget(t.key)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${target === t.key ? "bg-amber-400 text-stone-900" : "bg-slate-900 text-slate-300 hover:bg-slate-800"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex rounded-lg border border-slate-700 overflow-hidden lg:hidden ml-auto">
            {["search", "deck"].map((t) => (
              <button key={t} data-testid={`mobile-tab-${t}`} onClick={() => setMobileTab(t)}
                className={`px-3 py-1.5 text-xs font-medium capitalize transition-colors ${mobileTab === t ? "bg-slate-700 text-white" : "bg-slate-900 text-slate-300"}`}>{t}</button>
            ))}
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        <div className={`${mobileTab === "search" ? "flex" : "hidden"} lg:flex`}>
          <CardSearchPanel onAdd={addCard} targetLabel={targets.find((t) => t.key === target)?.label || "Mainboard"} />
        </div>
        <div className={`${mobileTab === "deck" ? "flex" : "hidden"} lg:flex flex-1 min-w-0`}>
          <div className="flex-1 flex flex-col min-w-0 bg-[#0a1120]">
            <DeckWorkspace deck={deck} format={deck.format} showCommander={showCommander}
              onQty={changeQty} onRemove={removeCard} onPrintings={openPrintings} onReorder={reorder} />
          </div>
          <aside className="w-80 border-l border-slate-800 bg-[#070c17] overflow-y-auto p-4 hidden xl:block" data-testid="stats-sidebar">
            <DeckStats cards={analyticsCards} />
          </aside>
        </div>
      </div>

      {/* Share dialog */}
      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent className="bg-slate-900 border-slate-700 text-slate-100" data-testid="share-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Share this deck</DialogTitle>
            <DialogDescription className="text-slate-400">Anyone with this link can view your decklist.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-2 mt-2">
            <Input data-testid="share-url" readOnly value={shareUrl} className="bg-slate-950 border-slate-700 text-slate-200" />
            <Button data-testid="copy-share-url" onClick={() => { navigator.clipboard.writeText(shareUrl); toast.success("Copied"); }} className="bg-amber-400 hover:bg-amber-500 text-stone-900 shrink-0"><Copy className="w-4 h-4" /></Button>
          </div>
        </DialogContent>
      </Dialog>

      <PrintingsDialog open={!!printingCtx} onOpenChange={(o) => !o && setPrintingCtx(null)} card={printingCtx?.card} onSelect={selectPrinting} />
      <AuthDialog open={authOpen} onOpenChange={setAuthOpen} onSuccess={onAuthSuccess} />
    </div>
  );
}
