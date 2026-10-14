import type { Project } from "@/lib/api/types";

export interface FunnelStep {
  stage: number;
  /** Projects that reached this stage or went further. */
  count: number;
  /** Share of the previous stage that reached this one (null for the first step or an empty previous step). */
  conversion: number | null;
}

/** Archived projects are left out; closed ones still count toward the stages they reached. */
export function trackedProjects(projects: Project[]): Project[] {
  return projects.filter((p) => p.status !== "archived");
}

export function furthestStage(p: Pick<Project, "outcome_stage">): number {
  return Math.max(0, Math.min(4, p.outcome_stage ?? 0));
}

export function buildFunnel(projects: Project[]): FunnelStep[] {
  const tracked = trackedProjects(projects);
  const counts = [0, 1, 2, 3, 4].map((stage) =>
    tracked.filter((p) => (stage === 0 ? p.has_result || furthestStage(p) > 0 : furthestStage(p) >= stage)).length,
  );
  return counts.map((count, stage) => ({
    stage,
    count,
    conversion: stage === 0 || counts[stage - 1] === 0 ? null : count / counts[stage - 1],
  }));
}
