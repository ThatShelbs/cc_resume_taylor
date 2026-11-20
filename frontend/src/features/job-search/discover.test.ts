import { describe, expect, it } from "vitest";
import { filterPostings, runSummary, searchSummary } from "./discover";
import type { Posting, Preferences, RunReport } from "./types";

const prefs = (patch: Partial<Preferences> = {}): Preferences => ({
  titles: ["Director, Medical Affairs"], equivalent_titles: [], title_keywords: [], min_level: "", skill_terms: [], industries: [],
  admired_companies: [], about_me: "", home_location: "Crystal Lake, IL", radius_miles: 50, anchor_cities: [], allowed_cities: [],
  remote_states: ["IL"], relocation: "no", remote_country: "US", base_floor: 200000, exclusions: [], recency_days: 14, count: 5,
  depth: "standard", sources: ["targets"], linkedin_direct: false, ...patch,
});

const posting = (patch: Partial<Posting>): Posting => ({
  id: "p", title: "Director", company: "Acme", locations: [], work_mode: "unknown", url: "", apply_url: "", ats: "greenhouse",
  source: "greenhouse", also_listed_on: [], aggregator_only: false, pay_min: null, pay_max: null, pay_text: "", posted_at: null,
  age_days: 1, freshness: "fresh", freshness_note: "", date_estimated: false, closes_at: null, stage: "prospect", dismiss_reason: "",
  is_new: false, project_id: "", ...patch,
});

describe("searchSummary", () => {
  it("describes the search in a few chips", () => {
    expect(searchSummary(prefs())).toEqual([
      "Director, Medical Affairs", "Level from your resume", "50 mi of Crystal Lake, IL + remote", "$200k+ base", "last 14 days",
    ]);
  });
});

describe("filterPostings", () => {
  const list = [
    posting({ id: "a", is_new: true }),
    posting({ id: "b", freshness: "aging", aggregator_only: true }),
    posting({ id: "c", also_listed_on: ["LinkedIn"] }),
  ];
  it("filters by chip", () => {
    const off = { isNew: false, fresh: false, strong: false, careersOnly: false };
    expect(filterPostings(list, off)).toHaveLength(3);
    expect(filterPostings(list, { ...off, isNew: true }).map((p) => p.id)).toEqual(["a"]);
    expect(filterPostings(list, { ...off, careersOnly: true }).map((p) => p.id)).toEqual(["a"]);
    expect(filterPostings(list, { ...off, fresh: true }).map((p) => p.id)).toEqual(["a", "c"]);
  });
});

describe("runSummary", () => {
  it("says how much was skipped as not the role instead of listing it", () => {
    const report = {
      coverage: [
        { company: "A", origin: "target", ats: "greenhouse", count: 3, status: "ok", note: "" },
        { company: "B", origin: "target", ats: "workday", count: 0, status: "empty", note: "" },
        { company: "C", origin: "target", ats: "", count: 0, status: "failed", note: "" },
      ],
      off_role: 1180,
      rejected: Array.from({ length: 64 }, (_, i) => ({ id: String(i) })),
      results: [],
    } as unknown as RunReport;
    expect(runSummary(report).line).toBe(
      "Checked 3 companies' career sites. 1,180 listings were not your role. 64 roles failed your filters. 1 site has no openings right now. 1 site could not be read.",
    );
  });
});
