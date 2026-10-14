/** How a project's status and hiring-process outcome are labelled and colored. */
import { Badge } from "@/components/ui/badge";
import type { ProjectStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const STATUS_META: Record<ProjectStatus, { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline"; dot: string }> = {
  draft: { label: "Draft", variant: "secondary", dot: "bg-muted-foreground/60" },
  applied: { label: "Applied", variant: "default", dot: "bg-primary" },
  interviewing: { label: "Interviewing", variant: "warning", dot: "bg-warning" },
  offer: { label: "Offer", variant: "success", dot: "bg-success" },
  rejected: { label: "Closed", variant: "outline", dot: "bg-destructive/70" },
  archived: { label: "Archived", variant: "outline", dot: "bg-muted-foreground/40" },
};

export function StatusBadge({ status, className }: { status: ProjectStatus; className?: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.draft;
  return (
    <Badge variant={meta.variant} className={className}>
      <span className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </Badge>
  );
}

/** Furthest stage reached in the hiring process; the index is what the API stores. */
export const OUTCOME_STAGES = [
  { key: "generated", label: "Generated", dot: "bg-muted-foreground/60" },
  { key: "applied", label: "Applied", dot: "bg-primary" },
  { key: "initial_screen", label: "Initial screen", dot: "bg-warning" },
  { key: "additional_rounds", label: "Additional rounds", dot: "bg-warning" },
  { key: "offer", label: "Offer made", dot: "bg-success" },
] as const;

export function OutcomeBadge({ stage, className }: { stage: number; className?: string }) {
  const meta = OUTCOME_STAGES[stage] ?? OUTCOME_STAGES[0];
  return (
    <Badge variant="outline" className={className}>
      <span className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </Badge>
  );
}
