/** Pure helpers for the Discover page: the one-line search summary, the filter chips and the run summary. */
import type { Posting, Preferences, RunReport } from "./types";

export interface Filters {
  isNew: boolean;
  fresh: boolean;
  strong: boolean;
  careersOnly: boolean;
}

const LEVEL_LABELS: Record<string, string> = {
  ic: "Any level", manager: "Manager and up", senior_manager: "Senior manager and up", director: "Director and up",
  senior_director: "Senior director and up", vp: "VP and up", executive: "Executive",
};

/** Short chips describing what a search looks for, from the saved preferences. */
export function searchSummary(p: Preferences): string[] {
  const out: string[] = [];
  if (p.titles.length) out.push(p.titles.slice(0, 2).join(" / ") + (p.titles.length > 2 ? ` +${p.titles.length - 2}` : ""));
  out.push(p.min_level ? LEVEL_LABELS[p.min_level] ?? p.min_level : "Level from your resume");
  const where: string[] = [];
  if (p.home_location && p.radius_miles) where.push(`${p.radius_miles} mi of ${p.home_location}`);
  else if (p.home_location) where.push(p.home_location);
  if (p.relocation === "no" || p.remote_states.length) where.push("remote");
  if (where.length) out.push(where.join(" + "));
  if (p.base_floor) out.push(`$${Math.round(p.base_floor / 1000)}k+ base`);
  out.push(`last ${p.recency_days} days`);
  return out;
}

export function isCareersOnly(p: Posting): boolean {
  return !p.aggregator_only && !p.agency && p.also_listed_on.length === 0;
}

export function filterPostings(list: Posting[], f: Filters): Posting[] {
  return list.filter(
    (p) =>
      (!f.isNew || p.is_new) &&
      (!f.fresh || p.freshness === "fresh") &&
      (!f.strong || (p.fit?.total ?? 0) >= 70) &&
      (!f.careersOnly || isCareersOnly(p)),
  );
}

const plural = (n: number, one: string, many: string) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

/** "Checked 42 companies' career sites. 1,180 listings were not your role. 64 roles failed your filters." */
export function runSummary(r: RunReport): { line: string; empty: boolean } {
  const unread = r.coverage.filter((c) => c.status === "failed").length;
  const idle = r.coverage.filter((c) => c.status === "empty").length;
  const parts = [`Checked ${plural(r.coverage.length, "company", "companies")}' career sites`];
  if (r.off_role) parts.push(`${plural(r.off_role, "listing was", "listings were")} not your role`);
  if (r.rejected.length) parts.push(`${plural(r.rejected.length, "role", "roles")} failed your filters`);
  if (idle) parts.push(`${plural(idle, "site has", "sites have")} no openings right now`);
  if (unread) parts.push(`${plural(unread, "site", "sites")} could not be read`);
  return { line: parts.join(". ") + ".", empty: r.coverage.length === 0 && r.results.length === 0 };
}
