import { describe, expect, it } from "vitest";
import { ageLabel, closesIn, formatPay, verifiedLabel } from "./format";
import { dropAction, groupByColumn, isStale } from "./pipeline";
import type { BoardCard } from "./types";

const card = (patch: Partial<BoardCard>): BoardCard => ({
  kind: "posting", id: "x", column: "prospect", title: "Director", company: "Acme", url: "", fit: null,
  freshness: null, age_days: null, updated_at: "2026-11-01", ...patch,
});

describe("formatting", () => {
  it("formats pay ranges without dashes and handles unstated pay", () => {
    expect(formatPay({ pay_min: 200000, pay_max: 240000 })).toBe("$200k to $240k");
    expect(formatPay({ pay_min: 225000, pay_max: 225000 })).toBe("$225k");
    expect(formatPay({ pay_min: null, pay_max: null })).toBeNull();
  });

  it("labels posting age and marks estimates", () => {
    expect(ageLabel(0)).toBe("Posted today");
    expect(ageLabel(14, true)).toBe("Posted 14 days ago (estimated)");
    expect(ageLabel(null)).toBe("Posting date not stated");
  });

  it("counts days until a posting closes", () => {
    const now = new Date("2026-11-16T00:00:00Z");
    expect(closesIn("2026-11-20T00:00:00Z", now)).toBe(4);
    expect(closesIn(null, now)).toBeNull();
  });

  it("says when a posting was last verified", () => {
    const now = new Date("2026-11-16T12:00:00Z");
    expect(verifiedLabel({ verified: "live", last_verified_at: "2026-11-16T10:00:00Z" }, now)).toBe("Verified live 2 h ago");
    expect(verifiedLabel({ verified: "unconfirmed", last_verified_at: "2026-11-16T11:59:00Z" }, now)).toContain("could not confirm");
    expect(verifiedLabel({ verified: undefined, last_verified_at: undefined }, now)).toBeNull();
  });
});

describe("board drops", () => {
  it("moves postings between prospect, interested and closed", () => {
    expect(dropAction(card({}), "interested")).toEqual({ type: "patch_posting", stage: "interested" });
    expect(dropAction(card({}), "closed")).toMatchObject({ type: "patch_posting", stage: "dismissed" });
  });

  it("opens the tailor dialog when a posting is dropped on a resume stage", () => {
    expect(dropAction(card({}), "resume_ready")).toEqual({ type: "tailor" });
    expect(dropAction(card({}), "applied").type).toBe("invalid");
  });

  it("advances projects through the outcome stages and never backwards", () => {
    const project = card({ kind: "project", column: "resume_ready" });
    expect(dropAction(project, "applied")).toEqual({ type: "patch_project", patch: { outcome_stage: 1 } });
    expect(dropAction(project, "interviewing")).toEqual({ type: "patch_project", patch: { outcome_stage: 2 } });
    expect(dropAction(project, "offer")).toEqual({ type: "patch_project", patch: { outcome_stage: 4 } });
    expect(dropAction(project, "closed")).toEqual({ type: "patch_project", patch: { status: "rejected" } });
    expect(dropAction(card({ kind: "project", column: "applied" }), "prospect").type).toBe("invalid");
    expect(dropAction(project, "resume_ready")).toEqual({ type: "none" });
  });

  it("groups cards by column, best fit first", () => {
    const grouped = groupByColumn([card({ id: "a", fit: 60 }), card({ id: "b", fit: 90 }), card({ id: "c", column: "applied" })], ["prospect", "applied"]);
    expect(grouped.prospect.map((c) => c.id)).toEqual(["b", "a"]);
    expect(grouped.applied).toHaveLength(1);
  });

  it("flags prospects that have been open three weeks", () => {
    expect(isStale(card({ age_days: 25 }))).toBe(true);
    expect(isStale(card({ age_days: 25, column: "applied" }))).toBe(false);
    expect(isStale(card({ age_days: 3 }))).toBe(false);
  });
});
