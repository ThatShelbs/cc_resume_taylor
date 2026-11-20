import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, RefreshCw, SlidersHorizontal, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { stepsFor } from "@/features/jobs/stages";
import { useJobs, useJobState } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys, useSettings, useSystem } from "@/lib/api/queries";
import type { JobSummary, Project } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { jsKeys, usePostings, usePreferences, useReadiness, useRun, useRuns, useTargets } from "./api";
import { PostingCard } from "./components/PostingCard";
import { atsLabel, REJECTION_LABELS } from "./format";
import { searchSummary, filterPostings, runSummary, type Filters } from "./discover";
import { TailorDialog } from "./TailorDialog";
import type { Posting } from "./types";

type Sort = "overall" | "fresh" | "skills";
const SEARCH_KINDS = ["job_search", "job_search_draft"];

function sortPostings(list: Posting[], sort: Sort): Posting[] {
  const skills = (p: Posting) => ["skills", "leadership", "domain", "seniority_realism"].reduce((n, k) => n + (p.fit?.subscores[k]?.score ?? 0), 0);
  const copy = [...list];
  if (sort === "fresh") return copy.sort((a, b) => (a.age_days ?? 999) - (b.age_days ?? 999) || (b.fit?.total ?? 0) - (a.fit?.total ?? 0));
  if (sort === "skills") return copy.sort((a, b) => skills(b) - skills(a));
  return copy.sort((a, b) => (b.fit?.total ?? 0) - (a.fit?.total ?? 0));
}

function ReadinessBanner() {
  const { data } = useReadiness();
  if (!data || data.tier === "full") return null;
  if (data.tier === "partial") {
    return (
      <Callout tone="info" title="Scores use your resume text" action={<Button asChild size="sm" variant="outline"><Link to={ROUTES.evidence}>Build your fact bank</Link></Button>}>
        A fact bank lets every score cite the exact facts behind it, and makes tailoring stronger.
      </Callout>
    );
  }
  return (
    <Callout
      tone="info"
      title="Add your resume for a search that knows you"
      action={<Button asChild size="sm" variant="outline"><Link to={ROUTES.resume}>Add your resume</Link></Button>}
    >
      Without a resume, results are scored as a "Preference match" against what you tell us on the Preferences tab. With it, your titles, level and skills are drafted for you and every score cites your real experience.
    </Callout>
  );
}

function RunProgress({ jobId }: { jobId: string }) {
  const stream = useJobState(jobId);
  const job = stream?.job;
  if (!job) return <p className="text-sm text-muted-foreground">Starting...</p>;
  const steps = stepsFor(job);
  const step = steps.find((s) => s.key === job.stage);
  const last = stream?.lines.filter((l) => l.trim()).at(-1);
  return (
    <div className="grid gap-1" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className="relative flex size-2"><span className="absolute inset-0 animate-ping rounded-full bg-primary/50" /><span className="relative size-2 rounded-full bg-primary" /></span>
        {step?.label ?? "Working"}
      </div>
      <p className="text-xs text-muted-foreground">{step?.detail}</p>
      {last && <p className="truncate text-xs text-muted-foreground">{last}</p>}
    </div>
  );
}

const FILTER_CHIPS: { key: keyof Filters; label: string; hint: string }[] = [
  { key: "isNew", label: "New", hint: "First seen in the latest run" },
  { key: "fresh", label: "Fresh", hint: "Posted within about 2 days" },
  { key: "strong", label: "Fit 70+", hint: "Strong matches only" },
  { key: "careersOnly", label: "Not on LinkedIn", hint: "Listed on the company's own site only, which usually means fewer applicants" },
];

function coverageStatus(c: { status: string; note: string }): { text: string; tone: string } {
  if (c.status === "ok") return { text: "Connected", tone: "text-success" };
  if (c.status === "empty") return { text: "No openings right now", tone: "text-muted-foreground" };
  return { text: c.note || "Not connected", tone: "text-warning" };
}

export default function DiscoverPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { track } = useJobs();
  const { data: settings } = useSettings();
  const { data: readiness } = useReadiness();
  const { data: prefs } = usePreferences();
  const { data: targetData } = useTargets();
  const { data: system } = useSystem();
  const { data: postings = [] } = usePostings();
  const { data: runs = [] } = useRuns();
  const latest = runs[0]?.id;
  const { data: report } = useRun(latest);

  const [jobId, setJobId] = useState<string | null>(null);
  const [view, setView] = useState<"latest" | "saved">("latest");
  const [sort, setSort] = useState<Sort>("overall");
  const [filters, setFilters] = useState<Filters>({ isNew: false, fresh: false, strong: false, careersOnly: false });
  const [tailorFor, setTailorFor] = useState<Posting | null>(null);
  const [starting, setStarting] = useState(false);
  const autoStarted = useRef(false);

  const running = jobId ?? system?.active_jobs.find((j) => SEARCH_KINDS.includes(j.kind))?.id ?? null;
  const runningStream = useJobState(running);
  const busy = starting || (!!running && !(runningStream?.done ?? false));

  const startSearch = async () => {
    const count = prefs?.count ?? 5;
    const job = await api.post<JobSummary>("/api/job-search/search", { count });
    setJobId(job.id);
    track(job, { title: `Searching for your top ${count}`, open: false, successMessage: "Search finished" });
  };

  const refresh = async () => {
    setStarting(true);
    try {
      await startSearch();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setStarting(false);
    }
  };

  // First visit with a resume or profile: draft the settings, then run the first search, with no clicks.
  useEffect(() => {
    if (!readiness?.first_run || autoStarted.current) return;
    autoStarted.current = true;
    setStarting(true);
    api.post<JobSummary>("/api/job-search/preferences/draft")
      .then((job) => {
        setJobId(job.id);
        track(job, {
          title: "Setting up your search",
          open: false,
          successMessage: "Settings drafted. Starting your first search.",
          onSuccess: async () => {
            await Promise.all([qc.invalidateQueries({ queryKey: jsKeys.prefs }), qc.invalidateQueries({ queryKey: jsKeys.readiness })]);
            try {
              await startSearch();
            } catch (e) {
              toast.error((e as Error).message);
            }
          },
          onFailure: () => toast.error("Could not draft your settings. Open Settings to fill them in."),
        });
      })
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setStarting(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readiness?.first_run]);

  // One click: tailor with the saved defaults. Anything that needs a choice (missing profile, interview
  // first) opens the options dialog instead.
  const quickTailor = async (p: Posting) => {
    if (!readiness?.has_profile || !readiness?.has_resume || settings?.interview_default) {
      setTailorFor(p);
      return;
    }
    try {
      const { project, job } = await api.post<{ project: Project; job: JobSummary | null }>(`/api/job-search/postings/${p.id}/tailor`, { generate: true });
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: jsKeys.all });
      if (job) track(job, { title: `Tailoring for ${project.company || project.name}`, coverLetter: settings?.cover_letter_default, successMessage: "Your tailored resume is ready" });
      navigate(ROUTES.project(project.id));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const addCompany = async (name: string) => {
    try {
      await api.post("/api/job-search/targets/import", { items: [{ name }] });
      qc.invalidateQueries({ queryKey: jsKeys.targets });
      qc.invalidateQueries({ queryKey: jsKeys.readiness });
      toast.success("Added to your target companies");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const byId = useMemo(() => new Map(postings.map((p) => [p.id, p])), [postings]);
  const base = useMemo(
    () => (view === "saved" ? postings : (report?.results ?? []).map((r) => byId.get(r.id)).filter((p): p is Posting => !!p)),
    [view, postings, report, byId],
  );
  const shown = useMemo(() => sortPostings(filterPostings(base, filters), sort), [base, filters, sort]);
  const targetNames = new Set((targetData?.targets ?? []).map((t) => t.name.toLowerCase()));
  const activeFilters = Object.values(filters).some(Boolean);

  const groupedRejections = useMemo(() => {
    const g: Record<string, NonNullable<typeof report>["rejected"]> = {};
    for (const r of report?.rejected ?? []) (g[r.reason] ??= []).push(r);
    return g;
  }, [report]);

  const chips = prefs ? searchSummary(prefs) : [];
  const summary = report ? runSummary(report) : null;

  return (
    <div className="grid gap-6">
      <ReadinessBanner />

      <Card className="grid gap-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">Your search</div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {chips.length ? chips.map((c) => <Badge key={c} variant="secondary">{c}</Badge>) : <span className="text-sm text-muted-foreground">Using what is on your resume.</span>}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button asChild variant="outline" size="sm"><Link to={ROUTES.jobSearchPreferences}><SlidersHorizontal /> Edit</Link></Button>
            <Button variant="gradient" onClick={refresh} loading={starting && !running} disabled={busy}>
              <RefreshCw /> {runs.length ? "Refresh" : "Find roles"}
            </Button>
          </div>
        </div>
        {busy && running && <RunProgress jobId={running} />}
        {!busy && runs.length > 0 && !summary?.empty && report?.finished && (
          <p className="text-xs text-muted-foreground">Last run {new Date(report.finished).toLocaleString()}. Fresh postings rank higher: a role open 14+ days may already be in panel interviews.</p>
        )}
      </Card>

      {report?.notes?.length ? (
        <Callout tone="warning" title="About the last run">
          {report.notes.join(" ")}
        </Callout>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1 rounded-lg border p-0.5 text-sm" role="group" aria-label="Which postings">
            {(["latest", "saved"] as const).map((v) => (
              <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
                className={cn("rounded-md px-3 py-1 font-medium", view === v ? "bg-secondary" : "text-muted-foreground")}>
                {v === "latest" ? "Latest run" : `All saved (${postings.length})`}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter postings">
            {FILTER_CHIPS.map((f) => (
              <button key={f.key} type="button" title={f.hint} aria-pressed={filters[f.key]} onClick={() => setFilters((cur) => ({ ...cur, [f.key]: !cur[f.key] }))}
                className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  filters[f.key] ? "border-primary/40 bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="w-52">
          <Select value={sort} onValueChange={(v) => setSort(v as Sort)} aria-label="Sort postings"
            options={[{ value: "overall", label: "Best fit and freshness" }, { value: "fresh", label: "Freshest first" }, { value: "skills", label: "Best experience match" }]} />
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title={busy ? "Searching..." : activeFilters && base.length ? "No postings match these filters" : "No results yet"}
          description={activeFilters && base.length ? "Turn a filter off to see the rest." : "Press Find roles to see the best postings from company career pages, ranked by fit and freshness."}
        />
      ) : (
        <div className="grid gap-3">
          {shown.map((p) => (
            <PostingCard key={p.id} posting={p} onTailor={quickTailor} onTailorOptions={setTailorFor} onAddCompany={(n) => addCompany(n)} companyIsTarget={targetNames.has(p.company.toLowerCase())} />
          ))}
        </div>
      )}

      {view === "latest" && report && summary && (
        <div className="grid gap-3">
          <p className="text-xs text-muted-foreground">{summary.line}</p>
          <details className="rounded-lg border px-4 py-3 text-sm">
            <summary className="flex cursor-pointer items-center gap-2 font-medium"><ChevronDown className="size-4" />Details of this run</summary>
            <div className="mt-3 grid gap-4">
              <details className="rounded-lg border px-4 py-3 text-sm">
                <summary className="cursor-pointer font-medium">Rejected and why ({report.rejected.length})</summary>
                <div className="mt-3 grid gap-4">
                  {Object.entries(groupedRejections).map(([reason, list]) => (
                    <div key={reason}>
                      <div className="text-xs font-medium">{REJECTION_LABELS[reason] ?? reason} ({list.length})</div>
                      <ul className="mt-1 grid gap-1 text-xs text-muted-foreground">
                        {list.slice(0, 25).map((r) => <li key={r.id}>{r.company}: {r.title}. {r.evidence}</li>)}
                        {list.length > 25 && <li>and {list.length - 25} more</li>}
                      </ul>
                    </div>
                  ))}
                  {report.rejected.length === 0 && <p className="text-xs text-muted-foreground">Nothing was rejected.</p>}
                </div>
              </details>
              <details className="rounded-lg border px-4 py-3 text-sm">
                <summary className="cursor-pointer font-medium">Careers pages searched ({report.coverage.length})</summary>
                <table className="mt-3 w-full text-left text-xs">
                  <thead className="text-muted-foreground"><tr><th className="py-1 font-medium">Company</th><th className="font-medium">Source</th><th className="font-medium">Your role / listed</th><th className="font-medium">Status</th></tr></thead>
                  <tbody>
                    {report.coverage.map((c) => {
                      const st = coverageStatus(c);
                      return (
                        <tr key={c.company + c.origin} className="border-t">
                          <td className="py-1.5">
                            {c.careers_url ? (
                              <a href={c.careers_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline" title="Open the company's careers page">
                                {c.company}<ExternalLink className="size-3" aria-hidden />
                              </a>
                            ) : c.company}
                            {c.search_url && (
                              <a href={c.search_url} target="_blank" rel="noreferrer" className="ml-2 text-muted-foreground underline-offset-2 hover:underline">search there</a>
                            )}
                          </td>
                          <td>{c.ats ? atsLabel(c.ats) : "None found"}</td>
                          <td className="tabular-nums">{c.count}{c.listed !== undefined ? ` / ${c.listed}` : ""}</td>
                          <td className={st.tone}>{st.text}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </details>
              {report.ideated?.length > 0 && (
                <details className="rounded-lg border px-4 py-3 text-sm">
                  <summary className="cursor-pointer font-medium">Companies Claude thought of for this run ({report.ideated.length})</summary>
                  <ul className="mt-3 grid gap-1.5 text-xs">
                    {report.ideated.map((c) => (
                      <li key={c.name} className="flex items-center justify-between gap-3">
                        <span><span className="font-medium">{c.name}</span> <span className="text-muted-foreground">{c.rationale}</span></span>
                        {!targetNames.has(c.name.toLowerCase()) && <Button size="sm" variant="ghost" onClick={() => addCompany(c.name)}>Add</Button>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </details>
        </div>
      )}

      <TailorDialog posting={tailorFor} open={!!tailorFor} onOpenChange={(o) => !o && setTailorFor(null)} />
    </div>
  );
}

