import type { JobSummary } from "@/lib/api/types";

export interface TrackOptions {
  title?: string;
  open?: boolean;
  coverLetter?: boolean;
  successMessage?: string;
  onSuccess?: (job: JobSummary) => void;
  onFailure?: (job: JobSummary) => void;
}

export interface Tracked {
  job: JobSummary;
  opts: TrackOptions;
}

export interface JobActions {
  track: (job: JobSummary, opts?: TrackOptions) => void;
  open: (jobId: string) => void;
}
