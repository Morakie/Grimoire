import React, { useMemo, useState } from "react";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Textarea } from "@/components/ui/textarea";
import { BookOpen, Eye, Pencil } from "lucide-react";

/*
 * Deck primers: a small, safe Markdown subset rendered as React elements (never raw HTML).
 *   # / ## / ### headings, paragraphs, - or * bullets, 1. numbered lists, > quotes, ---
 *   **bold**, *italic*, [link](https://...), and [[Card Name]] card references with a preview.
 */

const INLINE = /(\[\[[^\]]+\]\]|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;

function CardRef({ name, cards }) {
  const card = cards[name.toLowerCase()] || cards[name.toLowerCase().split(" // ")[0]];
  const label = <span className="text-amber-300 underline decoration-amber-400/40 underline-offset-2 cursor-default">{name}</span>;
  if (!card?.image) return label;
  return (
    <HoverCard openDelay={100} closeDelay={60}>
      <HoverCardTrigger asChild><span tabIndex={0}>{label}</span></HoverCardTrigger>
      <HoverCardContent side="top" className="w-56 p-0 bg-transparent border-none shadow-2xl">
        <img src={card.image} alt={card.name} className="w-full rounded-xl" />
      </HoverCardContent>
    </HoverCard>
  );
}

function inline(text, cards, keyBase) {
  const out = [];
  let last = 0;
  let m;
  INLINE.lastIndex = 0;
  while ((m = INLINE.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const key = `${keyBase}-${m.index}`;
    if (t.startsWith("[[")) out.push(<CardRef key={key} name={t.slice(2, -2).trim()} cards={cards} />);
    else if (t.startsWith("**")) out.push(<strong key={key} className="text-slate-100 font-semibold">{t.slice(2, -2)}</strong>);
    else if (t.startsWith("[")) {
      const [, label, href] = t.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      out.push(<a key={key} href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-amber-300 underline underline-offset-2 hover:text-amber-200">{label}</a>);
    } else out.push(<em key={key}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function parseBlocks(src) {
  const lines = (src || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let para = [];
  const flush = () => { if (para.length) { blocks.push({ t: "p", text: para.join(" ") }); para = []; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { flush(); continue; }
    let m;
    if ((m = trimmed.match(/^(#{1,3})\s+(.*)$/))) { flush(); blocks.push({ t: `h${m[1].length}`, text: m[2] }); continue; }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flush(); blocks.push({ t: "hr" }); continue; }
    if (/^[-*]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
      flush();
      const ordered = /^\d/.test(trimmed);
      const items = [];
      while (i < lines.length && (ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/).test(lines[i])) {
        items.push(lines[i].trim().replace(ordered ? /^\d+[.)]\s+/ : /^[-*]\s+/, ""));
        i++;
      }
      i--;
      blocks.push({ t: ordered ? "ol" : "ul", items });
      continue;
    }
    if (trimmed.startsWith(">")) { flush(); blocks.push({ t: "quote", text: trimmed.replace(/^>\s?/, "") }); continue; }
    para.push(trimmed);
  }
  flush();
  return blocks;
}

export function PrimerView({ text, deckCards = [] }) {
  const cards = useMemo(() => {
    const map = {};
    deckCards.forEach((c) => { if (c?.name) { map[c.name.toLowerCase()] = c; map[c.name.toLowerCase().split(" // ")[0]] = c; } });
    return map;
  }, [deckCards]);
  const blocks = useMemo(() => parseBlocks(text), [text]);
  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-slate-300 max-w-3xl" data-testid="primer-view">
      {blocks.map((b, i) => {
        const k = `b${i}`;
        if (b.t === "h1") return <h2 key={k} className="font-display text-2xl font-bold text-slate-100 pt-2">{inline(b.text, cards, k)}</h2>;
        if (b.t === "h2") return <h3 key={k} className="font-display text-xl font-semibold text-slate-100 pt-2">{inline(b.text, cards, k)}</h3>;
        if (b.t === "h3") return <h4 key={k} className="font-display text-base font-semibold uppercase tracking-wide text-amber-400/90 pt-1">{inline(b.text, cards, k)}</h4>;
        if (b.t === "hr") return <hr key={k} className="border-slate-800 my-4" />;
        if (b.t === "quote") return <blockquote key={k} className="border-l-2 border-amber-400/50 pl-3 text-slate-400 italic">{inline(b.text, cards, k)}</blockquote>;
        if (b.t === "ul" || b.t === "ol") {
          const L = b.t;
          return (
            <L key={k} className={`${L === "ul" ? "list-disc" : "list-decimal"} pl-6 space-y-1 marker:text-amber-400/70`}>
              {b.items.map((it, j) => <li key={j}>{inline(it, cards, `${k}-${j}`)}</li>)}
            </L>
          );
        }
        return <p key={k}>{inline(b.text, cards, k)}</p>;
      })}
    </div>
  );
}

const PLACEHOLDER = `# How the deck wins
Explain the game plan in a few lines.

## Key cards
- [[Sol Ring]]: fast mana for an explosive start
- **Bold** and *italic* work too

## Mulligans
Keep hands with two lands and a ramp piece.`;

export default function PrimerEditor({ value, onChange, deckCards }) {
  const [mode, setMode] = useState(value ? "view" : "edit");
  const tab = (k, label, Icon) => (
    <button type="button" data-testid={`primer-${k}`} onClick={() => setMode(k)}
      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-colors ${mode === k ? "bg-amber-400 text-stone-900 font-semibold" : "text-slate-400 hover:text-slate-200"}`}>
      <Icon className="w-3.5 h-3.5" /> {label}
    </button>
  );
  return (
    <div className="px-3 sm:px-6 lg:px-10 py-4 sm:py-6 max-w-[1500px] mx-auto w-full" data-testid="primer-editor">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h3 className="text-sm font-display font-bold uppercase tracking-wide text-amber-400/90 flex items-center gap-2"><BookOpen className="w-4 h-4" /> Primer</h3>
        <div className="flex items-center gap-1 rounded-full border border-slate-700 p-0.5">
          {tab("edit", "Write", Pencil)}
          {tab("view", "Preview", Eye)}
        </div>
      </div>
      {mode === "edit" ? (
        <>
          <Textarea data-testid="primer-textarea" value={value} onChange={(e) => onChange(e.target.value)} placeholder={PLACEHOLDER} maxLength={20000}
            className="min-h-[50vh] bg-slate-950 border-slate-700 text-slate-100 text-sm font-mono leading-relaxed focus-visible:ring-amber-400" />
          <p className="text-[11px] text-slate-500 mt-2">
            # Heading, ## Subheading, - bullet, 1. numbered, **bold**, *italic*, [link](https://…), and [[Card Name]] for a card with a preview. Shown on your shared deck page.
          </p>
        </>
      ) : value?.trim() ? (
        <PrimerView text={value} deckCards={deckCards} />
      ) : (
        <p className="text-sm text-slate-500">No primer yet. Switch to Write to add one.</p>
      )}
    </div>
  );
}
