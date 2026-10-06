import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { API } from "@/lib/api";
import DeckWorkspace from "@/components/DeckWorkspace";
import DeckStats from "@/components/DeckStats";
import { Sparkles, Loader2 } from "lucide-react";
import { formatLabel, totalCount } from "@/lib/mtg";

export default function PublicDeck() {
  const { shareId } = useParams();
  const [deck, setDeck] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    axios.get(`${API}/decks/public/${shareId}`)
      .then(({ data }) => setDeck(data))
      .catch(() => setError(true));
  }, [shareId]);

  if (error) {
    return (
      <div className="h-screen flex flex-col items-center justify-center bg-[#060a14] text-slate-300 gap-3">
        <p className="font-display text-xl">Deck not found</p>
        <Link to="/" className="text-amber-400 hover:underline text-sm" data-testid="home-link">Go to Grimoire</Link>
      </div>
    );
  }
  if (!deck) {
    return <div className="h-screen flex items-center justify-center bg-[#060a14]"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>;
  }

  const showCommander = deck.format === "commander";
  const analyticsCards = [...deck.mainboard, ...deck.commander];
  const total = totalCount(deck.mainboard) + totalCount(deck.commander);

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100">
      <header className="border-b border-slate-800 bg-[#070c17]">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="logo">
            <Sparkles className="w-5 h-5 text-amber-400" />
            <span className="font-display text-lg font-bold">Grimoire</span>
          </Link>
          <Link to="/register"><span className="text-sm text-amber-400 hover:underline" data-testid="public-cta">Build your own →</span></Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="font-display text-3xl font-bold" data-testid="public-deck-name">{deck.name}</h1>
          <p className="text-sm text-slate-400 mt-1">{formatLabel(deck.format)} · {total} cards {deck.owner_name && <>· by {deck.owner_name}</>}</p>
        </div>
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 rounded-2xl border border-slate-800 bg-[#0a1120] overflow-hidden">
            <DeckWorkspace deck={deck} format={deck.format} readOnly showCommander={showCommander}
              onQty={() => {}} onRemove={() => {}} onPrintings={() => {}} onReorder={() => {}} />
          </div>
          <div className="rounded-2xl border border-slate-800 bg-[#070c17] p-4">
            <DeckStats cards={analyticsCards} />
          </div>
        </div>
      </main>
    </div>
  );
}
