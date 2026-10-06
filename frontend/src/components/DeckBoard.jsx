import React, { useEffect, useState } from "react";
import { DndContext, closestCorners, PointerSensor, useSensor, useSensors, useDroppable, DragOverlay } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ManaCost } from "@/components/ManaCost";
import { GripVertical, Minus, Plus, X, Images, Layers } from "lucide-react";
import {
  groupKeyFor, GROUP_ORDER, sortCards, isBasicLand, maxCopies, totalCount,
  VIEW_OPTIONS, GROUP_OPTIONS, SORT_OPTIONS,
} from "@/lib/mtg";

const CATS = [
  { key: "commander", label: "Commander" },
  { key: "mainboard", label: "Mainboard" },
  { key: "sideboard", label: "Sideboard" },
];

const parseCardId = (id) => { const p = id.split("|"); return { cat: p[1], cid: p[2] }; };
const parseContId = (id) => { const p = id.split("|"); return { cat: p[1], grp: p[2] }; };

function BoardCard({ card, category, view, format, index, readOnly, onQty, onRemove, onPrintings }) {
  const sortId = `card|${category}|${card.id}`;
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: sortId, disabled: readOnly });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1, zIndex: isDragging ? 60 : undefined };
  const max = maxCopies(card, format);
  const atMax = card.quantity >= max && !isBasicLand(card);
  const dragProps = readOnly ? {} : { ...attributes, ...listeners };

  if (view === "grid") {
    return (
      <div ref={setNodeRef} style={{ ...style, marginTop: index > 0 ? -188 : 0 }} data-testid={`deck-card-${card.id}`}
        className="group relative rounded-lg hover:z-50 focus-within:z-50 transition-[margin] duration-150 hover:-translate-y-0 hover:mt-0">
        <div {...dragProps} className={`relative rounded-lg overflow-hidden border border-slate-800 shadow-lg ${readOnly ? "" : "cursor-grab active:cursor-grabbing"}`}>
          <div className="aspect-[0.716] bg-slate-800">
            {card.image ? <img src={card.image} alt={card.name} loading="lazy" className="w-full h-full object-cover pointer-events-none" />
              : <div className="w-full h-full flex items-center justify-center p-2 text-center text-xs text-slate-300">{card.name}</div>}
          </div>
          <span className="absolute top-1 left-1 bg-black/80 text-amber-400 text-xs font-bold rounded px-1.5 py-0.5 tabular-nums">{card.quantity}×</span>
        </div>
        {!readOnly && (
          <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button data-testid={`inc-${card.id}`} onClick={() => onQty(category, card.id, 1)} disabled={atMax} className="w-6 h-6 rounded bg-black/80 text-white hover:bg-amber-500 hover:text-stone-900 flex items-center justify-center disabled:opacity-30"><Plus className="w-3.5 h-3.5" /></button>
            <button data-testid={`dec-${card.id}`} onClick={() => onQty(category, card.id, -1)} className="w-6 h-6 rounded bg-black/80 text-white hover:bg-slate-600 flex items-center justify-center"><Minus className="w-3.5 h-3.5" /></button>
            <button data-testid={`printings-${card.id}`} onClick={() => onPrintings(card)} className="w-6 h-6 rounded bg-black/80 text-white hover:bg-amber-500 hover:text-stone-900 flex items-center justify-center"><Images className="w-3.5 h-3.5" /></button>
            <button data-testid={`remove-${card.id}`} onClick={() => onRemove(category, card.id)} className="w-6 h-6 rounded bg-black/80 text-white hover:bg-red-500 flex items-center justify-center"><X className="w-3.5 h-3.5" /></button>
          </div>
        )}
      </div>
    );
  }

  // text row
  return (
    <div ref={setNodeRef} style={style} data-testid={`deck-card-${card.id}`}
      className="group flex items-center gap-2 h-9 px-2 rounded hover:bg-slate-800/70 transition-colors">
      {!readOnly && (
        <button {...dragProps} data-testid={`drag-${card.id}`} className="cursor-grab active:cursor-grabbing text-slate-600 hover:text-slate-400 touch-none"><GripVertical className="w-4 h-4" /></button>
      )}
      <span className="w-6 text-center text-sm font-bold text-amber-400 tabular-nums">{card.quantity}</span>
      <HoverCard openDelay={120} closeDelay={60}>
        <HoverCardTrigger asChild><span className="flex-1 min-w-0 truncate text-sm text-slate-100 cursor-default">{card.name}</span></HoverCardTrigger>
        <HoverCardContent side="right" className="w-56 p-0 bg-transparent border-none shadow-2xl">
          {card.image && <img src={card.image} alt={card.name} className="w-full rounded-xl" />}
        </HoverCardContent>
      </HoverCard>
      <ManaCost cost={card.mana_cost} size={14} className="shrink-0" />
      {!readOnly && (
        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button data-testid={`printings-${card.id}`} onClick={() => onPrintings(card)} className="p-1 text-slate-400 hover:text-amber-400"><Images className="w-3.5 h-3.5" /></button>
          <button data-testid={`dec-${card.id}`} onClick={() => onQty(category, card.id, -1)} className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700"><Minus className="w-3.5 h-3.5" /></button>
          <button data-testid={`inc-${card.id}`} onClick={() => onQty(category, card.id, 1)} disabled={atMax} className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700 disabled:opacity-30"><Plus className="w-3.5 h-3.5" /></button>
          <button data-testid={`remove-${card.id}`} onClick={() => onRemove(category, card.id)} className="p-1 text-slate-500 hover:text-red-400"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}
    </div>
  );
}

function Column({ cat, groupKey, label, count, cards, view, format, readOnly, group, handlers }) {
  const { setNodeRef, isOver } = useDroppable({ id: `cont|${cat}|${groupKey}` });
  const items = cards.map((c) => `card|${cat}|${c.id}`);
  return (
    <div className={`${view === "grid" ? "w-[168px]" : "w-full sm:w-60"} shrink-0`} data-testid={`column-${cat}-${groupKey}`}>
      {group !== "custom" && (
        <div className="flex items-center justify-between mb-2 px-1">
          <h4 className="text-xs font-display font-semibold uppercase tracking-wide text-slate-300 truncate">{label}</h4>
          <span className="text-xs text-slate-500 tabular-nums">{count}</span>
        </div>
      )}
      <SortableContext items={items} strategy={verticalListSortingStrategy}>
        <div ref={setNodeRef} className={`${view === "grid" ? "pt-0 min-h-[60px]" : "space-y-0 min-h-[40px]"} rounded-lg transition-colors ${isOver ? "bg-amber-400/5 ring-1 ring-amber-400/30" : ""}`}>
          {cards.map((c, i) => (
            <BoardCard key={c.id} card={c} category={cat} view={view} index={i} format={format} readOnly={readOnly}
              onQty={handlers.onQty} onRemove={handlers.onRemove} onPrintings={handlers.onPrintings} />
          ))}
          {cards.length === 0 && <div className="h-10 flex items-center justify-center text-[11px] text-slate-600">Drop here</div>}
        </div>
      </SortableContext>
    </div>
  );
}

export default function DeckBoard({ deck, format, showCommander, readOnly = false, onQty, onRemove, onPrintings, onCardsChange }) {
  const [view, setView] = useState(() => localStorage.getItem("grim_view") || "text");
  const [group, setGroup] = useState(() => localStorage.getItem("grim_group") || "type");
  const [sort, setSort] = useState(() => localStorage.getItem("grim_sort") || "manual");
  const [activeCard, setActiveCard] = useState(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  useEffect(() => { localStorage.setItem("grim_view", view); }, [view]);
  useEffect(() => { localStorage.setItem("grim_group", group); }, [group]);
  useEffect(() => { localStorage.setItem("grim_sort", sort); }, [sort]);

  const categories = CATS.filter((c) => (c.key !== "commander" || showCommander) && deck[c.key].length >= 0);
  const visibleCats = categories.filter((c) => c.key !== "commander" || (showCommander && true));

  const buildColumns = (cards) => {
    const order = GROUP_ORDER[group];
    const map = {};
    cards.forEach((c) => { const k = groupKeyFor(c, group); (map[k] = map[k] || []).push(c); });
    const keys = [...order.filter((k) => map[k]), ...Object.keys(map).filter((k) => !order.includes(k))];
    return keys.map((k) => ({ key: k, cards: sortCards(map[k], sort) }));
  };

  const findCard = (cat, cid) => deck[cat].find((c) => c.id === cid);

  const handleDragStart = (e) => {
    const { cat, cid } = parseCardId(e.active.id);
    setActiveCard(findCard(cat, cid));
  };

  const handleDragEnd = (e) => {
    setActiveCard(null);
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const a = parseCardId(active.id);
    let destCat, destGroup, overCardId = null;
    if (String(over.id).startsWith("cont|")) {
      const o = parseContId(over.id); destCat = o.cat; destGroup = o.grp;
    } else {
      const o = parseCardId(over.id); destCat = o.cat; overCardId = o.cid;
      const oc = findCard(o.cat, o.cid);
      destGroup = oc ? groupKeyFor(oc, group) : null;
    }
    const card = findCard(a.cat, a.cid);
    if (!card) return;

    let newCard = card;
    if (group !== "custom" && destGroup) {
      const cur = groupKeyFor(card, group);
      if (destGroup !== cur) newCard = { ...card, group_overrides: { ...(card.group_overrides || {}), [group]: destGroup } };
    }

    const next = { mainboard: [...deck.mainboard], sideboard: [...deck.sideboard], commander: [...deck.commander] };
    const srcArr = next[a.cat].filter((c) => c.id !== a.cid);
    const destArr = a.cat === destCat ? srcArr : [...next[destCat]];

    let insertIdx;
    if (overCardId) {
      insertIdx = destArr.findIndex((c) => c.id === overCardId);
      if (insertIdx < 0) insertIdx = destArr.length;
    } else {
      const groupIdxs = destArr.map((c, i) => (groupKeyFor(c, group) === destGroup ? i : -1)).filter((i) => i >= 0);
      insertIdx = groupIdxs.length ? groupIdxs[groupIdxs.length - 1] + 1 : destArr.length;
    }
    destArr.splice(insertIdx, 0, newCard);

    if (a.cat === destCat) next[a.cat] = destArr;
    else { next[a.cat] = srcArr; next[destCat] = destArr; }
    onCardsChange(next);
  };

  const handlers = { onQty, onRemove, onPrintings };
  const isEmpty = !deck.mainboard.length && !deck.sideboard.length && !deck.commander.length;

  return (
    <div className="flex-1 overflow-y-auto flex flex-col" data-testid="deck-board">
      {/* Toolbar */}
      <div className="sticky top-0 z-20 bg-[#0a1120]/95 backdrop-blur border-b border-slate-800 px-6 lg:px-10 py-2.5 flex items-center gap-3 flex-wrap">
        <Control label="View" value={view} onChange={setView} options={VIEW_OPTIONS} testid="view-select" />
        <Control label="Group" value={group} onChange={setGroup} options={GROUP_OPTIONS} testid="group-select" />
        <Control label="Sort" value={sort} onChange={setSort} options={SORT_OPTIONS} testid="sort-select" />
        {!readOnly && <span className="text-[11px] text-slate-500 ml-auto hidden md:block">Drag cards to reorder or move between sections</span>}
      </div>

      <div className="flex-1 px-6 lg:px-10 py-6">
        {isEmpty && (
          <div className="h-full min-h-[280px] flex flex-col items-center justify-center text-center gap-2 text-slate-500">
            <Layers className="w-10 h-10 text-slate-700" />
            <p className="text-sm">Your deck is empty.</p>
            {!readOnly && <p className="text-xs text-slate-600">Search for cards and hit + to add them.</p>}
          </div>
        )}
        <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
          <div className="space-y-7 max-w-[1500px] mx-auto">
            {visibleCats.map((c) => {
              if (c.key === "commander" && !showCommander) return null;
              if (deck[c.key].length === 0 && (readOnly || c.key === "commander")) return null;
              const cols = buildColumns(deck[c.key]);
              return (
                <section key={c.key} data-testid={`section-${c.key}`}>
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-sm font-display font-bold uppercase tracking-wide text-amber-400/90">{c.label}</h3>
                    <span className="text-xs text-slate-500 tabular-nums" data-testid={`count-${c.key}`}>{totalCount(deck[c.key])}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-5 gap-y-6 items-start">
                    {cols.length === 0 ? (
                      <Column cat={c.key} groupKey={group === "custom" ? "all" : (GROUP_ORDER[group][0] || "all")} label="" count={0} cards={[]} view={view} format={format} readOnly={readOnly} group={group} handlers={handlers} />
                    ) : cols.map((col) => (
                      <Column key={col.key} cat={c.key} groupKey={col.key} label={col.key === "all" ? c.label : col.key}
                        count={totalCount(col.cards)} cards={col.cards} view={view} format={format} readOnly={readOnly} group={group} handlers={handlers} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
          <DragOverlay>
            {activeCard ? (
              view === "grid" ? (
                <div className="w-[168px] rounded-lg overflow-hidden border border-amber-400/50 shadow-2xl rotate-2">
                  {activeCard.image && <img src={activeCard.image} alt="" className="w-full" />}
                </div>
              ) : (
                <div className="px-3 py-1.5 rounded bg-slate-800 border border-amber-400/50 text-sm text-slate-100 shadow-2xl flex items-center gap-2">
                  <span className="text-amber-400 font-bold">{activeCard.quantity}</span> {activeCard.name}
                </div>
              )
            ) : null}
          </DragOverlay>
        </DndContext>
      </div>
    </div>
  );
}

function Control({ label, value, onChange, options, testid }) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-xs text-slate-500">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger data-testid={testid} className="h-8 w-32 bg-slate-900 border-slate-700 text-slate-200 text-xs"><SelectValue /></SelectTrigger>
        <SelectContent className="bg-slate-900 border-slate-700 text-slate-200">
          {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
  );
}
