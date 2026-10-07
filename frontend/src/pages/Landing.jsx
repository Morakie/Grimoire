import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { Sparkles, Layers, BarChart3, Share2, ArrowRight, Zap, Shuffle, Users, RefreshCw } from "lucide-react";

const HERO_BG = "https://images.unsplash.com/photo-1578662996442-48f60103fc96?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NzN8MHwxfHNlYXJjaHwzfHxkYXJrJTIwZmFudGFzeSUyMHRleHR1cmUlMjBhYnN0cmFjdHxlbnwwfHx8fDE3OTEzMjU0NjB8MA&ixlib=rb-4.1.0&q=85";

const features = [
  { icon: Zap, title: "Real-time Scryfall search", desc: "Search every card ever printed with instant high-res art, oracle text and mana symbols." },
  { icon: Layers, title: "Arena-style deck builder", desc: "Split-screen workspace. Quick-add, drag to reorder, mainboard, sideboard & commander." },
  { icon: BarChart3, title: "Deep deck analytics", desc: "Live mana curve, color distribution and card-type breakdowns as you build." },
  { icon: Share2, title: "Share any decklist", desc: "Generate a public link and switch card art to any printing, Moxfield-style." },
];

export default function Landing() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [lobbies, setLobbies] = useState([]);
  const [loadingLobbies, setLoadingLobbies] = useState(true);

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

  return (
    <div className="min-h-screen bg-[#060a14] text-slate-100 grim-grain">
      <header className="flex items-center justify-between px-6 lg:px-10 py-5 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-2" data-testid="logo">
          <Sparkles className="w-6 h-6 text-amber-400" />
          <span className="font-display text-xl font-bold tracking-tight">Grimoire</span>
        </Link>
        <div className="flex items-center gap-3">
          {user ? (
            <Button data-testid="nav-dashboard" onClick={() => navigate("/dashboard")} className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">My Decks</Button>
          ) : (
            <>
              <Link to="/login"><Button data-testid="nav-login" variant="ghost" className="text-slate-300 hover:text-white hover:bg-slate-800">Log in</Button></Link>
              <Link to="/register"><Button data-testid="nav-register" className="bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">Sign up</Button></Link>
            </>
          )}
        </div>
      </header>

      <section className="relative max-w-7xl mx-auto px-6 lg:px-10 pt-16 pb-24 overflow-hidden">
        <div className="absolute right-0 top-0 w-[55%] h-full opacity-20 pointer-events-none rounded-3xl overflow-hidden hidden lg:block">
          <img src={HERO_BG} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-l from-transparent to-[#060a14]" />
        </div>
        <div className="relative max-w-2xl animate-fade-up">
          <span className="inline-flex items-center gap-2 text-xs uppercase tracking-widest text-amber-400/90 border border-amber-400/30 rounded-full px-3 py-1 mb-6">
            <Zap className="w-3 h-3" /> Powered by Scryfall
          </span>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] tracking-tight">
            Build smarter <span className="text-amber-400">Magic</span> decks.
          </h1>
          <p className="mt-6 text-base lg:text-lg text-slate-400 max-w-xl">
            Grimoire is a fast, modern deck builder for Magic: The Gathering. Search live card data, visualize your mana curve, and run live Rotisserie cube drafts with friends.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Button data-testid="hero-cta" onClick={() => navigate("/build")} className="h-12 px-7 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-base">
              Start building <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
            <Button data-testid="hero-draft-cta" onClick={() => navigate("/draft")} variant="outline" className="h-12 px-7 bg-slate-900/60 border-amber-400/40 text-amber-300 hover:bg-amber-400/10 hover:text-amber-200 font-semibold text-base">
              <Shuffle className="w-4 h-4 mr-2" /> Start drafting
            </Button>
          </div>
        </div>
      </section>

      {/* Open draft lobbies */}
      <section className="max-w-7xl mx-auto px-6 lg:px-10 pb-16">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-amber-400" />
            <h2 className="font-display text-lg md:text-lg font-bold">Open draft lobbies</h2>
          </div>
          <button data-testid="refresh-lobbies" onClick={loadLobbies} className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-amber-300 transition-colors">
            <RefreshCw className={`w-3.5 h-3.5 ${loadingLobbies ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>

        {loadingLobbies ? (
          <div className="text-sm text-slate-500" data-testid="lobbies-loading">Loading lobbies…</div>
        ) : lobbies.length === 0 ? (
          <div data-testid="lobbies-empty" className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-8 text-center">
            <p className="text-sm text-slate-400">No open lobbies right now.</p>
            <Button data-testid="empty-host-draft" onClick={() => navigate("/draft")} className="mt-4 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
              <Shuffle className="w-4 h-4 mr-2" /> Host a draft
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
                  Join draft <ArrowRight className="w-4 h-4 ml-1.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="max-w-7xl mx-auto px-6 lg:px-10 pb-28">
        <div className="grid sm:grid-cols-2 gap-5">
          {features.map((f, i) => (
            <div key={i} className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 hover:border-amber-400/40 transition-colors" data-testid={`feature-${i}`}>
              <div className="w-11 h-11 rounded-xl bg-amber-400/10 border border-amber-400/20 flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-amber-400" />
              </div>
              <h3 className="font-display text-lg font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-400">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
