import { useEffect, useState } from "react";
import { toast } from "sonner";
import { OUTCOME_STAGES, STATUS_META } from "@/components/shared/status";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { usePatchProject } from "@/lib/api/queries";
import type { Project, ProjectStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Where the application stands: outcome stage, status, applied date, posting link and notes. */
export function TrackingPanel({ project }: { project: Project }) {
  const patch = usePatchProject(project.id);
  const [notes, setNotes] = useState(project.notes);
  const [url, setUrl] = useState(project.url);
  useEffect(() => setNotes(project.notes), [project.notes]);
  useEffect(() => setUrl(project.url), [project.url]);

  const commit = (fields: Partial<Project>) =>
    patch.mutate(fields, { onError: (e) => toast.error((e as Error).message) });

  return (
    <Card className="grid gap-5 p-5">
      <div>
        <h3 className="text-sm font-semibold">Outcome</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">The furthest stage this application has reached. It feeds the Progress tab.</p>
        <div role="radiogroup" aria-label="Outcome" className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          {OUTCOME_STAGES.map((s, i) => (
            <button
              key={s.key}
              type="button"
              role="radio"
              aria-checked={(project.outcome_stage ?? 0) === i}
              onClick={() => commit({ outcome_stage: i })}
              className={cn(
                "flex flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left text-sm font-medium transition-all hover:bg-secondary",
                (project.outcome_stage ?? 0) === i && "border-primary bg-primary/[0.06] ring-1 ring-primary/30",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={cn("size-2 rounded-full", s.dot)} />
                {i}
              </span>
              {s.label}
            </button>
          ))}
        </div>
        {project.outcome_dates?.[OUTCOME_STAGES[project.outcome_stage ?? 0].key] && (
          <p className="mt-2 text-xs text-muted-foreground">
            Reached {OUTCOME_STAGES[project.outcome_stage].label.toLowerCase()} on {project.outcome_dates[OUTCOME_STAGES[project.outcome_stage].key]}.
          </p>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold">Where things stand</h3>
        <div role="radiogroup" aria-label="Status" className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {(Object.keys(STATUS_META) as ProjectStatus[]).map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={project.status === s}
              onClick={() => commit({ status: s, ...(s === "applied" && !project.applied_on ? { applied_on: new Date().toISOString().slice(0, 10) } : {}) })}
              className={cn(
                "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all hover:bg-secondary",
                project.status === s && "border-primary bg-primary/[0.06] ring-1 ring-primary/30",
              )}
            >
              <span className={cn("size-2 rounded-full", STATUS_META[s].dot)} />
              {STATUS_META[s].label}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Applied on" htmlFor="applied-on">
          <Input
            id="applied-on"
            type="date"
            value={project.applied_on ?? ""}
            onChange={(e) => commit({ applied_on: e.target.value || null })}
          />
        </Field>
        <Field label="Posting link" htmlFor="posting-url">
          <Input id="posting-url" value={url} onChange={(e) => setUrl(e.target.value)} onBlur={() => url !== project.url && commit({ url })} placeholder="https://" />
        </Field>
      </div>
      <Field label="Notes" hint="Recruiter names, interview dates, follow-ups. Saved when you click away." htmlFor="notes">
        <Textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => notes !== project.notes && commit({ notes })}
          className="min-h-[160px]"
        />
      </Field>
    </Card>
  );
}
