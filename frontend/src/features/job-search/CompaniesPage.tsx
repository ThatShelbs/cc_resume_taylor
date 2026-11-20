import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileUp, Globe, Sparkles, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useJobs, useJobState } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { useSystem } from "@/lib/api/queries";
import type { JobSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { jsKeys, useReadiness, useSuggestions, useTargets } from "./api";
import { atsLabel } from "./format";
import type { Target } from "./types";

const CLUSTER_SHORT: Record<string, string> = {
  past_peers: "Past-employer peers",
  industry: "Industry leaders",
  adjacent: "Adjacent industries",
  growth: "Fast-growing",
  admired: "Admired",
};

interface AddResult { added: string[]; skipped: string[]; over_limit: string[]; total: number }

function RouteChip({ t }: { t: Target }) {
  const r = t.route;
  if (r.status === "resolved") {
    const chip = <Badge variant="success">{atsLabel(r.ats)}{r.job_count !== null ? `, ${r.job_count} postings` : ""}</Badge>;
    return r.board_url ? <a href={r.board_url} target="_blank" rel="noreferrer" title="Open the job board">{chip}</a> : chip;
  }
  if (r.status === "empty") {
    return <Badge variant="outline" title={r.note || "Its career site works but lists no openings. It is checked again within a week."}>No openings right now</Badge>;
  }
  if (r.status === "failed") return <Badge variant="warning" title={r.note}>Not found. Add its careers URL</Badge>;
  return <Badge variant="outline">Not checked yet</Badge>;
}

function UrlCell({ t }: { t: Target }) {
  const qc = useQueryClient();
  const [value, setValue] = useState(t.careers_url);
  const save = useMutation({
    mutationFn: () => api.patch(`/api/job-search/targets/${t.id}`, { careers_url: value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: jsKeys.all }),
    onError: (e) => toast.error((e as Error).message),
  });
  const found = t.route.careers_url && t.route.careers_url !== value ? t.route.careers_url : "";
  return (
    <div className="grid gap-1">
      <div className="flex items-center gap-1">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onBlur={() => value !== t.careers_url && save.mutate()}
          placeholder="https://careers.example.com"
          aria-label={`Careers page for ${t.name}`}
          className="h-8 text-xs"
        />
        {value && (
          <Button asChild size="icon-sm" variant="ghost" aria-label={`Open ${t.name}'s careers page`}>
            <a href={value} target="_blank" rel="noreferrer"><ExternalLink /></a>
          </Button>
        )}
      </div>
      {found && (
        <a href={found} target="_blank" rel="noreferrer" className="truncate text-xs text-muted-foreground underline-offset-2 hover:underline" title={found}>
          Found: {found.replace(/^https?:\/\//, "")}
        </a>
      )}
    </div>
  );
}

export default function CompaniesPage() {
  const qc = useQueryClient();
  const { track } = useJobs();
  const { data: readiness } = useReadiness();
  const { data } = useTargets();
  const { data: suggestions } = useSuggestions();
  const { data: system } = useSystem();
  const targets = data?.targets ?? [];
  const max = data?.max ?? 100;
  const room = max - targets.length;

  const [text, setText] = useState("");
  const [count, setCount] = useState("30");
  const [clusters, setClusters] = useState<string[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const running = jobId ?? system?.active_jobs.find((j) => j.kind.startsWith("job_search"))?.id ?? null;
  const stream = useJobState(running);
  const busy = !!running && !(stream?.done ?? false);
  const clusterOptions = readiness?.options.clusters ?? {};

  const refresh = () => qc.invalidateQueries({ queryKey: jsKeys.all });

  const importText = useMutation({
    mutationFn: () => api.post<AddResult>("/api/job-search/targets/import", { text }),
    onSuccess: (r) => {
      refresh();
      setText("");
      toast.success(`Added ${r.added.length}${r.skipped.length ? `, skipped ${r.skipped.length} duplicates` : ""}${r.over_limit.length ? `, ${r.over_limit.length} did not fit in ${max}` : ""}`);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const startJob = (path: string, body: object, title: string) =>
    api.post<JobSummary>(path, body).then((job) => {
      setJobId(job.id);
      track(job, { title, open: false, successMessage: `${title}: done` });
    });
  const suggest = useMutation({
    mutationFn: () => startJob("/api/job-search/targets/suggest", { count: Math.min(Number(count), room), clusters: clusters.length ? clusters : undefined }, "Finding companies for you"),
    onError: (e) => toast.error((e as Error).message),
  });
  const discover = useMutation({
    mutationFn: (force: boolean) => startJob("/api/job-search/targets/discover", { force }, "Finding career pages"),
    onError: (e) => toast.error((e as Error).message),
  });
  const accept = useMutation({
    mutationFn: () => api.post<AddResult>("/api/job-search/targets/suggestions/accept", { names: [...picked] }),
    onSuccess: (r) => {
      setPicked(new Set());
      refresh();
      toast.success(`Added ${r.added.length} companies. Click "Find career pages" to connect them.`);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/api/job-search/targets/${id}`),
    onSuccess: refresh,
  });

  const grouped = useMemo(() => {
    const g: Record<string, NonNullable<typeof suggestions>["companies"]> = {};
    for (const c of suggestions?.companies ?? []) (g[c.cluster] ??= []).push(c);
    return g;
  }, [suggestions]);

  const toggle = (name: string) =>
    setPicked((s) => {
      const n = new Set(s);
      if (n.has(name)) n.delete(name);
      else n.add(name);
      return n;
    });

  const unresolved = targets.filter((t) => t.route.status !== "resolved").length;

  return (
    <div className="grid gap-6">
      <Card className="grid gap-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">Suggest companies for me</h2>
            <p className="text-sm text-muted-foreground">
              {readiness?.tier === "quick"
                ? "Based on the titles, industries and companies you list on the Preferences tab."
                : "Based on your real employers, titles and skills, plus what you list on the Preferences tab."}
            </p>
          </div>
          <span className="text-sm tabular-nums text-muted-foreground">{targets.length} of {max} companies</span>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="grid w-32 gap-1.5 text-sm font-medium">
            How many
            <Select value={count} onValueChange={setCount} aria-label="How many companies" options={[10, 20, 30, 50, 100].filter((n) => n <= Math.max(room, 10)).map((n) => ({ value: String(n), label: String(n) }))} />
          </label>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Kinds of companies">
            {Object.entries(clusterOptions).map(([key, label]) => (
              <button key={key} type="button" aria-pressed={clusters.includes(key)} title={label}
                onClick={() => setClusters((c) => (c.includes(key) ? c.filter((x) => x !== key) : [...c, key]))}
                className={cn("rounded-full border px-3 py-1 text-xs font-medium", clusters.includes(key) ? "border-primary/40 bg-primary/10 text-primary" : "text-muted-foreground")}>
                {CLUSTER_SHORT[key] ?? key}
              </button>
            ))}
          </div>
          <Button variant="gradient" onClick={() => suggest.mutate()} loading={suggest.isPending} disabled={busy || room <= 0}>
            <Sparkles /> Suggest companies
          </Button>
        </div>
        {busy && <p className="text-sm text-muted-foreground" role="status">{stream?.lines.filter((l) => l.trim()).at(-1) ?? "Working..."}</p>}

        {suggestions && suggestions.companies.length > 0 && (
          <div className="grid gap-4 border-t pt-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Review the suggestions ({suggestions.companies.length})</h3>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setPicked(new Set(suggestions.companies.map((c) => c.name)))}>Select all</Button>
                <Button size="sm" variant="gradient" disabled={picked.size === 0} onClick={() => accept.mutate()} loading={accept.isPending}>Add {picked.size || ""} selected</Button>
              </div>
            </div>
            {Object.entries(grouped).map(([cluster, list]) => (
              <div key={cluster}>
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">{clusterOptions[cluster] ?? cluster}</div>
                <ul className="grid gap-1.5 sm:grid-cols-2">
                  {list.map((c) => (
                    <li key={c.name}>
                      <label className="flex cursor-pointer gap-2 rounded-lg border p-2.5 text-sm hover:bg-secondary/40">
                        <input type="checkbox" className="mt-1" checked={picked.has(c.name)} onChange={() => toggle(c.name)} />
                        <span><span className="font-medium">{c.name}</span><span className="block text-xs text-muted-foreground">{c.rationale}</span></span>
                      </label>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="grid gap-3 p-5">
        <h2 className="text-base font-semibold">Add your own list</h2>
        <p className="text-sm text-muted-foreground">One company per line, optionally followed by a comma and its careers page. You can also load a CSV file.</p>
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} placeholder={"Abbott\nGenentech, https://careers.gene.com\nIntuit"} aria-label="Companies to add" />
        <div className="flex gap-2">
          <Button onClick={() => importText.mutate()} disabled={!text.trim() || room <= 0} loading={importText.isPending}>Add companies</Button>
          <Button variant="outline" onClick={() => fileRef.current?.click()}><FileUp /> Load a CSV</Button>
          <input ref={fileRef} type="file" accept=".csv,.txt" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setText(await f.text()); e.target.value = ""; }} />
        </div>
      </Card>

      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Your target companies</h2>
          <Button variant="outline" onClick={() => discover.mutate(false)} loading={discover.isPending} disabled={busy || targets.length === 0}>
            <Globe /> Find career pages{unresolved ? ` (${unresolved} to connect)` : ""}
          </Button>
        </div>
        {targets.length === 0 ? (
          <p className="text-sm text-muted-foreground">No companies yet. Ask for suggestions above or paste a list.</p>
        ) : (
          <Table>
            <TableHeader><TableRow><TableHead>Company</TableHead><TableHead>Connection</TableHead><TableHead className="w-72">Careers page</TableHead><TableHead className="w-10"><span className="sr-only">Remove</span></TableHead></TableRow></TableHeader>
            <TableBody>
              {targets.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.name}{t.added_by === "suggested" && <span className="ml-2 text-xs font-normal text-muted-foreground">suggested</span>}</TableCell>
                  <TableCell><RouteChip t={t} /></TableCell>
                  <TableCell><UrlCell t={t} /></TableCell>
                  <TableCell><Button size="icon-sm" variant="ghost" aria-label={`Remove ${t.name}`} onClick={() => remove.mutate(t.id)}><Trash2 /></Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </div>
  );
}
