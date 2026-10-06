import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { Sparkles, Layers, BarChart3, Share2, ArrowRight, Zap } from "lucide-react";

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
  const cta = user ? "/dashboard" : "/register";

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
            Grimoire is a fast, modern deck builder for Magic: The Gathering. Search live card data, visualize your mana curve, and craft the perfect list across every format.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Button data-testid="hero-cta" onClick={() => navigate(cta)} className="h-12 px-7 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold text-base">
              Start building <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          </div>
        </div>
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
