/**
 * Tracks every background job the UI started (or found running on load):
 * streams its progress, shows the progress sheet or a floating indicator,
 * and on completion refreshes the affected data and toasts the outcome.
 */
import { useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FloatingIndicator } from "@/features/jobs/components/FloatingIndicator";
import { JobSheet } from "@/features/jobs/components/JobSheet";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import { useJobStream, type JobStream } from "@/lib/api/sse";
import type { JobSummary } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import type { JobActions, Tracked, TrackOptions } from "./types";

export type { TrackOptions } from "./types";


const ActionsContext = createContext<JobActions | null>(null);
const StreamsContext = createContext<Record<string, JobStream>>({});

export function useJobs(): JobActions {
  const ctx = useContext(ActionsContext);
  if (!ctx) throw new Error("useJobs must be used inside <JobCenter>");
  return ctx;
}

export function useJobState(jobId: string | null | undefined): JobStream | null {
  const streams = useContext(StreamsContext);
  return jobId ? (streams[jobId] ?? null) : null;
}

function JobWatcher({ id, onUpdate }: { id: string; onUpdate: (id: string, s: JobStream) => void }) {
  const stream = useJobStream(id);
  useEffect(() => onUpdate(id, stream), [id, stream, onUpdate]);
  return null;
}

export function JobCenter({ children }: { children: ReactNode }) {
  const [tracked, setTracked] = useState<Record<string, Tracked>>({});
  const [streams, setStreams] = useState<Record<string, JobStream>>({});
  const [openId, setOpenId] = useState<string | null>(null);
  const finished = useRef(new Set<string>());
  const qc = useQueryClient();
  const navigate = useNavigate();

  const track = useCallback((job: JobSummary, opts: TrackOptions = {}) => {
    setTracked((t) => ({ ...t, [job.id]: { job, opts } }));
    if (opts.open !== false) setOpenId(job.id);
  }, []);

  // Pick up jobs that were already running when the page (re)loaded.
  useEffect(() => {
    api
      .get<JobSummary[]>("/api/jobs")
      .then((jobs) => jobs.forEach((j) => track(j, { open: false })))
      .catch(() => undefined);
  }, [track]);

  const onUpdate = useCallback(
    (id: string, s: JobStream) => {
      setStreams((prev) => (prev[id] === s ? prev : { ...prev, [id]: s }));
      if (!s.done || !s.job || finished.current.has(id)) return;
      finished.current.add(id);
      const entry = tracked[id];
      const job = s.job;
      const pid = job.project_id;
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: keys.system });
      if (pid) qc.invalidateQueries({ queryKey: ["project", pid] });
      if (job.kind === "fact_bank") qc.invalidateQueries({ queryKey: keys.facts });

      const view = pid && !location.pathname.includes(pid) ? { label: "Open", onClick: () => navigate(ROUTES.project(pid)) } : undefined;
      if (job.status === "succeeded") {
        entry?.opts.onSuccess?.(job);
        toast.success(entry?.opts.successMessage ?? `${job.label}: done`, { action: view });
      } else if (job.status === "failed") {
        entry?.opts.onFailure?.(job);
        toast.error(job.deny?.length ? "Blocked by your never-claim list" : "Something went wrong", {
          description: job.hint ?? job.error ?? undefined,
          action: { label: "Details", onClick: () => setOpenId(id) },
          duration: 10_000,
        });
      }
    },
    [tracked, qc, navigate],
  );

  const actions = useMemo<JobActions>(() => ({ track, open: setOpenId }), [track]);
  const openEntry = openId ? tracked[openId] : null;
  const running = Object.values(tracked).filter((t) => !streams[t.job.id]?.done);
  const indicator = running.find((t) => t.job.id !== openId);

  return (
    <ActionsContext.Provider value={actions}>
      <StreamsContext.Provider value={streams}>
        {children}
        {Object.keys(tracked).map((id) => (
          <JobWatcher key={id} id={id} onUpdate={onUpdate} />
        ))}
        <JobSheet
          entry={openEntry}
          stream={openId ? streams[openId] : undefined}
          onOpenChange={(o) => !o && setOpenId(null)}
        />
        <AnimatePresence>
          {indicator && (
            <FloatingIndicator
              key={indicator.job.id}
              entry={indicator}
              stream={streams[indicator.job.id]}
              onOpen={() => setOpenId(indicator.job.id)}
            />
          )}
        </AnimatePresence>
      </StreamsContext.Provider>
    </ActionsContext.Provider>
  );
}
