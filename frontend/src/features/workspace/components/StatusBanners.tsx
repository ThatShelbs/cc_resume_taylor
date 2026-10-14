import { Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Callout } from "@/components/shared/Callout";
import { Button } from "@/components/ui/button";
import type { JobSummary, Project } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { RunningBanner } from "./RunningBanner";

/** What needs attention above the editor: a running job, a failed run, stale inputs, missing setup. */
export function StatusBanners({
  project,
  job,
  running,
  hasDraft,
  blockedInputs,
  onOpenJob,
  onRegenerate,
}: {
  project: Project;
  job: JobSummary | null;
  running: boolean;
  hasDraft: boolean;
  blockedInputs: boolean | undefined;
  onOpenJob: (jobId: string) => void;
  onRegenerate: () => void;
}) {
  return (
    <div className="mt-5 grid gap-3">
      {running && job && <RunningBanner job={job} onOpen={() => onOpenJob(job.id)} />}
      {!running && job?.status === "failed" && (
        <Callout
          tone="error"
          title={job.deny?.length ? "The last run was blocked by your never-claim list" : `The last ${job.kind === "render" ? "render" : "generation"} didn't finish`}
          action={
            <Button size="sm" variant="outline" onClick={() => onOpenJob(job.id)}>
              Details
            </Button>
          }
        >
          <span className="whitespace-pre-wrap">{job.hint ?? job.error}</span>
        </Callout>
      )}
      {!running && project.inputs_changed.length > 0 && hasDraft && (
        <Callout
          tone="warning"
          title="Your source materials changed since this was generated"
          action={
            <Button size="sm" variant="outline" onClick={onRegenerate} disabled={blockedInputs}>
              <Sparkles /> Regenerate
            </Button>
          }
        >
          Updated: {project.inputs_changed.map((k) => k.replace("_", " ")).join(", ")}. Regenerate to tailor from the latest versions,
          or keep this one.
        </Callout>
      )}
      {blockedInputs && (
        <Callout
          tone="warning"
          title="Add your base resume and profile to generate"
          action={
            <Button asChild size="sm" variant="outline">
              <Link to={ROUTES.welcome}>Start setup</Link>
            </Button>
          }
        />
      )}
    </div>
  );
}
