import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { Clock, ExternalLink, GripVertical } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { ageLabel, FRESHNESS, scoreTone } from "../format";
import { COLUMN_META, groupByColumn, isStale } from "../pipeline";
import type { BoardCard, Column } from "../types";

function CardBody({ card }: { card: BoardCard }) {
  const fresh = card.freshness ? FRESHNESS[card.freshness] : null;
  const stale = isStale(card);
  return (
    <div className="grid gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {card.kind === "project" ? (
            <Link to={ROUTES.project(card.id)} className="line-clamp-2 text-[13px] font-medium leading-snug hover:underline" onPointerDown={(e) => e.stopPropagation()}>
              {card.title}
            </Link>
          ) : (
            <a href={card.url} target="_blank" rel="noreferrer" className="line-clamp-2 inline-flex items-start gap-1 text-[13px] font-medium leading-snug hover:underline" onPointerDown={(e) => e.stopPropagation()}>
              {card.title}
              <ExternalLink className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
            </a>
          )}
          <div className="truncate text-xs text-muted-foreground">{card.company}</div>
        </div>
        {card.fit !== null && <span className={cn("text-sm font-semibold tabular-nums", scoreTone(card.fit))} title="Fit score">{card.fit}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {card.is_new && <Badge variant="success">New</Badge>}
        {fresh && card.kind === "posting" && <Badge variant={fresh.variant}>{fresh.label}</Badge>}
        {card.active_job && <Badge variant="warning">Working</Badge>}
        {card.dismiss_reason && <Badge variant="outline">{card.dismiss_reason.replace(/_/g, " ")}</Badge>}
        {card.age_days !== null && card.kind === "posting" && (
          <span className={cn("inline-flex items-center gap-1 text-[11px]", stale ? "text-warning" : "text-muted-foreground")}>
            {stale && <Clock className="size-3" />}
            {ageLabel(card.age_days)}
          </span>
        )}
      </div>
    </div>
  );
}

function DraggableCard({ card }: { card: BoardCard }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: card.id, data: { card } });
  return (
    <div ref={setNodeRef} className={cn("group flex gap-1 rounded-lg border bg-card p-2.5 shadow-soft", isDragging && "opacity-40")}>
      <button type="button" className="mt-0.5 cursor-grab touch-none text-muted-foreground/60 hover:text-foreground" aria-label={`Move ${card.title}`} {...attributes} {...listeners}>
        <GripVertical className="size-4" />
      </button>
      <div className="min-w-0 flex-1"><CardBody card={card} /></div>
    </div>
  );
}

function DroppableColumn({ id, cards }: { id: Column; cards: BoardCard[] }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const meta = COLUMN_META[id];
  return (
    <section
      ref={setNodeRef}
      aria-label={meta.label}
      className={cn("flex min-h-40 w-60 shrink-0 flex-col gap-2 rounded-xl border bg-secondary/30 p-2.5 transition-colors", isOver && "border-primary/50 bg-primary/5")}
    >
      <header className="flex items-baseline justify-between px-1">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{meta.label}</h3>
        <span className="text-xs tabular-nums text-muted-foreground">{cards.length}</span>
      </header>
      {cards.map((c) => <DraggableCard key={c.id} card={c} />)}
      {cards.length === 0 && <p className="px-1 py-3 text-center text-xs text-muted-foreground/70">{meta.hint}</p>}
    </section>
  );
}

export function Board({ cards, columns, onDrop }: { cards: BoardCard[]; columns: Column[]; onDrop: (card: BoardCard, target: Column) => void }) {
  const [active, setActive] = useState<BoardCard | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor));
  const grouped = groupByColumn(cards, columns);

  const end = (e: DragEndEvent) => {
    setActive(null);
    const card = e.active.data.current?.card as BoardCard | undefined;
    if (card && e.over) onDrop(card, e.over.id as Column);
  };

  return (
    <DndContext sensors={sensors} onDragStart={(e: DragStartEvent) => setActive((e.active.data.current?.card as BoardCard) ?? null)} onDragEnd={end} onDragCancel={() => setActive(null)}>
      <div className="flex gap-3 overflow-x-auto pb-3">
        {columns.map((c) => <DroppableColumn key={c} id={c} cards={grouped[c] ?? []} />)}
      </div>
      <DragOverlay>{active && <div className="w-56 rounded-lg border bg-card p-2.5 shadow-lift"><CardBody card={active} /></div>}</DragOverlay>
    </DndContext>
  );
}
