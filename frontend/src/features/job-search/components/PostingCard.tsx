import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Building2, ExternalLink, MapPin, RefreshCw, ThumbsDown, ThumbsUp, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { jsKeys } from "../api";
import { ageLabel, atsLabel, closesIn, DISMISS_REASONS, formatPay, FRESHNESS, scoreTone, verifiedLabel } from "../format";
import type { Posting } from "../types";

const SUB_LABELS: Record<string, string> = {
  skills: "Skills", leadership: "Leadership", domain: "Domain", seniority_realism: "Seniority",
  freshness: "Freshness", comp: "Pay", location: "Location", source: "Direct source",
};

export function PostingCard({
  posting,
  onTailor,
  onAddCompany,
  companyIsTarget,
}: {
  posting: Posting;
  onTailor: (p: Posting) => void;
  onAddCompany?: (name: string) => void;
  companyIsTarget: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const fit = posting.fit;
  const fresh = FRESHNESS[posting.freshness] ?? FRESHNESS.unknown;
  const pay = formatPay(posting);
  const closes = closesIn(posting.closes_at);
  const verified = verifiedLabel(posting);
  const dismissed = posting.stage === "dismissed";

  const refresh = () => qc.invalidateQueries({ queryKey: jsKeys.all });
  const patch = useMutation({
    mutationFn: (body: { stage: string; dismiss_reason?: string }) => api.patch(`/api/job-search/postings/${posting.id}`, body),
    onSuccess: refresh,
    onError: (e) => toast.error((e as Error).message),
  });
  const verify = useMutation({
    mutationFn: () => api.post<Posting>(`/api/job-search/postings/${posting.id}/verify`),
    onSuccess: (p) => {
      refresh();
      toast[p.verified === "live" ? "success" : "message"](p.verified === "live" ? "Still live" : p.verified === "closed" ? "This posting is closed" : "Could not confirm it is live");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <Card className={cn("grid gap-3 p-4", dismissed && "opacity-60")}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {posting.is_new && <Badge variant="success">New</Badge>}
            <Badge variant={fresh.variant} title={posting.freshness_note}>{fresh.label}</Badge>
            {posting.agency ? (
              <Badge variant="outline" title={`${posting.agency}'s own posting. The hiring company is usually not named; you apply through ${posting.agency}.`}>
                Staffing agency{posting.employment_type ? `: ${posting.employment_type}` : ""}
              </Badge>
            ) : posting.aggregator_only ? (
              <Badge variant="outline" title="Found on a job board only; the company's own posting was not located.">Board lead</Badge>
            ) : posting.also_listed_on.length ? (
              <Badge variant="secondary">Also on {posting.also_listed_on.join(", ")}</Badge>
            ) : (
              <Badge variant="success" title="Listed on the company's careers page only, which usually means a smaller applicant pool.">Careers page only</Badge>
            )}
            {posting.stage === "interested" && <Badge>Interested</Badge>}
            {posting.project_id && (
              <Badge variant="outline">
                <Link to={ROUTES.project(posting.project_id)}>Resume project</Link>
              </Badge>
            )}
          </div>
          <h3 className="mt-1.5 text-base font-semibold leading-snug">{posting.title}</h3>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1"><Building2 className="size-3.5" />{posting.company}</span>
            {posting.locations.length > 0 && (
              <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" />{posting.locations.slice(0, 2).join("; ")}{posting.work_mode !== "unknown" ? ` (${posting.work_mode})` : ""}</span>
            )}
            {pay && <span>{pay}</span>}
          </div>
        </div>
        {fit && (
          <div className="shrink-0 text-right" title={fit.kind === "preference_match" ? "How well this matches what you said you want" : "Fit score out of 100"}>
            <div className={cn("text-3xl font-semibold tabular-nums leading-none", scoreTone(fit.total))}>{fit.total}</div>
            <div className="mt-1 text-[11px] text-muted-foreground">{fit.kind === "preference_match" ? "Preference match" : "Fit"}</div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>{ageLabel(posting.age_days, posting.date_estimated)}</span>
        {closes !== null && closes <= 14 && <span className="text-warning">Closes in {Math.max(closes, 0)} days</span>}
        {verified && (
          <span className="inline-flex items-center gap-1"><BadgeCheck className="size-3.5" />{verified}</span>
        )}
        {posting.flags?.map((f) => <span key={f}>{f}</span>)}
      </div>

      {fit?.verdict && <p className="text-sm leading-relaxed">{fit.verdict}</p>}

      {fit && (
        <div>
          <button type="button" className="text-xs font-medium text-primary hover:underline" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {open ? "Hide the evidence" : "Show the evidence"}
          </button>
          {open && (
            <div className="mt-2 grid gap-3 text-sm">
              <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
                {Object.entries(fit.subscores).map(([k, s]) => (
                  <div key={k} className="flex items-baseline justify-between gap-2 text-xs">
                    <span className="text-muted-foreground">{SUB_LABELS[k] ?? k}</span>
                    <span className="tabular-nums">{s.score}/{s.max}</span>
                  </div>
                ))}
              </div>
              {Object.entries(fit.subscores).flatMap(([k, s]) => (s.quotes ?? []).map((q) => ({ k, q }))).slice(0, 4).map(({ k, q }) => (
                <blockquote key={k + q} className="border-l-2 pl-3 text-xs italic text-muted-foreground">
                  &ldquo;{q}&rdquo; <span className="not-italic">({SUB_LABELS[k] ?? k})</span>
                </blockquote>
              ))}
              {fit.gaps.length > 0 && (
                <div>
                  <div className="text-xs font-medium">Gaps to be honest about</div>
                  <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">{fit.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
                </div>
              )}
              {fit.angle && <p className="text-xs"><span className="font-medium">Angle: </span>{fit.angle}</p>}
              {posting.freshness_note && <p className="text-xs text-muted-foreground">{posting.freshness_note}</p>}
              {posting.ats && <p className="text-xs text-muted-foreground">Source: {atsLabel(posting.ats)}{posting.read_by_claude ? " (read by Claude from the page)" : ""}</p>}
            </div>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {!posting.project_id && (
          <Button size="sm" variant="gradient" onClick={() => onTailor(posting)}>
            <Wand2 /> Tailor resume
          </Button>
        )}
        {posting.stage === "prospect" && !posting.project_id && (
          <Button size="sm" variant="outline" onClick={() => patch.mutate({ stage: "interested" })}>
            <ThumbsUp /> Interested
          </Button>
        )}
        {!dismissed && !posting.project_id && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="sm" variant="ghost"><ThumbsDown /> Not interested</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuLabel>Why not?</DropdownMenuLabel>
              {DISMISS_REASONS.map((r) => (
                <DropdownMenuItem key={r.value} onSelect={() => patch.mutate({ stage: "dismissed", dismiss_reason: r.value })}>{r.label}</DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        {dismissed && <Button size="sm" variant="ghost" onClick={() => patch.mutate({ stage: "prospect" })}>Restore</Button>}
        <Button asChild size="sm" variant="ghost">
          <a href={posting.apply_url || posting.url} target="_blank" rel="noreferrer"><ExternalLink /> Open posting</a>
        </Button>
        <CareersLink posting={posting} />
        <Button size="sm" variant="ghost" onClick={() => verify.mutate()} loading={verify.isPending}>
          <RefreshCw /> Re-verify
        </Button>
        {onAddCompany && !companyIsTarget && posting.origin !== "target" && (
          <Button size="sm" variant="ghost" onClick={() => onAddCompany(posting.company)}>Add {posting.company} to targets</Button>
        )}
      </div>
    </Card>
  );
}

/** The company's own careers page: for a board lead, where to look for (and apply to) the same role directly. */
export function CareersLink({ posting }: { posting: Posting }) {
  if (posting.agency) return null;
  const lead = posting.aggregator_only;
  const href = (lead && posting.company_search_url) || posting.company_careers_url;
  if (!href) return null;
  return (
    <Button asChild size="sm" variant="ghost">
      <a href={href} target="_blank" rel="noreferrer" title={lead ? "Apply on the company's own site when the role is listed there" : undefined}>
        <Building2 /> {lead ? `Look for it on ${posting.company}'s site` : "Company careers page"}
      </a>
    </Button>
  );
}
