import { BarChart3, Plus } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/shared/EmptyState";
import { Monogram } from "@/components/shared/Monogram";
import { PageHeader } from "@/components/shared/PageHeader";
import { OUTCOME_STAGES, StatusBadge } from "@/components/shared/status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjects } from "@/lib/api/queries";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { buildFunnel, furthestStage, trackedProjects } from "./funnel";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export default function ProgressPage() {
  const { data: projects, isLoading } = useProjects();
  const funnel = useMemo(() => buildFunnel(projects ?? []), [projects]);
  const tracked = useMemo(() => trackedProjects(projects ?? []), [projects]);
  const max = Math.max(1, ...funnel.map((s) => s.count));

  // Furthest stage first, so the most promising applications are at the top.
  const pipeline = useMemo(
    () =>
      [...tracked]
        .filter((p) => furthestStage(p) > 0)
        .sort((a, b) => furthestStage(b) - furthestStage(a) || b.updated_at.localeCompare(a.updated_at)),
    [tracked],
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader title="Progress" description="How far each application has gotten, across everything you have tracked." />

      {isLoading ? (
        <Skeleton className="mt-6 h-64 rounded-xl" />
      ) : !tracked.length ? (
        <EmptyState
          icon={BarChart3}
          title="Nothing to track yet"
          description="Create a project, then record its outcome (applied, screen, more rounds, offer) from the project card or its Tracking tab."
          action={
            <Button asChild variant="gradient">
              <Link to={ROUTES.newProject}>
                <Plus /> New project
              </Link>
            </Button>
          }
        />
      ) : (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {funnel.map((s) => (
              <Card key={s.stage} className="px-4 py-3.5">
                <div className="text-xs font-medium text-muted-foreground">{OUTCOME_STAGES[s.stage].label}</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight">{s.count}</div>
              </Card>
            ))}
          </div>

          <Card className="mt-4 p-5">
            <h2 className="text-sm font-semibold">Funnel</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Each bar counts applications that reached that stage or went further. The percentage is the share of the previous stage.
            </p>
            <div className="mt-4 grid gap-3">
              {funnel.map((s) => (
                <div key={s.stage} className="grid grid-cols-[8.5rem_1fr_3rem] items-center gap-3 text-sm">
                  <span className="truncate text-muted-foreground">{OUTCOME_STAGES[s.stage].label}</span>
                  <div className="h-6 overflow-hidden rounded-md bg-secondary">
                    <div
                      className={cn("h-full rounded-md transition-all", OUTCOME_STAGES[s.stage].dot)}
                      style={{ width: `${(s.count / max) * 100}%` }}
                      role="img"
                      aria-label={`${s.count} reached ${OUTCOME_STAGES[s.stage].label}`}
                    />
                  </div>
                  <span className="text-right text-xs tabular-nums text-muted-foreground">
                    {s.conversion === null ? "" : pct(s.conversion)}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card className="mt-4 p-5">
            <h2 className="text-sm font-semibold">Applications in play</h2>
            {pipeline.length === 0 ? (
              <p className="mt-2 text-sm text-muted-foreground">Once you mark a project as applied, it shows up here.</p>
            ) : (
              <ul className="mt-3 divide-y">
                {pipeline.map((p) => {
                  const stage = OUTCOME_STAGES[furthestStage(p)];
                  const date = p.outcome_dates?.[stage.key];
                  return (
                    <li key={p.id}>
                      <Link to={ROUTES.project(p.id)} className="flex items-center gap-3 py-2.5 hover:bg-secondary/50 sm:-mx-2 sm:px-2 sm:rounded-md">
                        <Monogram text={p.company || p.name} className="size-8 text-xs" />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm font-medium">{p.role || p.name}</div>
                          <div className="truncate text-xs text-muted-foreground">{p.company || "Company not set"}</div>
                        </div>
                        <StatusBadge status={p.status} className="hidden sm:inline-flex" />
                        <div className="w-36 text-right text-xs">
                          <div className="font-medium">{stage.label}</div>
                          {date && <div className="text-muted-foreground">{date}</div>}
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
