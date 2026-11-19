import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, Radar, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { stepsFor } from "@/features/jobs/stages";
import { useJobs, useJobState } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { useSystem } from "@/lib/api/queries";
import type { JobSummary } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { jsKeys, usePostings, usePreferences, useReadiness, useRun, useRuns, useTargets } from "./api";
import { PostingCard } from "./components/PostingCard";
import { atsLabel, REJECTION_LABELS, SOURCE_LABELS } from "./format";
import { TailorDialog } from "./TailorDialog";
import type { AccountStatus, Depth, Posting, Source } from "./types";

function accountGate(accounts: AccountStatus[] | undefined, site: string): string | null {
  const a = accounts?.find((x) => x.site === site);
  if (!a) return "Not available";
  if (a.cooldown_until) return `Paused for today (${a.cooldown_reason || "bot check"})`;
  if (!a.connected && !a.login_optional) return "Connect your account in Preferences";
  return null;
}

const DEPTH_INFO: Record<Depth, { label: string; hint: string }> = {
  quick: { label: "Quick", hint: "Your companies plus a short board sweep. A few minutes." },
  standard: { label: "Standard", hint: "Adds about 30 ideated companies and a wider sweep. 5 to 8 minutes." },
  deep: { label: "Deep", hint: "75 ideated companies and about 60 queries. Runs in the background for 15 to 25 minutes." },
};

type Sort = "overall" | "fresh" | "skills";

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
      title="You can search before you set anything up"
      action={<Button asChild size="sm" variant="outline"><Link to={ROUTES.resume}>Add your resume</Link></Button>}
    >
      Without a resume, results are scored as a "Preference match" against what you tell us on the Preferences tab. Add your profile and base resume to get evidence-based fit scores and one-click tailoring.
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

export default function DiscoverPage() {
  const qc = useQueryClient();
  const { track } = useJobs();
  const { data: readiness } = useReadiness();
  const { data: prefs } = usePreferences();
  const { data: targetData } = useTargets();
  const { data: system } = useSystem();
  const { data: postings = [] } = usePostings();
  const { data: runs = [] } = useRuns();
  const latest = runs[0]?.id;
  const { data: report } = useRun(latest);

  const [count, setCount] = useState<number | null>(null);
  const [depth, setDepth] = useState<Depth | null>(null);
  const [sources, setSources] = useState<Source[] | null>(null);
  const [recency, setRecency] = useState<string>("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [view, setView] = useState<"latest" | "saved">("latest");
  const [sort, setSort] = useState<Sort>("overall");
  const [tailorFor, setTailorFor] = useState<Posting | null>(null);

  const effCount = count ?? prefs?.count ?? 5;
  const effDepth = depth ?? prefs?.depth ?? "standard";
  const effSources = sources ?? prefs?.sources ?? ["targets", "ideated", "boards"];
  const targetCount = targetData?.targets.length ?? 0;
  const running = jobId ?? system?.active_jobs.find((j) => j.kind === "job_search")?.id ?? null;
  const runningStream = useJobState(running);
  const busy = !!running && !(runningStream?.done ?? false);

  const start = useMutation({
    mutationFn: () =>
      api.post<JobSummary>("/api/job-search/search", {
        count: effCount, depth: effDepth, sources: effSources, recency_days: recency ? Number(recency) : undefined,
      }),
    onSuccess: (job) => {
      setJobId(job.id);
      track(job, { title: `Searching for your top ${effCount}`, open: false, successMessage: "Search finished" });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const addCompany = useMutation({
    mutationFn: (name: string) => api.post("/api/job-search/targets/import", { items: [{ name }] }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: jsKeys.targets });
      qc.invalidateQueries({ queryKey: jsKeys.readiness });
      toast.success("Added to your target companies");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const byId = useMemo(() => new Map(postings.map((p) => [p.id, p])), [postings]);
  const shown = useMemo(() => {
    const list = view === "saved" ? postings : (report?.results ?? []).map((r) => byId.get(r.id)).filter((p): p is Posting => !!p);
    return sortPostings(list, sort);
  }, [view, postings, report, byId, sort]);
  const targetNames = new Set((targetData?.targets ?? []).map((t) => t.name.toLowerCase()));

  const toggleSource = (s: Source) => setSources(effSources.includes(s) ? effSources.filter((x) => x !== s) : [...effSources, s]);
  const sourceDisabled = (s: Source): string | null =>
    s === "targets" && targetCount === 0 ? "Add companies on the Companies tab"
    : s === "linkedin" && !prefs?.linkedin_direct ? "Turn on in Preferences (opt-in)"
    : s.endsWith("_account") ? accountGate(readiness?.accounts, s.replace("_account", ""))
    : null;

  const groupedRejections = useMemo(() => {
    const g: Record<string, typeof report extends undefined ? never : NonNullable<typeof report>["rejected"]> = {};
    for (const r of report?.rejected ?? []) (g[r.reason] ??= []).push(r);
    return g;
  }, [report]);

  return (
    <div className="grid gap-6">
      <ReadinessBanner />

      <Card className="grid gap-4 p-5">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="grid gap-1.5 text-sm font-medium">
            How many roles
            <Select value={String(effCount)} onValueChange={(v) => setCount(Number(v))} aria-label="How many roles"
              options={(readiness?.options.counts ?? [3, 5, 10, 20]).map((n) => ({ value: String(n), label: `Best ${n}` }))} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            How deep
            <Select value={effDepth} onValueChange={(v) => setDepth(v as Depth)} aria-label="How deep"
              options={(Object.keys(DEPTH_INFO) as Depth[]).map((d) => ({ value: d, label: DEPTH_INFO[d].label }))} />
          </label>
          <label className="grid gap-1.5 text-sm font-medium">
            Posted within
            <Select value={recency || String(prefs?.recency_days ?? 14)} onValueChange={setRecency} aria-label="Posted within"
              options={[7, 14, 21, 30].map((d) => ({ value: String(d), label: `${d} days` }))} />
          </label>
        </div>
        <p className="text-xs text-muted-foreground">{DEPTH_INFO[effDepth].hint} Fresh postings rank higher: a role open 14+ days may already be in panel interviews.</p>

        <div className="flex flex-wrap gap-2" role="group" aria-label="Where to search">
          {(readiness?.options.sources ?? (Object.keys(SOURCE_LABELS) as Source[])).map((s) => {
            const why = sourceDisabled(s);
            const on = effSources.includes(s) && !why;
            return (
              <button
                key={s}
                type="button"
                disabled={!!why}
                title={why ?? undefined}
                aria-pressed={on}
                onClick={() => toggleSource(s)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                  on ? "border-primary/40 bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {SOURCE_LABELS[s]}
                {s === "targets" && targetCount > 0 ? ` (${targetCount})` : ""}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="gradient" onClick={() => start.mutate()} loading={start.isPending} disabled={busy || effSources.filter((s) => !sourceDisabled(s)).length === 0}>
            <Radar /> Run search
          </Button>
          {busy && running && <RunProgress jobId={running} />}
        </div>
      </Card>

      {report?.notes?.length ? (
        <Callout tone="warning" title="About the last run">
          {report.notes.join(" ")}
        </Callout>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border p-0.5 text-sm" role="group" aria-label="Which postings">
          {(["latest", "saved"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}
              className={cn("rounded-md px-3 py-1 font-medium", view === v ? "bg-secondary" : "text-muted-foreground")}>
              {v === "latest" ? "Latest run" : `All saved (${postings.length})`}
            </button>
          ))}
        </div>
        <div className="w-52">
          <Select value={sort} onValueChange={(v) => setSort(v as Sort)} aria-label="Sort postings"
            options={[{ value: "overall", label: "Best fit and freshness" }, { value: "fresh", label: "Freshest first" }, { value: "skills", label: "Best experience match" }]} />
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title={busy ? "Searching..." : "No results yet"}
          description="Run a search to see the best roles from company career pages, ranked by fit and freshness."
        />
      ) : (
        <div className="grid gap-3">
          {shown.map((p) => (
            <PostingCard key={p.id} posting={p} onTailor={setTailorFor} onAddCompany={(n) => addCompany.mutate(n)} companyIsTarget={targetNames.has(p.company.toLowerCase())} />
          ))}
        </div>
      )}

      {view === "latest" && report && (
        <div className="grid gap-3">
          {report.careers_only_share !== undefined && report.results.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {Math.round(report.careers_only_share * 100)}% of these were found on careers pages only. Seen {report.postings_seen ?? 0} postings in {report.timings?.total ?? 0}s.
            </p>
          )}
          <details className="rounded-lg border px-4 py-3 text-sm">
            <summary className="flex cursor-pointer items-center gap-2 font-medium"><ChevronDown className="size-4" />Rejected and why ({report.rejected.length})</summary>
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
            <summary className="flex cursor-pointer items-center gap-2 font-medium"><ChevronDown className="size-4" />Careers pages searched ({report.coverage.length})</summary>
            <table className="mt-3 w-full text-left text-xs">
              <thead className="text-muted-foreground"><tr><th className="py-1 font-medium">Company</th><th className="font-medium">Source</th><th className="font-medium">Postings</th><th className="font-medium">Status</th></tr></thead>
              <tbody>
                {report.coverage.map((c) => (
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
                    <td className="tabular-nums">{c.count}</td>
                    <td className={c.status === "ok" ? "text-success" : "text-warning"}>{c.status === "ok" ? "Connected" : c.note || "Not connected"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
          {report.ideated?.length > 0 && (
            <details className="rounded-lg border px-4 py-3 text-sm">
              <summary className="flex cursor-pointer items-center gap-2 font-medium"><ChevronDown className="size-4" />Companies Claude thought of for this run ({report.ideated.length})</summary>
              <ul className="mt-3 grid gap-1.5 text-xs">
                {report.ideated.map((c) => (
                  <li key={c.name} className="flex items-center justify-between gap-3">
                    <span><span className="font-medium">{c.name}</span> <span className="text-muted-foreground">{c.rationale}</span></span>
                    {!targetNames.has(c.name.toLowerCase()) && <Button size="sm" variant="ghost" onClick={() => addCompany.mutate(c.name)}>Add</Button>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <TailorDialog posting={tailorFor} open={!!tailorFor} onOpenChange={(o) => !o && setTailorFor(null)} />
    </div>
  );
}
