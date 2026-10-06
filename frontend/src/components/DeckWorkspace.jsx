import React from "react";
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import CardRow from "@/components/CardRow";
import { totalCount } from "@/lib/mtg";
import { Layers } from "lucide-react";

function CategoryList({ title, category, cards, format, readOnly, onQty, onRemove, onPrintings, onReorder }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const ids = cards.map((c) => `${category}:${c.id}`);
    const oldIndex = ids.indexOf(active.id);
    const newIndex = ids.indexOf(over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    onReorder(category, arrayMove(cards, oldIndex, newIndex));
  };

  return (
    <div data-testid={`category-${category}`}>
      <div className="flex items-center justify-between px-3 py-2 sticky top-0 bg-[#0a1120] z-10 border-b border-slate-800">
        <h3 className="text-sm font-display font-semibold text-slate-200 uppercase tracking-wide">{title}</h3>
        <span className="text-xs text-slate-500 tabular-nums" data-testid={`count-${category}`}>{totalCount(cards)}</span>
      </div>
      {cards.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-slate-600">Empty</div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={cards.map((c) => `${category}:${c.id}`)} strategy={verticalListSortingStrategy}>
            {cards.map((card) => (
              <CardRow key={card.id} card={card} category={category} format={format} readOnly={readOnly}
                onQty={(id, d) => onQty(category, id, d)} onRemove={(id) => onRemove(category, id)} onPrintings={onPrintings} />
            ))}
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}

export default function DeckWorkspace({ deck, format, readOnly = false, showCommander, onQty, onRemove, onPrintings, onReorder }) {
  const isEmpty = !deck.mainboard.length && !deck.sideboard.length && !deck.commander.length;
  return (
    <div className="flex-1 overflow-y-auto" data-testid="deck-workspace">
      {isEmpty && (
        <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-center gap-2 text-slate-500 px-6">
          <Layers className="w-10 h-10 text-slate-700" />
          <p className="text-sm">Your deck is empty.</p>
          <p className="text-xs text-slate-600">Search for cards {readOnly ? "" : "and hit + to add them."}</p>
        </div>
      )}
      {showCommander && deck.commander.length > 0 && (
        <CategoryList title="Commander" category="commander" cards={deck.commander} format={format} readOnly={readOnly}
          onQty={onQty} onRemove={onRemove} onPrintings={onPrintings} onReorder={onReorder} />
      )}
      {deck.mainboard.length > 0 && (
        <CategoryList title="Mainboard" category="mainboard" cards={deck.mainboard} format={format} readOnly={readOnly}
          onQty={onQty} onRemove={onRemove} onPrintings={onPrintings} onReorder={onReorder} />
      )}
      {deck.sideboard.length > 0 && (
        <CategoryList title="Sideboard" category="sideboard" cards={deck.sideboard} format={format} readOnly={readOnly}
          onQty={onQty} onRemove={onRemove} onPrintings={onPrintings} onReorder={onReorder} />
      )}
    </div>
  );
}
