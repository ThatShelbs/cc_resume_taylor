import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Wand2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api/client";
import { jsKeys, usePreferences, useReadiness } from "./api";
import type { Preferences } from "./types";

const LEVELS = [
  { value: "manager", label: "Manager" },
  { value: "senior_manager", label: "Senior manager" },
  { value: "director", label: "Director" },
  { value: "senior_director", label: "Senior director" },
  { value: "vp", label: "VP" },
  { value: "executive", label: "Executive" },
];

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const text = (a: string[]) => a.join("\n");

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
  const [form, setForm] = useState<Preferences | null>(null);
  const [serpKey, setSerpKey] = useState("");

  useEffect(() => {
    if (saved && !form) setForm(saved);
  }, [saved, form]);

  const dirty = !!form && !!saved && JSON.stringify(form) !== JSON.stringify(saved);
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const save = useMutation({
    mutationFn: () => api.put<Preferences>("/api/job-search/preferences", form),
    onSuccess: (p) => {
      qc.setQueryData(jsKeys.prefs, p);
      setForm(p);
      qc.invalidateQueries({ queryKey: jsKeys.readiness });
      toast.success("Preferences saved");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const suggest = useMutation({
    mutationFn: () => api.post<{ titles: string[]; skill_terms: string[]; home_location: string }>("/api/job-search/preferences/suggest"),
    onSuccess: (s) => {
      setForm((f) => f && {
        ...f,
        titles: f.titles.length ? f.titles : s.titles,
        skill_terms: f.skill_terms.length ? f.skill_terms : s.skill_terms,
        home_location: f.home_location || s.home_location,
      });
      toast.success("Filled the empty fields from your profile. Review them, then save.");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const saveKey = useMutation({
    mutationFn: () => api.put("/api/settings/serpapi-key", { key: serpKey }),
    onSuccess: () => { setSerpKey(""); qc.invalidateQueries({ queryKey: jsKeys.readiness }); toast.success("SerpAPI key saved"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const clearKey = useMutation({
    mutationFn: () => api.del("/api/settings/serpapi-key"),
    onSuccess: () => qc.invalidateQueries({ queryKey: jsKeys.readiness }),
  });

  const connect = useMutation({
    mutationFn: (site: string) => api.post(`/api/job-search/accounts/${site}/connect`),
    onSuccess: () => {
      toast.message("A Chrome window is opening. Sign in there, then come back.");
      const timer = setInterval(() => qc.invalidateQueries({ queryKey: jsKeys.readiness }), 4000);
      setTimeout(() => clearInterval(timer), 120000);
    },
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
          <Button variant="outline" onClick={() => suggest.mutate()} loading={suggest.isPending}><Wand2 /> Suggest from my profile</Button>
          <Button variant="gradient" onClick={() => save.mutate()} disabled={!dirty} loading={save.isPending}>Save</Button>
        </div>
      </div>

      <Card className="divide-y p-6">
        <Row title="Titles to search" description="One per line. Director, Sr Director, Head of, and similar.">
          <Textarea rows={4} value={text(form.titles)} onChange={(e) => set("titles", lines(e.target.value))} aria-label="Titles to search" placeholder={"Director, Data Science\nHead of Analytics"} />
        </Row>
        <Row title="Minimum level" description="Postings below this level are dropped.">
          <div className="max-w-56"><Select value={form.min_level} onValueChange={(v) => set("min_level", v)} options={LEVELS} aria-label="Minimum level" /></div>
        </Row>
        <Row title="Counts as director level" description="Titles like Principal or Lead that you treat as director-equivalent. One per line.">
          <Textarea rows={2} value={text(form.equivalent_titles)} onChange={(e) => set("equivalent_titles", lines(e.target.value))} aria-label="Director-equivalent titles" placeholder="Principal" />
        </Row>
        <Row title="Skills and themes" description="Used to find and rank roles. One per line.">
          <Textarea rows={4} value={text(form.skill_terms)} onChange={(e) => set("skill_terms", lines(e.target.value))} aria-label="Skills and themes" />
        </Row>
        <Row title="Industries" description="Helps suggest companies, especially before you have a resume.">
          <Textarea rows={2} value={text(form.industries)} onChange={(e) => set("industries", lines(e.target.value))} aria-label="Industries" placeholder="Pharma commercial analytics" />
        </Row>
        <Row title="Companies you admire" description="Seeds the suggestions. One per line.">
          <Textarea rows={2} value={text(form.admired_companies)} onChange={(e) => set("admired_companies", lines(e.target.value))} aria-label="Companies you admire" />
        </Row>
        <Row title="About you" description={readiness?.tier === "quick" ? "Optional. A few sentences on what you do and want next. Used only to steer the search, never to claim experience." : "Optional. Anything the search should know that is not on your resume."}>
          <Textarea rows={3} value={form.about_me} onChange={(e) => set("about_me", e.target.value)} aria-label="About you" />
        </Row>
      </Card>

      <Card className="divide-y p-6">
        <Row title="Relocation" description="If you will not relocate, any on-site or hybrid role outside your area, or outside the country, is dropped right away. Remote roles open to your country still pass.">
          <div className="grid gap-3">
            <label className="flex items-center gap-3 text-sm">
              <Switch checked={form.relocation === "no"} onCheckedChange={(v) => set("relocation", v ? "no" : "yes")} aria-label="I will not relocate" />
              I will not relocate
            </label>
            {form.relocation === "no" && (
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="outline"
                  onClick={() => setForm((f) => f && { ...f, anchor_cities: ["Milwaukee, WI", "Chicago, IL"], radius_miles: 60 })}
                >
                  Use Chicagoland and southeast Wisconsin
                </Button>
                <span className="text-xs text-muted-foreground">Sets Milwaukee and Chicago as anchors with a 60 mile radius. Add your home city below.</span>
              </div>
            )}
          </div>
        </Row>
        <Row title="Home location" description="City and state, for the distance rule.">
          <Input value={form.home_location} onChange={(e) => set("home_location", e.target.value)} placeholder="Crystal Lake, IL" aria-label="Home location" className="max-w-xs" />
        </Row>
        <Row title="Radius (miles)" description="Straight-line distance, not drive time. 0 turns the distance rule off.">
          <Input type="number" min={0} value={form.radius_miles} onChange={(e) => set("radius_miles", Number(e.target.value) || 0)} aria-label="Radius in miles" className="max-w-32" />
        </Row>
        <Row title="Other places you could work" description="Extra anchor cities, such as a second office town. One per line.">
          <Textarea rows={2} value={text(form.anchor_cities)} onChange={(e) => set("anchor_cities", lines(e.target.value))} aria-label="Other anchor cities" placeholder="Pleasant Prairie, WI" />
        </Row>
        <Row title="Always-allowed cities" description="On-site roles here pass even outside the radius.">
          <Textarea rows={2} value={text(form.allowed_cities)} onChange={(e) => set("allowed_cities", lines(e.target.value))} aria-label="Allowed cities" placeholder="Chicago, IL" />
        </Row>
        <Row title="States you can work remotely from" description="Remote roles must allow one of these. Comma separated, like IL, WI.">
          <Input value={form.remote_states.join(", ")} onChange={(e) => set("remote_states", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} aria-label="Remote states" className="max-w-xs" placeholder="IL" />
        </Row>
        <Row title="Base pay floor ($)" description="A posting whose stated top of range is below this is dropped. Postings that state no pay are kept and flagged. 0 turns it off.">
          <Input type="number" min={0} step={5000} value={form.base_floor} onChange={(e) => set("base_floor", Number(e.target.value) || 0)} aria-label="Base pay floor" className="max-w-40" />
        </Row>
        <Row title="Exclusions" description="A posting that mentions any of these is dropped. One per line.">
          <Textarea rows={3} value={text(form.exclusions)} onChange={(e) => set("exclusions", lines(e.target.value))} aria-label="Exclusions" placeholder={"MD required\nquota carrying"} />
        </Row>
        <Row title="Default recency (days)" description="Older postings may already be in panel interviews. If too few qualify, a run widens to 30 days once and badges the older roles.">
          <Input type="number" min={1} max={90} value={form.recency_days} onChange={(e) => set("recency_days", Number(e.target.value) || 14)} aria-label="Default recency in days" className="max-w-32" />
        </Row>
      </Card>

      <Card className="divide-y p-6">
        <Row title="Connected accounts" description="Search LinkedIn, Indeed and Google Jobs as you, for more relevant roles than the public pages show.">
          <div className="grid gap-3">
            {(readiness?.accounts ?? []).map((a) => (
              <div key={a.site} className="flex flex-wrap items-center gap-3 text-sm">
                <span className="w-28 font-medium">{a.label}</span>
                <span className="text-muted-foreground">
                  {a.cooldown_until ? `Paused until ${new Date(a.cooldown_until).toLocaleString()} (${a.cooldown_reason})`
                    : a.connected ? `Connected. Today: ${a.used_today.search} of ${a.caps.search} searches` : "Not connected"}
                </span>
                <Button variant="outline" size="sm" onClick={() => connect.mutate(a.site)} loading={connect.isPending && connect.variables === a.site}>
                  {a.connected ? "Sign in again" : "Connect"}
                </Button>
                {a.connected && <Button variant="outline" size="sm" onClick={() => disconnect.mutate(a.site)}>Disconnect</Button>}
              </div>
            ))}
            <Callout tone="info">
              Connect opens a Chrome window. You sign in yourself, including any two-step check, and the app never sees or stores your password; it keeps only the browser session on this computer. Searches run slowly with small daily limits, and stop for the day at the first bot check or sign-out. LinkedIn and Indeed prohibit automated use in their terms, so low volume reduces the risk of a restriction but cannot remove it.
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
        <Row title="Google Jobs (optional)" description="Adds Google Jobs results through a SerpAPI key. Never shown again after saving.">
          <div className="flex flex-wrap items-center gap-2">
            {readiness?.serpapi.set ? (
              <>
                <span className="text-sm">Key saved, ending {readiness.serpapi.last4}</span>
                <Button variant="outline" size="sm" onClick={() => clearKey.mutate()}>Remove</Button>
              </>
            ) : (
              <>
                <Input type="password" value={serpKey} onChange={(e) => setSerpKey(e.target.value)} placeholder="SerpAPI key" aria-label="SerpAPI key" className="max-w-xs" autoComplete="off" />
                <Button variant="outline" size="sm" onClick={() => saveKey.mutate()} disabled={!serpKey.trim()} loading={saveKey.isPending}>Save key</Button>
              </>
            )}
          </div>
        </Row>
      </Card>
    </div>
  );
}
