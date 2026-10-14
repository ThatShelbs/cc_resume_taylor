/** The slide-over that shows one background job: its steps, elapsed time, errors and live log. */
import { Check, ChevronDown, CircleSlash, Loader2, TerminalSquare, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { progressPercent, stepStates, stepsFor, type StepState } from "../stages";
import type { Tracked } from "../types";
import { api } from "@/lib/api/client";
import type { JobStream } from "@/lib/api/sse";
import type { JobSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function useElapsed(job: JobSummary | null | undefined, done: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  const base = useRef<{ at: number; elapsed: number } | null>(null);
  useEffect(() => {
    if (job?.elapsed != null) base.current = { at: Date.now(), elapsed: job.elapsed };
  }, [job?.elapsed, job?.status, job?.stage]);
  useEffect(() => {
    if (done) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [done]);
  if (!base.current) return 0;
  return done ? base.current.elapsed : base.current.elapsed + (now - base.current.at) / 1000;
}

function fmtElapsed(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return m ? `${m}m ${sec.toString().padStart(2, "0")}s` : `${sec}s`;
}

function StepIcon({ state, index }: { state: StepState; index: number }) {
  if (state === "done")
    return (
      <span className="flex size-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
        <Check className="size-3.5" strokeWidth={3} />
      </span>
    );
  if (state === "active")
    return (
      <span className="relative flex size-6 items-center justify-center">
        <span className="absolute inset-0 animate-pulse-ring rounded-full bg-primary/40" />
        <span className="relative flex size-6 items-center justify-center rounded-full border-2 border-primary bg-background">
          <Loader2 className="size-3.5 animate-spin text-primary" />
        </span>
      </span>
    );
  if (state === "failed")
    return (
      <span className="flex size-6 items-center justify-center rounded-full bg-destructive text-destructive-foreground">
        <X className="size-3.5" strokeWidth={3} />
      </span>
    );
  if (state === "skipped")
    return (
      <span className="flex size-6 items-center justify-center rounded-full border border-dashed text-muted-foreground">
        <CircleSlash className="size-3" />
      </span>
    );
  return (
    <span className="flex size-6 items-center justify-center rounded-full border bg-background text-[11px] font-medium text-muted-foreground">
      {index + 1}
    </span>
  );
}

export function JobSheet({
  entry,
  stream,
  onOpenChange,
}: {
  entry: Tracked | null;
  stream: JobStream | undefined;
  onOpenChange: (open: boolean) => void;
}) {
  const job = stream?.job ?? entry?.job ?? null;
  const done = !!stream?.done;
  const elapsed = useElapsed(job, done);
  const [showLog, setShowLog] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  const lines = stream?.lines ?? [];

  useEffect(() => {
    if (showLog && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines.length, showLog]);

  if (!entry || !job) return <Sheet open={false} onOpenChange={onOpenChange} />;

  const steps = stepsFor(job, { coverLetter: entry.opts.coverLetter });
  const states = stepStates(steps, job);
  const pct = progressPercent(states);
  const cancel = async () => {
    try {
      await api.post(`/api/jobs/${job.id}/cancel`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Sheet open onOpenChange={onOpenChange}>
      <SheetContent aria-describedby={undefined} className="sm:max-w-md">
        <div className="border-b px-6 pb-5 pt-6">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {job.status === "succeeded" ? "Finished" : job.status === "failed" ? "Stopped" : job.status === "cancelled" ? "Cancelled" : "Working"}
          </div>
          <h2 className="mt-1 pr-8 text-lg font-semibold tracking-tight">{entry.opts.title ?? job.label}</h2>
          <div className="mt-4 flex items-center gap-3">
            <Progress
              value={job.status === "succeeded" ? 100 : pct}
              className="h-1.5"
              indicatorClassName={cn(job.status === "failed" && "bg-destructive", job.status === "succeeded" && "bg-success")}
            />
            <span className="w-14 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{fmtElapsed(elapsed)}</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <ol className="relative grid gap-5">
            {steps.map((step, i) => (
              <li key={step.key} className="relative flex gap-3.5">
                {i < steps.length - 1 && (
                  <span
                    className={cn(
                      "absolute left-3 top-7 h-[calc(100%-0.25rem)] w-px -translate-x-1/2",
                      states[i] === "done" ? "bg-primary/60" : "bg-border",
                    )}
                  />
                )}
                <StepIcon state={states[i]} index={i} />
                <div className="min-w-0 pt-0.5">
                  <div
                    className={cn(
                      "text-sm font-medium leading-tight",
                      states[i] === "pending" && "text-muted-foreground",
                      states[i] === "skipped" && "text-muted-foreground line-through decoration-muted-foreground/40",
                    )}
                  >
                    {step.label}
                  </div>
                  <div className="mt-0.5 text-xs leading-snug text-muted-foreground">{step.detail}</div>
                </div>
              </li>
            ))}
          </ol>

          {job.status === "failed" && (
            <Callout tone="error" title={job.deny?.length ? "Blocked by your never-claim list" : "The run stopped"} className="mt-6">
              <span className="whitespace-pre-wrap">{job.hint ?? job.error}</span>
              {job.deny?.length > 0 && (
                <ul className="mt-2 grid gap-1.5">
                  {job.deny.map((d, i) => (
                    <li key={i} className="rounded-md bg-background/70 px-2 py-1 text-xs">
                      <span className="font-medium text-foreground">{d.where}</span>: matched <code>{d.pattern}</code>
                    </li>
                  ))}
                </ul>
              )}
            </Callout>
          )}

          <button
            type="button"
            onClick={() => setShowLog((v) => !v)}
            className="mt-6 flex w-full items-center gap-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <TerminalSquare className="size-3.5" />
            Live log ({lines.length} lines)
            <ChevronDown className={cn("ml-auto size-3.5 transition-transform", showLog && "rotate-180")} />
          </button>
          {showLog && (
            <pre
              ref={logRef}
              className="mt-2 max-h-72 overflow-auto rounded-lg border bg-muted/50 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground"
            >
              {lines.length ? lines.join("\n") : "Waiting for output..."}
            </pre>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t px-6 py-4">
          {!done && (
            <Button variant="ghost" onClick={cancel}>
              Cancel run
            </Button>
          )}
          <Button variant={done ? "default" : "outline"} onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Run in background"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
