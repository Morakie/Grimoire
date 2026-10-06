import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { ManaCost } from "@/components/ManaCost";
import { GripVertical, Minus, Plus, X, Images } from "lucide-react";
import { isBasicLand, maxCopies } from "@/lib/mtg";

export default function CardRow({ card, category, format, readOnly, onQty, onRemove, onPrintings }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `${category}:${card.id}`, disabled: readOnly });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1, zIndex: isDragging ? 50 : "auto" };
  const max = maxCopies(card, format);
  const atMax = card.quantity >= max && !isBasicLand(card);

  return (
    <div ref={setNodeRef} style={style} data-testid={`deck-card-${card.id}`}
      className="group flex items-center gap-2 h-11 px-2 border-b border-slate-800/60 hover:bg-slate-800/60 transition-colors">
      {!readOnly && (
        <button {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-slate-600 hover:text-slate-400 touch-none" data-testid={`drag-${card.id}`}>
          <GripVertical className="w-4 h-4" />
        </button>
      )}
      <span className="w-7 text-center text-sm font-bold text-amber-400 tabular-nums">{card.quantity}</span>

      <HoverCard openDelay={120} closeDelay={60}>
        <HoverCardTrigger asChild>
          <span className="flex-1 min-w-0 truncate text-sm text-slate-100 cursor-default">{card.name}</span>
        </HoverCardTrigger>
        <HoverCardContent side="right" className="w-56 p-0 bg-transparent border-none shadow-2xl">
          {card.image && <img src={card.image} alt={card.name} className="w-full rounded-xl" />}
        </HoverCardContent>
      </HoverCard>

      <ManaCost cost={card.mana_cost} size={14} className="shrink-0" />

      {!readOnly && (
        <div className="flex items-center gap-1 shrink-0 opacity-60 group-hover:opacity-100 transition-opacity">
          <button data-testid={`printings-${card.id}`} onClick={() => onPrintings(card)} className="p-1 text-slate-400 hover:text-amber-400" title="Change art/printing">
            <Images className="w-3.5 h-3.5" />
          </button>
          <button data-testid={`dec-${card.id}`} onClick={() => onQty(card.id, -1)} className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700">
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button data-testid={`inc-${card.id}`} onClick={() => onQty(card.id, 1)} disabled={atMax}
            className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed">
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button data-testid={`remove-${card.id}`} onClick={() => onRemove(card.id)} className="p-1 text-slate-500 hover:text-red-400">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
