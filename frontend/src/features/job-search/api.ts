import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { BoardCard, Column, Posting, Preferences, Readiness, RunReport, RunSummary, Suggestion, Target } from "./types";

export const jsKeys = {
  all: ["job-search"] as const,
  readiness: ["job-search", "readiness"] as const,
  prefs: ["job-search", "preferences"] as const,
  targets: ["job-search", "targets"] as const,
  suggestions: ["job-search", "suggestions"] as const,
  postings: ["job-search", "postings"] as const,
  posting: (id: string) => ["job-search", "posting", id] as const,
  runs: ["job-search", "runs"] as const,
  run: (id: string) => ["job-search", "run", id] as const,
  pipeline: ["job-search", "pipeline"] as const,
};

export const useReadiness = () =>
  useQuery({ queryKey: jsKeys.readiness, queryFn: () => api.get<Readiness>("/api/job-search/readiness"), staleTime: 15_000 });

export const usePreferences = () =>
  useQuery({ queryKey: jsKeys.prefs, queryFn: () => api.get<Preferences>("/api/job-search/preferences") });

export const useTargets = () =>
  useQuery({ queryKey: jsKeys.targets, queryFn: () => api.get<{ targets: Target[]; max: number }>("/api/job-search/targets") });

export const useSuggestions = () =>
  useQuery({
    queryKey: jsKeys.suggestions,
    queryFn: () => api.get<{ exists: boolean; companies: Suggestion[]; tier?: string }>("/api/job-search/targets/suggestions/latest"),
  });

export const usePostings = () =>
  useQuery({ queryKey: jsKeys.postings, queryFn: () => api.get<Posting[]>("/api/job-search/postings") });

export const useRuns = () => useQuery({ queryKey: jsKeys.runs, queryFn: () => api.get<RunSummary[]>("/api/job-search/runs") });

export const useRun = (id: string | undefined) =>
  useQuery({
    queryKey: jsKeys.run(id ?? ""),
    queryFn: () => api.get<RunReport>(`/api/job-search/runs/${id}`),
    enabled: !!id,
  });

export const usePipeline = () =>
  useQuery({
    queryKey: jsKeys.pipeline,
    queryFn: () => api.get<{ columns: Column[]; cards: BoardCard[] }>("/api/job-search/pipeline"),
  });
