/** The small pill shown while a background job runs and its sheet is closed. */
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import { stepStates, stepsFor } from "@/features/jobs/stages";
import type { Tracked } from "@/features/jobs/types";
import type { JobStream } from "@/lib/api/sse";

export function FloatingIndicator({ entry, stream, onOpen }: { entry: Tracked; stream: JobStream | undefined; onOpen: () => void }) {
  const job = stream?.job ?? entry.job;
  const steps = stepsFor(job, { coverLetter: entry.opts.coverLetter });
  const states = stepStates(steps, job);
  const active = steps[states.indexOf("active")];
  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 16, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 400, damping: 30 }}
      onClick={onOpen}
      className="fixed bottom-5 right-5 z-40 flex max-w-[calc(100vw-2.5rem)] items-center gap-3 rounded-full border bg-popover py-2 pl-2 pr-4 text-left shadow-lift transition-colors hover:bg-secondary"
    >
      <span className="flex size-8 items-center justify-center rounded-full bg-primary/10">
        <Loader2 className="size-4 animate-spin text-primary" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{entry.opts.title ?? job.label}</span>
        <span className="block truncate text-xs text-muted-foreground">{active?.label ?? "Queued"}</span>
      </span>
    </motion.button>
  );
}
