import type { BoardCard, Column } from "./types";

export const COLUMN_META: Record<Column, { label: string; hint: string }> = {
  prospect: { label: "Prospect", hint: "Found by a search" },
  interested: { label: "Interested", hint: "Worth tailoring for" },
  tailoring: { label: "Tailoring", hint: "Resume being built" },
  resume_ready: { label: "Resume ready", hint: "Ready to send" },
  applied: { label: "Applied", hint: "Application sent" },
  interviewing: { label: "Interviewing", hint: "Screens and rounds" },
  offer: { label: "Offer", hint: "Offer made" },
  closed: { label: "Closed", hint: "Passed, rejected or archived" },
};

export type DropAction =
  | { type: "none" }
  | { type: "patch_posting"; stage: "prospect" | "interested" | "dismissed"; dismiss_reason?: string }
  | { type: "tailor" }
  | { type: "patch_project"; patch: { outcome_stage?: number; status?: string } }
  | { type: "invalid"; reason: string };

/**
 * What happens when a card is dropped on a column. A posting moves through prospect, interested
 * and closed on its own; resume stages need a project (so dropping a posting there opens the
 * tailor dialog); a project advances through applied, interviewing and offer.
 */
export function dropAction(card: Pick<BoardCard, "kind" | "column">, target: Column): DropAction {
  if (card.column === target) return { type: "none" };
  if (card.kind === "posting") {
    if (target === "prospect" || target === "interested") return { type: "patch_posting", stage: target };
    if (target === "closed") return { type: "patch_posting", stage: "dismissed", dismiss_reason: "not_interested" };
    if (target === "tailoring" || target === "resume_ready") return { type: "tailor" };
    return { type: "invalid", reason: "Tailor a resume for this posting first, then move it along." };
  }
  switch (target) {
    case "applied":
      return { type: "patch_project", patch: { outcome_stage: 1 } };
    case "interviewing":
      return { type: "patch_project", patch: { outcome_stage: 2 } };
    case "offer":
      return { type: "patch_project", patch: { outcome_stage: 4 } };
    case "closed":
      return { type: "patch_project", patch: { status: "rejected" } };
    default:
      return { type: "invalid", reason: "A resume project can't move back before it was applied for. Open it to make changes." };
  }
}

export function groupByColumn(cards: BoardCard[], columns: Column[]): Record<Column, BoardCard[]> {
  const out = Object.fromEntries(columns.map((c) => [c, [] as BoardCard[]])) as Record<Column, BoardCard[]>;
  for (const card of cards) (out[card.column] ??= []).push(card);
  for (const col of columns) {
    out[col].sort((a, b) => (b.fit ?? -1) - (a.fit ?? -1) || b.updated_at.localeCompare(a.updated_at));
  }
  return out;
}

/** Applications open this long without an interview are worth a nudge. */
export function isStale(card: Pick<BoardCard, "column" | "age_days">, thresholdDays = 21): boolean {
  return ["prospect", "interested"].includes(card.column) && (card.age_days ?? 0) >= thresholdDays;
}
