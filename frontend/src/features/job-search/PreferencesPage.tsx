import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { ListField, NumberField } from "./components/ListField";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import type { JobSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { jsKeys, usePreferences, useReadiness, useTargets } from "./api";
import { SOURCE_HINTS, SOURCE_LABELS } from "./format";
import type { AccountStatus, Depth, Preferences, Source } from "./types";

const DEPTHS: { value: Depth; label: string }[] = [
  { value: "quick", label: "Quick: your companies and a short board sweep (a few minutes)" },
  { value: "standard", label: "Standard: adds about 30 suggested companies (5 to 8 minutes)" },
  { value: "deep", label: "Deep: 75 suggested companies, runs 15 to 25 minutes" },
];

function sourceBlocked(s: Source, prefs: Preferences, targetCount: number, accounts: AccountStatus[] | undefined): string | null {
  if (s === "targets" && targetCount === 0) return "Add companies on the Companies tab";
  if (s === "linkedin" && !prefs.linkedin_direct) return "Turn on LinkedIn direct below (opt-in)";
  if (s.endsWith("_account")) {
    const a = accounts?.find((x) => x.site === s.replace("_account", ""));
    if (!a) return "Not available";
    if (a.cooldown_until) return `Paused for today (${a.cooldown_reason || "bot check"})`;
    if (!a.connected && !a.login_optional) return "Connect your account below";
  }
  return null;
}

const LEVELS = [
  { value: "ic", label: "Individual contributor" },
  { value: "manager", label: "Manager" },
  { value: "senior_manager", label: "Senior manager" },
  { value: "director", label: "Director" },
  { value: "senior_director", label: "Senior director" },
  { value: "vp", label: "VP" },
  { value: "executive", label: "Executive" },
];

function Row({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid gap-2 py-4 first:pt-0 last:pb-0 md:grid-cols-[16rem_1fr] md:gap-6">
      <div>
        <div className="text-sm font-medium">{title}</div>
        {description && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export default function PreferencesPage() {
  const qc = useQueryClient();
  const { data: saved } = usePreferences();
  const { data: readiness } = useReadiness();
  const { data: targetData } = useTargets();
  const { track } = useJobs();
  const [form, setForm] = useState<Preferences | null>(null);

  useEffect(() => {
    // an older server may not send newer fields; fill them so the form never reads undefined
    if (saved && !form) setForm({ ...saved, title_keywords: saved.title_keywords ?? [], min_level: saved.min_level ?? "" });
  }, [saved, form]);

  const dirty = !!form && !!saved && JSON.stringify(form) !== JSON.stringify(saved);
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const save = useMutation({
    mutationFn: () => api.put<Preferences>("/api/job-search/preferences", form),
    onSuccess: (p) => {
      qc.setQueryData(jsKeys.prefs, p);
      setForm({ ...p, title_keywords: p.title_keywords ?? [] });
      qc.invalidateQueries({ queryKey: jsKeys.readiness });
      toast.success("Preferences saved");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const suggest = useMutation({
    mutationFn: () => api.post<JobSummary>("/api/job-search/preferences/draft"),
    onSuccess: (job) =>
      track(job, {
        title: "Drafting your search settings",
        open: false,
        successMessage: "Drafted from your resume. Review the filled fields.",
        onSuccess: async () => {
          await qc.invalidateQueries({ queryKey: jsKeys.prefs });
          const fresh = qc.getQueryData<Preferences>(jsKeys.prefs);
          if (fresh) setForm(fresh);
        },
      }),
    onError: (e) => toast.error((e as Error).message),
  });
  const toggleSource = (s: Source) =>
    setForm((f) => f && { ...f, sources: f.sources.includes(s) ? f.sources.filter((x) => x !== s) : [...f.sources, s] });

  const connect = useMutation({
    mutationFn: (site: string) => api.post(`/api/job-search/accounts/${site}/connect`),
    onSuccess: () => {
      toast.message("A Chrome window is opening. Sign in there, then come back.");
      const timer = setInterval(() => qc.invalidateQueries({ queryKey: jsKeys.readiness }), 4000);
      setTimeout(() => clearInterval(timer), 720000);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const cancelLogin = useMutation({
    mutationFn: () => api.post("/api/job-search/accounts/cancel-login"),
    onSuccess: () => { qc.invalidateQueries({ queryKey: jsKeys.readiness }); toast.success("Sign-in cancelled"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const disconnect = useMutation({
    mutationFn: (site: string) => api.del(`/api/job-search/accounts/${site}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: jsKeys.readiness }); toast.success("Disconnected and the saved session was removed"); },
    onError: (e) => toast.error((e as Error).message),
  });

  if (!form) return <Skeleton className="h-96" />;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">These rules decide what a search keeps. Unknown details never reject a posting; only evidence does.</p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => suggest.mutate()} loading={suggest.isPending}><Wand2 /> Fill empty fields from my resume</Button>
          <Button variant="gradient" onClick={() => save.mutate()} disabled={!dirty} loading={save.isPending}>Save</Button>
        </div>
      </div>

      <Card className="divide-y p-6">
        <Row title="Titles to search" description="One per line. Director, Sr Director, Head of, and similar.">
          <ListField rows={4} value={form.titles} onChange={(v) => set("titles", v)} aria-label="Titles to search" placeholder={"Director, Data Science\nHead of Analytics"} />
        </Row>
        <Row title="Role keywords" description="The work itself, without level words, one per line (for example &quot;medical affairs&quot;). A posting is kept only if its title contains the words of one of these or of a title above. Everything else is skipped before it is read.">
          <ListField rows={3} value={form.title_keywords} onChange={(v) => set("title_keywords", v)} aria-label="Role keywords" placeholder="medical affairs" />
        </Row>
        <Row title="Minimum level" description="Postings below this level are dropped. By default this is one level below your most recent title, so step-up and lateral roles pass.">
          <div className="max-w-72"><Select value={form.min_level || "auto"} onValueChange={(v) => set("min_level", v === "auto" ? "" : v)} options={[{ value: "auto", label: "Match my resume" }, ...LEVELS]} aria-label="Minimum level" /></div>
        </Row>
        <Row title="Counts as director level" description="Titles like Principal or Lead that you treat as director-equivalent. One per line.">
          <ListField rows={2} value={form.equivalent_titles} onChange={(v) => set("equivalent_titles", v)} aria-label="Director-equivalent titles" placeholder="Principal" />
        </Row>
        <Row title="Skills and themes" description="Used to find and rank roles. One per line.">
          <ListField rows={4} value={form.skill_terms} onChange={(v) => set("skill_terms", v)} aria-label="Skills and themes" />
        </Row>
        <Row title="Industries" description="Helps suggest companies, especially before you have a resume.">
          <ListField rows={2} value={form.industries} onChange={(v) => set("industries", v)} aria-label="Industries" placeholder="Pharma commercial analytics" />
        </Row>
        <Row title="Companies you admire" description="Seeds the suggestions. One per line.">
          <ListField rows={2} value={form.admired_companies} onChange={(v) => set("admired_companies", v)} aria-label="Companies you admire" />
        </Row>
        <Row title="About you" description={readiness?.tier === "quick" ? "Optional. A few sentences on what you do and want next. Used only to steer the search, never to claim experience." : "Optional. Anything the search should know that is not on your resume."}>
          <Textarea rows={3} value={form.about_me} onChange={(e) => set("about_me", e.target.value)} aria-label="About you" />
        </Row>
      </Card>

      <Card className="divide-y p-6">
        <Row title="How to search" description="Used by the Refresh button on Discover. Deeper searches look at more companies and take longer.">
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-medium">
                Roles to keep
                <Select value={String(form.count)} onValueChange={(v) => set("count", Number(v))} aria-label="Roles to keep"
                  options={(readiness?.options.counts ?? [3, 5, 10, 20]).map((n) => ({ value: String(n), label: `Best ${n}` }))} />
              </label>
              <label className="grid gap-1.5 text-sm font-medium">
                Depth
                <Select value={form.depth} onValueChange={(v) => set("depth", v as Depth)} aria-label="Search depth" options={DEPTHS} />
              </label>
            </div>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Where to search">
              {(readiness?.options.sources ?? (Object.keys(SOURCE_LABELS) as Source[])).map((s) => {
                const why = sourceBlocked(s, form, targetData?.targets.length ?? 0, readiness?.accounts);
                const on = form.sources.includes(s) && !why;
                return (
                  <button key={s} type="button" disabled={!!why} title={why ?? SOURCE_HINTS[s]} aria-pressed={on} onClick={() => toggleSource(s)}
                    className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                      on ? "border-primary/40 bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
                    {SOURCE_LABELS[s]}
                  </button>
                );
              })}
            </div>
          </div>
        </Row>
        <Row title="Relocation" description="If you will not relocate, any on-site or hybrid role outside your area, or outside the country, is dropped right away. Remote roles open to your country still pass.">
          <div className="grid gap-3">
            <label className="flex items-center gap-3 text-sm">
              <Switch checked={form.relocation === "no"} onCheckedChange={(v) => set("relocation", v ? "no" : "yes")} aria-label="I will not relocate" />
              I will not relocate
            </label>
          </div>
        </Row>
        <Row title="Home location" description="City and state, for the distance rule.">
          <Input value={form.home_location} onChange={(e) => set("home_location", e.target.value)} placeholder="City, ST" aria-label="Home location" className="max-w-xs" />
        </Row>
        <Row title="Radius (miles)" description="Straight-line distance, not drive time. 0 turns the distance rule off.">
          <NumberField min={0} fallback={0} value={form.radius_miles} onChange={(v) => set("radius_miles", v)} aria-label="Radius in miles" className="max-w-32" />
        </Row>
        <Row title="Other places you could work" description="Extra anchor cities, such as a second office town. One per line.">
          <ListField rows={2} value={form.anchor_cities} onChange={(v) => set("anchor_cities", v)} aria-label="Other anchor cities" placeholder="Pleasant Prairie, WI" />
        </Row>
        <Row title="Always-allowed cities" description="On-site roles here pass even outside the radius.">
          <ListField rows={2} value={form.allowed_cities} onChange={(v) => set("allowed_cities", v)} aria-label="Allowed cities" placeholder="Chicago, IL" />
        </Row>
        <Row title="States you can work remotely from" description="Remote roles must allow one of these. Comma separated, like IL, WI.">
          <ListField single mode="commas" value={form.remote_states} onChange={(v) => set("remote_states", v)} clean={(x) => x.toUpperCase()} aria-label="Remote states" className="max-w-xs" placeholder="IL, WI" />
        </Row>
        <Row title="Base pay floor ($)" description="A posting whose stated top of range is below this is dropped. Postings that state no pay are kept and flagged. 0 turns it off.">
          <NumberField min={0} step={5000} fallback={0} value={form.base_floor} onChange={(v) => set("base_floor", v)} aria-label="Base pay floor" className="max-w-40" />
        </Row>
        <Row title="Exclusions" description="A posting that mentions any of these is dropped. One per line.">
          <ListField rows={3} value={form.exclusions} onChange={(v) => set("exclusions", v)} aria-label="Exclusions" placeholder={"MD required\nquota carrying"} />
        </Row>
        <Row title="Default recency (days)" description="Older postings may already be in panel interviews. If too few qualify, a run widens to 30 days once and badges the older roles.">
          <NumberField min={1} max={90} fallback={14} value={form.recency_days} onChange={(v) => set("recency_days", v)} aria-label="Default recency in days" className="max-w-32" />
        </Row>
      </Card>

      <Card className="divide-y p-6">
        <Row title="Connected accounts" description="Search LinkedIn, Indeed and ZipRecruiter in your own browser, for more relevant roles than the public pages show. Each search run uses up to 10 searches per site.">
          <div className="grid gap-3">
            {(readiness?.accounts ?? []).map((a) => (
              <div key={a.site} className="flex flex-wrap items-center gap-3 text-sm">
                <span className="w-28 font-medium">{a.label}</span>
                <span className="text-muted-foreground">{accountStatusText(a)}</span>
                <Button variant="outline" size="sm" onClick={() => connect.mutate(a.site)} loading={connect.isPending && connect.variables === a.site}>
                  {a.connected ? "Sign in again" : "Connect"}
                </Button>
                {!a.connected && <Button variant="ghost" size="sm" onClick={() => cancelLogin.mutate()} loading={cancelLogin.isPending}>Cancel sign-in</Button>}
                {a.connected && <Button variant="outline" size="sm" onClick={() => disconnect.mutate(a.site)}>Disconnect</Button>}
              </div>
            ))}
            <Callout tone="info">
              Connect opens a Chrome window. You sign in yourself, including any two-step check, and the app never sees or stores your password; it keeps only the browser session on this computer. Each search run does up to 10 searches per site at a person's pace, and a site stops for a day at the first bot check or sign-out. LinkedIn, Indeed and ZipRecruiter prohibit automated use in their terms, so a slow pace reduces the risk of a restriction but cannot remove it.
            </Callout>
          </div>
        </Row>
        <Row title="LinkedIn direct (opt-in)" description="Reads a few pages of LinkedIn's public job search, throttled and capped.">
          <div className="grid gap-3">
            <label className="flex items-center gap-3 text-sm">
              <Switch checked={form.linkedin_direct} onCheckedChange={(v) => set("linkedin_direct", v)} aria-label="Allow LinkedIn direct search" />
              Allow LinkedIn direct search
            </label>
            <Callout tone="warning">
              This is against LinkedIn's terms and it rate-limits silently, so it is off by default and stops at the first empty page. The job board sweep covers LinkedIn, Indeed and Glassdoor through web search instead, without fetching those pages.
            </Callout>
          </div>
        </Row>
      </Card>
    </div>
  );
}

function accountStatusText(a: AccountStatus): string {
  if (a.cooldown_until) return `Paused until ${new Date(a.cooldown_until).toLocaleString()} (${a.cooldown_reason})`;
  const last = a.last_run ? ` Last run used ${a.last_run.search} of ${a.budget.search}.` : "";
  if (a.connected) return `Connected. Up to ${a.budget.search} searches per run.${last}`;
  if (a.login_optional) return `Works without signing in; sign in for results tailored to you.${last}`;
  return "Not connected";
}
