import { describe, expect, it } from "vitest";
import { buildFunnel } from "@/features/progress/funnel";
import type { Project } from "@/lib/api/types";

const project = (patch: Partial<Project>): Project =>
  ({ id: "p", status: "draft", outcome_stage: 0, outcome_dates: {}, has_result: false, ...patch }) as Project;

describe("buildFunnel", () => {
  it("counts each stage cumulatively and computes step conversion", () => {
    const steps = buildFunnel([
      project({ has_result: true }),
      project({ outcome_stage: 1 }),
      project({ outcome_stage: 2 }),
      project({ outcome_stage: 4 }),
    ]);
    expect(steps.map((s) => s.count)).toEqual([4, 3, 2, 1, 1]);
    expect(steps[0].conversion).toBeNull();
    expect(steps[2].conversion).toBeCloseTo(2 / 3);
    expect(steps[4].conversion).toBe(1);
  });

  it("leaves out archived projects and avoids dividing by zero", () => {
    const steps = buildFunnel([project({ status: "archived", outcome_stage: 4 }), project({})]);
    expect(steps.map((s) => s.count)).toEqual([0, 0, 0, 0, 0]);
    expect(steps.every((s) => s.conversion === null)).toBe(true);
  });

  it("keeps closed projects at the stage they reached", () => {
    const steps = buildFunnel([project({ status: "rejected", outcome_stage: 2 })]);
    expect(steps.map((s) => s.count)).toEqual([1, 1, 1, 0, 0]);
  });
});
