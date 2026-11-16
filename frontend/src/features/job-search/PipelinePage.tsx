import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KanbanSquare, List } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { ROUTES } from "@/lib/routes";
import { jsKeys, usePipeline } from "./api";
import { Board } from "./components/Board";
import { ageLabel, FRESHNESS } from "./format";
import { COLUMN_META, dropAction } from "./pipeline";
import { TailorDialog } from "./TailorDialog";
import type { BoardCard, Column } from "./types";

type Data = { columns: Column[]; cards: BoardCard[] };

export default function PipelinePage() {
  const qc = useQueryClient();
  const { data, isLoading } = usePipeline();
  const [view, setView] = useState<"board" | "table">("board");
  const [tailorFor, setTailorFor] = useState<BoardCard | null>(null);

  const move = useMutation({
    mutationFn: async ({ card, action }: { card: BoardCard; target: Column; action: ReturnType<typeof dropAction> }) => {
      if (action.type === "patch_posting") {
        return api.patch(`/api/job-search/postings/${card.id}`, { stage: action.stage, dismiss_reason: action.dismiss_reason });
      }
      if (action.type === "patch_project") return api.patch(`/api/projects/${card.id}`, action.patch);
      return null;
    },
    onMutate: async ({ card, target, action }) => {
      if (action.type !== "patch_posting" && action.type !== "patch_project") return {};
      await qc.cancelQueries({ queryKey: jsKeys.pipeline });
      const prev = qc.getQueryData<Data>(jsKeys.pipeline);
      if (prev) qc.setQueryData<Data>(jsKeys.pipeline, { ...prev, cards: prev.cards.map((c) => (c.id === card.id ? { ...c, column: target } : c)) });
      return { prev };
    },
    onError: (e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(jsKeys.pipeline, ctx.prev);
      toast.error((e as Error).message);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: jsKeys.all });
      qc.invalidateQueries({ queryKey: keys.projects });
    },
  });

  const onDrop = (card: BoardCard, target: Column) => {
    const action = dropAction(card, target);
    if (action.type === "none") return;
    if (action.type === "invalid") {
      toast.message(action.reason);
      return;
    }
    if (action.type === "tailor") {
      setTailorFor(card);
      return;
    }
    move.mutate({ card, target, action });
  };

  if (isLoading || !data) return <Skeleton className="h-64" />;
  if (data.cards.length === 0) {
    return (
      <EmptyState
        icon={KanbanSquare}
        title="Nothing on the board yet"
        description="Run a search and mark roles as Interested, or tailor a resume for one. Every application, from prospect to offer, shows up here."
        action={<Button asChild variant="gradient"><Link to={ROUTES.jobSearch}>Find roles</Link></Button>}
      />
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Drag a card to move it. Postings move between Prospect, Interested and Closed; a resume project moves on to Applied, Interviewing and Offer.
        </p>
        <div className="flex gap-1 rounded-lg border p-0.5" role="group" aria-label="Board view">
          <Button size="sm" variant={view === "board" ? "secondary" : "ghost"} onClick={() => setView("board")} aria-pressed={view === "board"}><KanbanSquare /> Board</Button>
          <Button size="sm" variant={view === "table" ? "secondary" : "ghost"} onClick={() => setView("table")} aria-pressed={view === "table"}><List /> Table</Button>
        </div>
      </div>

      {view === "board" ? (
        <Board cards={data.cards} columns={data.columns} onDrop={onDrop} />
      ) : (
        <Table>
          <TableHeader>
            <TableRow><TableHead>Role</TableHead><TableHead>Company</TableHead><TableHead>Stage</TableHead><TableHead>Fit</TableHead><TableHead>Posting age</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {[...data.cards].sort((a, b) => data.columns.indexOf(a.column) - data.columns.indexOf(b.column) || (b.fit ?? -1) - (a.fit ?? -1)).map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium">
                  {c.kind === "project" ? <Link to={ROUTES.project(c.id)} className="hover:underline">{c.title}</Link> : <a href={c.url} target="_blank" rel="noreferrer" className="hover:underline">{c.title}</a>}
                </TableCell>
                <TableCell>{c.company}</TableCell>
                <TableCell><Badge variant="secondary">{COLUMN_META[c.column].label}</Badge></TableCell>
                <TableCell className="tabular-nums">{c.fit ?? ""}</TableCell>
                <TableCell>
                  {c.freshness && <Badge variant={FRESHNESS[c.freshness].variant} className="mr-2">{FRESHNESS[c.freshness].label}</Badge>}
                  <span className="text-xs text-muted-foreground">{c.age_days !== null ? ageLabel(c.age_days) : ""}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <TailorDialog posting={tailorFor && tailorFor.kind === "posting" ? tailorFor : null} open={!!tailorFor} onOpenChange={(o) => !o && setTailorFor(null)} />
    </div>
  );
}
