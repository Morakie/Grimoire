import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import CardSearchBar from "@/components/CardSearchBar";
import DeckBoard from "@/components/DeckBoard";
import DeckStats from "@/components/DeckStats";
import PrimerEditor from "@/components/Primer";
import BasicLandsDialog from "@/components/BasicLandsDialog";
import CommanderCheck, { CommanderBadge, useCommanderCheck } from "@/components/CommanderCheck";
import PrintingsDialog from "@/components/PrintingsDialog";
import ImportDialog from "@/components/ImportDialog";
import ExportDialog, { buildExport } from "@/components/ExportDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ArrowLeft, Share2, Save, Loader2, Check, Copy, BarChart3, Upload, Download, ListChecks, Layers, BookOpen, Mountain } from "lucide-react";
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
  const location = useLocation();
  const { user } = useAuth();
  // Back returns to the previous page inside Grimoire. When the deck was opened directly (new tab,
  // refresh, a pasted link) there is no previous Grimoire page, so go to My Decks (or home for guests).
  const goBack = () => {
    if (location.key !== "default" && window.history.length > 1) navigate(-1);
    else navigate(user ? "/dashboard" : "/");
  };
  const guest = !id;
  const [deck, setDeck] = useState(null);
  const [target, setTarget] = useState("mainboard");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [printingCtx, setPrintingCtx] = useState(null);
  const [statsOpen, setStatsOpen] = useState(false);
  const [basicsOpen, setBasicsOpen] = useState(false);
  const [pane, setPane] = useState("deck");   // "deck" | "primer"
  const sidebarRef = useRef(null);
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
  const commanderCheck = useCommanderCheck(deck, showCommander);
  // The badge opens the full check: the sidebar on wide screens, the analytics sheet otherwise.
  const openCheck = () => {
    if (window.matchMedia && window.matchMedia("(min-width: 1280px)").matches && sidebarRef.current) sidebarRef.current.scrollTo({ top: 0, behavior: "smooth" });
    else setStatsOpen(true);
  };

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
      // Replace the guest page in history, so Back doesn't land on the now-empty guest builder.
      navigate(`/deck/${data.id}`, { replace: true });
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

  const onCardsChange = (cats) => setDeck((prev) => ({ ...prev, ...cats }));

  const applyImport = (imported, { replace = false, format } = {}) => {
    setDeck((prev) => {
      if (format) prev = { ...prev, format }; // e.g. switch to Commander when a commander was detected
      if (replace) {
        // Keep per-card extras (e.g. custom group placement) for cards that survived the edit.
        const old = {};
        [...prev.mainboard, ...prev.sideboard, ...prev.commander].forEach((c) => { old[c.id] = c; });
        const keep = (list) => list.map((c) => (old[c.id] ? { ...old[c.id], ...c } : c));
        return { ...prev, mainboard: keep(imported.mainboard), sideboard: keep(imported.sideboard), commander: keep(imported.commander) };
      }
      const merge = (existing, incoming) => {
        const list = [...existing];
        incoming.forEach((card) => {
          const idx = list.findIndex((c) => c.name.toLowerCase() === card.name.toLowerCase());
          if (idx >= 0) list[idx] = { ...list[idx], quantity: list[idx].quantity + card.quantity };
          else list.push(card);
        });
        return list;
      };
      return {
        ...prev,
        mainboard: merge(prev.mainboard, imported.mainboard),
        sideboard: merge(prev.sideboard, imported.sideboard),
        commander: merge(prev.commander, imported.commander),
      };
    });
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
        <div className="px-3 sm:px-6 lg:px-10 py-2 sm:py-3 flex items-center gap-2 sm:gap-3 flex-wrap">
          <Button data-testid="back-btn" variant="ghost" size="icon" onClick={goBack} title="Back" className="text-slate-400 hover:text-white hover:bg-slate-800 shrink-0">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <Input data-testid="deck-name-input" value={deck.name} onChange={(e) => setDeck({ ...deck, name: e.target.value })}
            className="flex-1 min-w-[120px] max-w-[200px] sm:max-w-xs bg-transparent border-transparent hover:border-slate-700 focus-visible:border-slate-700 focus-visible:ring-0 text-base sm:text-lg font-display font-semibold px-2" />
          <Select value={deck.format} onValueChange={(v) => setDeck({ ...deck, format: v })}>
            <SelectTrigger data-testid="deck-format-select" className="w-36 sm:w-44 h-9 bg-slate-900 border-slate-700 text-slate-200 text-sm shrink-0"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
              {FORMATS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {showCommander && <CommanderBadge check={commanderCheck} onClick={openCheck} />}
          <div className="flex items-center gap-2 ml-auto flex-wrap justify-end">
            <span className="text-xs text-slate-500 hidden md:flex items-center gap-1">
              {saving ? <><Loader2 className="w-3 h-3 animate-spin" /> Saving</> : savedAt ? <><Check className="w-3 h-3 text-green-400" /> {guest ? "Saved locally" : "Saved"}</> : (guest ? <span className="text-amber-400/80">Draft · not saved</span> : null)}
            </span>
            <Button data-testid="import-btn" variant="outline" size="sm" onClick={() => setImportOpen(true)} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
              <Upload className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Import</span>
            </Button>
            <Button data-testid="bulk-edit-btn" variant="outline" size="sm" onClick={() => setBulkOpen(true)} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
              <ListChecks className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Bulk edit</span>
            </Button>
            <Button data-testid="basic-lands-btn" variant="outline" size="sm" onClick={() => setBasicsOpen(true)} title="Add basic lands" className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
              <Mountain className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Basics</span>
            </Button>
            <Button data-testid="export-btn" variant="outline" size="sm" onClick={() => setExportOpen(true)} className="bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800">
              <Download className="w-4 h-4 sm:mr-1" /> <span className="hidden sm:inline">Export</span>
            </Button>
            <Sheet open={statsOpen} onOpenChange={setStatsOpen}>
              <SheetTrigger asChild>
                <Button data-testid="mobile-stats-btn" variant="outline" size="sm" className="xl:hidden bg-slate-900 border-slate-700 text-slate-200"><BarChart3 className="w-4 h-4" /></Button>
              </SheetTrigger>
              <SheetContent side="right" className="bg-[#070c17] border-slate-800 text-slate-100 overflow-y-auto w-[340px]">
                <SheetHeader><SheetTitle className="text-slate-100 font-display">Analytics</SheetTitle></SheetHeader>
                <div className="mt-4 space-y-5">
                  {showCommander && <CommanderCheck check={commanderCheck} />}
                  <DeckStats cards={analyticsCards} />
                </div>
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
        {/* Find & add cards */}
        <div className="px-3 sm:px-6 lg:px-10 pb-2 sm:pb-3">
          <CardSearchBar onAdd={addCard} target={target} setTarget={setTarget} targets={targets} />
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col min-w-0 bg-[#0a1120]">
          <div className="flex items-center gap-1 px-3 sm:px-6 lg:px-10 pt-2 border-b border-slate-800 shrink-0" role="tablist" data-testid="deck-pane-tabs">
            {[["deck", "Deck", Layers], ["primer", "Primer", BookOpen]].map(([k, label, Icon]) => (
              <button key={k} role="tab" aria-selected={pane === k} data-testid={`pane-${k}`} onClick={() => setPane(k)}
                className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold border-b-2 -mb-px transition-colors ${pane === k ? "border-amber-400 text-amber-300" : "border-transparent text-slate-400 hover:text-slate-200"}`}>
                <Icon className="w-3.5 h-3.5" /> {label}
                {k === "primer" && deck.description?.trim() && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" aria-label="has primer" />}
              </button>
            ))}
          </div>
          {pane === "deck" ? (
            <DeckBoard deck={deck} format={deck.format} showCommander={showCommander}
              onQty={changeQty} onRemove={removeCard} onPrintings={openPrintings} onCardsChange={onCardsChange} />
          ) : (
            <div className="flex-1 overflow-y-auto">
              <PrimerEditor value={deck.description || ""} onChange={(v) => setDeck((d) => ({ ...d, description: v }))}
                deckCards={[...deck.commander, ...deck.mainboard, ...deck.sideboard]} />
            </div>
          )}
        </div>
        <aside ref={sidebarRef} className="w-80 border-l border-slate-800 bg-[#070c17] overflow-y-auto p-4 hidden xl:block space-y-5" data-testid="stats-sidebar">
          {showCommander && <CommanderCheck check={commanderCheck} />}
          <DeckStats cards={analyticsCards} />
        </aside>
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
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onImport={applyImport} format={deck.format} />
      <ImportDialog open={bulkOpen} onOpenChange={setBulkOpen} onImport={applyImport} mode="replace" format={deck.format}
        initialText={bulkOpen ? buildExport(deck) : ""} />
      <ExportDialog open={exportOpen} onOpenChange={setExportOpen} deck={deck} />
      <BasicLandsDialog open={basicsOpen} onOpenChange={setBasicsOpen} deck={deck} target={target === "commander" ? "mainboard" : target}
        onChange={(cat, list) => setDeck((prev) => ({ ...prev, [cat]: list }))} />
    </div>
  );
}
