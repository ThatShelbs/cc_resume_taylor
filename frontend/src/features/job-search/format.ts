import type { FreshnessBand, Posting } from "./types";

export function formatMoney(n: number): string {
  return n >= 1000 ? `$${Math.round(n / 1000)}k` : `$${n}`;
}

/** "$200k to $240k", "$225k", or null when the posting states no pay. */
export function formatPay(p: Pick<Posting, "pay_min" | "pay_max">): string | null {
  if (!p.pay_max) return null;
  if (!p.pay_min || p.pay_min === p.pay_max) return formatMoney(p.pay_max);
  return `${formatMoney(p.pay_min)} to ${formatMoney(p.pay_max)}`;
}

export const FRESHNESS: Record<FreshnessBand, { label: string; variant: "success" | "default" | "warning" | "destructive" | "outline" }> = {
  fresh: { label: "Fresh", variant: "success" },
  active: { label: "Active", variant: "default" },
  aging: { label: "Aging", variant: "warning" },
  late: { label: "Late", variant: "destructive" },
  unknown: { label: "Date unknown", variant: "outline" },
};

export function ageLabel(age: number | null, estimated = false): string {
  if (age === null) return "Posting date not stated";
  const when = age === 0 ? "Posted today" : age === 1 ? "Posted yesterday" : `Posted ${age} days ago`;
  return estimated ? `${when} (estimated)` : when;
}

export function scoreTone(total: number): string {
  if (total >= 80) return "text-success";
  if (total >= 60) return "text-primary";
  return "text-muted-foreground";
}

export function closesIn(closesAt: string | null, now: Date = new Date()): number | null {
  if (!closesAt) return null;
  const t = Date.parse(closesAt);
  if (Number.isNaN(t)) return null;
  return Math.ceil((t - now.getTime()) / 86_400_000);
}

export function verifiedLabel(p: Pick<Posting, "verified" | "last_verified_at">, now: Date = new Date()): string | null {
  if (!p.last_verified_at) return null;
  const mins = Math.max(0, Math.round((now.getTime() - Date.parse(p.last_verified_at)) / 60_000));
  const when = mins < 2 ? "just now" : mins < 90 ? `${mins} min ago` : mins < 36 * 60 ? `${Math.round(mins / 60)} h ago` : `${Math.round(mins / 1440)} days ago`;
  return p.verified === "live" ? `Verified live ${when}` : `Checked ${when}, could not confirm`;
}

export const SOURCE_LABELS: Record<string, string> = {
  targets: "My target companies",
  ideated: "Ideated companies",
  boards: "Job board sweep",
  linkedin: "LinkedIn direct",
  google: "Google Jobs",
  linkedin_account: "LinkedIn (my account)",
  indeed_account: "Indeed (my account)",
  google_account: "Google Jobs (my account)",
};

export const REJECTION_LABELS: Record<string, string> = {
  level: "Below your minimum level",
  stale: "Posted too long ago",
  excluded: "Matches an exclusion",
  pay_below_floor: "Pay below your floor",
  location: "Outside your location rules",
  closed: "No longer live",
};

export const DISMISS_REASONS: { value: string; label: string }[] = [
  { value: "not_interested", label: "Not interested" },
  { value: "wrong_level", label: "Wrong level" },
  { value: "wrong_location", label: "Wrong location" },
  { value: "pay", label: "Pay" },
  { value: "company", label: "Company" },
  { value: "stale", label: "Open too long" },
  { value: "applied_elsewhere", label: "Applied elsewhere" },
  { value: "other", label: "Other" },
];

export function atsLabel(ats: string): string {
  const names: Record<string, string> = {
    greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", workday: "Workday", smartrecruiters: "SmartRecruiters",
    workable: "Workable", eightfold: "Eightfold", careers_page: "Careers page",
  };
  return names[ats] ?? ats;
}
