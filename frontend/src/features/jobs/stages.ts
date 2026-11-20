import type { JobSummary } from "@/lib/api/types";

interface StepDef {
  key: string;
  label: string;
  detail: string;
}

const STEP_LIBRARY: Record<string, StepDef> = {
  preparing: { key: "preparing", label: "Taking measurements", detail: "Reading your profile, base resume, fact bank, and the posting" },
  drafting: { key: "drafting", label: "Cutting the pattern", detail: "Claude tailors the summary, bullets, and skills to this role" },
  structuring: { key: "structuring", label: "Pinning it together", detail: "Turning the draft into editable content" },
  validating: { key: "validating", label: "Checking every seam", detail: "Citations, numbers, never-claim list, keyword coverage" },
  cover_letter: { key: "cover_letter", label: "Writing the cover letter", detail: "Built only from the validated resume content" },
  rendering: { key: "rendering", label: "Stitching the document", detail: "Applying your template to a Word document" },
  profiling: { key: "profiling", label: "Reading your resume", detail: "Drafting titles, role keywords and level from your history" },
  ideating: { key: "ideating", label: "Sketching ideas", detail: "Thinking of companies that fit your history" },
  discovering: { key: "discovering", label: "Finding the doors", detail: "Locating each company's careers page" },
  sweeping: { key: "sweeping", label: "Casting a wide net", detail: "Searching job boards for leads" },
  crosswalking: { key: "crosswalking", label: "Tracing to the source", detail: "Matching board leads to careers-page postings" },
  filtering: { key: "filtering", label: "Sorting the bolts", detail: "Applying level, location, pay and freshness rules" },
  scoring: { key: "scoring", label: "Checking the fit", detail: "Claude reads each posting against your real experience" },
  researching: { key: "researching", label: "Reading up on them", detail: "Sourced notes on each company behind your top results" },
  verifying: { key: "verifying", label: "Pressing", detail: "Confirming each posting is still live" },
  ranking: { key: "ranking", label: "Laying it out", detail: "Ranking by fit and freshness" },
  pdf: { key: "pdf", label: "Pressing the PDF", detail: "Microsoft Word renders the final PDF" },
};

export function stepsFor(job: Pick<JobSummary, "kind" | "stages_seen">, opts: { coverLetter?: boolean } = {}): StepDef[] {
  const keysByKind: Record<string, string[]> = {
    generate: ["preparing", "drafting", "structuring", "validating", ...(opts.coverLetter ? ["cover_letter"] : []), "rendering", "pdf"],
    render: ["preparing", "validating", "rendering", "pdf"],
    fact_bank: ["preparing", "drafting", "validating"],
    ingest: ["preparing", "drafting", "validating"],
    interview: ["preparing", "drafting", "validating"],
    job_search: ["preparing", "ideating", "discovering", "sweeping", "crosswalking", "filtering", "scoring", "verifying", "researching", "ranking"],
    job_search_suggest: ["preparing", "ideating"],
    job_search_draft: ["preparing", "profiling"],
    job_search_discover: ["discovering"],
  };
  const keys = [...(keysByKind[job.kind] ?? ["preparing"])];
  // A stage the pipeline reported that we didn't predict (e.g. a cover
  // letter) still gets a row, in order.
  for (const seen of job.stages_seen ?? []) {
    if (seen !== "done" && !keys.includes(seen) && STEP_LIBRARY[seen]) {
      const pdfIdx = keys.indexOf("rendering");
      keys.splice(pdfIdx >= 0 ? pdfIdx : keys.length, 0, seen);
    }
  }
  return keys.map((k) => STEP_LIBRARY[k]);
}

export type StepState = "done" | "active" | "failed" | "pending" | "skipped";

/**
 * Where each step stands, from the job's current stage and status. Pure, so
 * the stepper's behavior is unit-tested without a server.
 */
export function stepStates(steps: StepDef[], job: Pick<JobSummary, "status" | "stage" | "stages_seen"> | null): StepState[] {
  if (!job) return steps.map(() => "pending");
  const keys = steps.map((s) => s.key);
  const seen = new Set(job.stages_seen ?? []);
  const current = keys.indexOf(job.stage);
  const furthest = Math.max(current, ...keys.map((k, i) => (seen.has(k) ? i : -1)));

  return steps.map((step, i) => {
    // Every "::stage" line is recorded, so a step never seen on a successful
    // run genuinely didn't happen (e.g. no Word, so no PDF export).
    if (job.status === "succeeded") return seen.has(step.key) || i === 0 ? "done" : "skipped";
    if (job.status === "queued") return "pending";
    if (i < furthest) return "done";
    if (i === furthest) {
      if (job.status === "failed" || job.status === "cancelled") return "failed";
      return "active";
    }
    return "pending";
  });
}

export function progressPercent(states: StepState[]): number {
  if (!states.length) return 0;
  const done = states.filter((s) => s === "done" || s === "skipped").length;
  const active = states.includes("active") ? 0.5 : 0;
  return Math.round(((done + active) / states.length) * 100);
}
