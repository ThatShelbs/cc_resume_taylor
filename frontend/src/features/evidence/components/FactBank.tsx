import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookCheck, Plus, Save, Search, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { EmptyState } from "@/components/shared/EmptyState";
import { AlertDialog, AlertDialogContent } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AutoTextarea, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys, useFacts, useSystem } from "@/lib/api/queries";
import type { Fact, FactsPayload, JobSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function FactBank() {
  const { data, isLoading } = useFacts();
  const { data: system } = useSystem();
  const { track } = useJobs();
  const qc = useQueryClient();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [baseline, setBaseline] = useState("");
  const [query, setQuery] = useState("");
  const [employer, setEmployer] = useState("all");
  const [confirmDraft, setConfirmDraft] = useState(false);

  useEffect(() => {
    if (!data) return;
    setFacts(data.facts);
    setBaseline(JSON.stringify(data.facts));
  }, [data]);

  const dirty = JSON.stringify(facts) !== baseline;
  const employers = useMemo(() => ["general", ...(data?.companies ?? []), "unassigned"], [data]);
  const issues = new Set(data?.employer_issues.map((i) => i.id));

  const save = useMutation({
    mutationFn: () => api.put<FactsPayload>("/api/facts", { facts: facts.filter((f) => f.text.trim()) }),
    onSuccess: (r) => {
      qc.setQueryData(keys.facts, r);
      qc.invalidateQueries({ queryKey: keys.system });
      toast.success("Fact bank saved", { description: "The previous version was backed up." });
    },
    onError: (e) => toast.error("Couldn't save", { description: (e as Error).message }),
  });

  const draft = useMutation({
    mutationFn: () => api.post<JobSummary>("/api/facts/draft", { force: !!data?.exists }),
    onSuccess: (job) => track(job, { title: "Drafting your fact bank", successMessage: "Fact bank drafted. Review the unassigned facts." }),
    onError: (e) => toast.error((e as Error).message),
  });

  const visible = facts
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => (employer === "all" || f.employer === employer) && (!query || `${f.id} ${f.text} ${f.tags.join(" ")}`.toLowerCase().includes(query.toLowerCase())));

  const set = (i: number, patch: Partial<Fact>) => setFacts((list) => list.map((f, k) => (k === i ? { ...f, ...patch } : f)));
  const unassigned = facts.filter((f) => f.employer === "unassigned").length;

  if (isLoading) return <Skeleton className="h-80" />;

  if (!data?.exists && !facts.length)
    return (
      <>
        <EmptyState
          icon={BookCheck}
          title="No fact bank yet"
          description="A fact bank is a list of atomic, true facts from your profile and resume, each tagged with its employer. When you have one, every generated bullet must cite the facts it's built from, and any bullet citing another employer's fact is dropped."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="gradient" disabled={system?.onboarding_needed} loading={draft.isPending} onClick={() => draft.mutate()}>
                <Sparkles /> Draft it from my profile and resume
              </Button>
              <Button variant="outline" onClick={() => setFacts([{ id: "", employer: "general", kind: "accomplishment", text: " ", metrics: [], tags: [] }])}>
                <Plus /> Start by hand
              </Button>
            </div>
          }
        />
      </>
    );

  return (
    <div className="grid gap-4">
      {unassigned > 0 && (
        <Callout tone="warning" title={`${unassigned} fact${unassigned > 1 ? "s are" : " is"} unassigned`}>
          Unassigned facts can inform the summary but can never back a bullet. Set the employer they belong to, or "general".
        </Callout>
      )}
      {data?.employer_issues.length ? (
        <Callout tone="warning" title="Some employers don't match your base resume">
          {data.employer_issues.map((i) => `${i.id} (${i.employer})`).join(", ")}. The pipeline treats these as unassigned until fixed.
        </Callout>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search facts, ids, tags" className="pl-8" />
        </div>
        <Select
          aria-label="Filter by employer"
          value={employer}
          onValueChange={setEmployer}
          className="sm:w-56"
          options={[{ value: "all", label: "All employers" }, ...employers.map((e) => ({ value: e, label: e }))]}
        />
        <Button variant="outline" onClick={() => setConfirmDraft(true)} disabled={system?.onboarding_needed}>
          <Sparkles /> Redraft
        </Button>
        <Button
          variant="outline"
          onClick={() => setFacts((list) => [...list, { id: "", employer: employer === "all" ? "general" : employer, kind: "accomplishment", text: " ", metrics: [], tags: [] }])}
        >
          <Plus /> Add fact
        </Button>
        <Button disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          <Save /> Save
        </Button>
      </div>

      <Card className="overflow-hidden">
        <div className="hidden grid-cols-[72px_190px_130px_1fr_36px] gap-3 border-b bg-muted/40 px-4 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground md:grid">
          <span>Id</span>
          <span>Employer</span>
          <span>Kind</span>
          <span>Fact, metrics, tags</span>
          <span />
        </div>
        <ul className="divide-y">
          {visible.map(({ f, i }) => (
            <li
              key={`${f.id}-${i}`}
              className={cn(
                "grid gap-2 px-4 py-3 md:grid-cols-[72px_190px_130px_1fr_36px] md:gap-3",
                (f.employer === "unassigned" || issues.has(f.id)) && "bg-warning/[0.04]",
              )}
            >
              <span className="pt-2 font-mono text-xs font-medium text-primary">{f.id || "new"}</span>
              <Select
                aria-label="Employer"
                value={employers.includes(f.employer) ? f.employer : "unassigned"}
                onValueChange={(v) => set(i, { employer: v })}
                className="h-8 text-[13px]"
                options={employers.map((e) => ({ value: e, label: e }))}
              />
              <Select
                aria-label="Kind"
                value={f.kind}
                onValueChange={(v) => set(i, { kind: v })}
                className="h-8 text-[13px] capitalize"
                options={(data?.kinds ?? []).map((k) => ({ value: k, label: <span className="capitalize">{k}</span> }))}
              />
              <div className="grid gap-1.5">
                <AutoTextarea value={f.text} onChange={(e) => set(i, { text: e.target.value })} className="min-h-[34px] py-1.5 text-[13px]" aria-label="Fact text" />
                <div className="grid gap-1.5 sm:grid-cols-2">
                  <Input
                    value={f.metrics.join(", ")}
                    onChange={(e) => set(i, { metrics: e.target.value.split(",").map((m) => m.trim()).filter(Boolean) })}
                    placeholder="Metrics, e.g. $300k, 200+ hours"
                    className="h-7 text-xs"
                    aria-label="Metrics"
                  />
                  <Input
                    value={f.tags.join(", ")}
                    onChange={(e) => set(i, { tags: e.target.value.split(",").map((m) => m.trim()).filter(Boolean) })}
                    placeholder="Tags, e.g. causal inference"
                    className="h-7 text-xs"
                    aria-label="Tags"
                  />
                </div>
              </div>
              <Tooltip content="Delete fact">
                <Button variant="ghost" size="icon-sm" className="text-muted-foreground hover:text-destructive" onClick={() => setFacts((l) => l.filter((_, k) => k !== i))} aria-label="Delete fact">
                  <Trash2 className="size-4" />
                </Button>
              </Tooltip>
            </li>
          ))}
          {!visible.length && <li className="px-4 py-8 text-center text-sm text-muted-foreground">No facts match.</li>}
        </ul>
      </Card>
      <p className="text-xs text-muted-foreground">
        {facts.length} facts. Keep ids stable once you've generated resumes, since each bullet's citations point to them.
      </p>

      <AlertDialog open={confirmDraft} onOpenChange={setConfirmDraft}>
        <AlertDialogContent
          title="Redraft the whole fact bank?"
          description="Claude re-extracts every fact from your profile and base resume. Your current bank, including hand edits, is backed up first."
          confirmLabel="Redraft"
          onConfirm={() => draft.mutate()}
        />
      </AlertDialog>
    </div>
  );
}
