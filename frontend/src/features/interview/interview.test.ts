import { describe, expect, it } from "vitest";
import { buildPayload, describePayload, emptyDraft, hasContent, type InterviewData } from "./interview";

const data: InterviewData = {
  exists: true,
  companies: ["Acme"],
  questions: [
    { id: "q1", question: "Influencing a VP?", why: "" },
    { id: "q2", question: "Roadmap ownership?", why: "" },
  ],
  skills: [
    { name: "Databricks", kind: "hard", status: "gap" },
    { name: "Executive influence", kind: "soft", status: "positionable" },
    { name: "Airflow", kind: "hard", status: "gap" },
  ],
};

describe("buildPayload", () => {
  it("sends only answered questions and decided skills", () => {
    const draft = emptyDraft();
    draft.answers.q1 = { text: "  I got the VP to fund it.  ", employer: "Acme" };
    draft.answers.q2 = { text: "   ", employer: "general" };
    draft.skills.Databricks = { answer: "no", note: "" };
    draft.skills["Executive influence"] = { answer: "have", note: " Presented to the VP. " };
    draft.skills.Airflow = { answer: "unsure", note: "" };
    const p = buildPayload(data, draft);
    expect(p.answers).toEqual([{ question: "Influencing a VP?", text: "I got the VP to fund it.", employer: "Acme" }]);
    expect(p.skills.map((s) => [s.name, s.status, s.note])).toEqual([
      ["Databricks", "no", ""],
      ["Executive influence", "have", "Presented to the VP."],
    ]);
  });

  it("defaults the employer to general and reports empty drafts", () => {
    const draft = emptyDraft();
    draft.answers.q1 = { text: "Yes.", employer: "" };
    expect(buildPayload(data, draft).answers[0].employer).toBe("general");
    expect(hasContent(buildPayload(data, emptyDraft()))).toBe(false);
  });
});

describe("describePayload", () => {
  it("summarizes what will be saved", () => {
    const draft = emptyDraft();
    draft.answers.q1 = { text: "Yes.", employer: "general" };
    draft.skills.Airflow = { answer: "have", note: "" };
    expect(describePayload(buildPayload(data, draft))).toBe("Saves 1 story and 1 confirmed skill to your profile for future applications.");
    expect(describePayload(buildPayload(data, emptyDraft()))).toBe("Nothing to save yet.");
  });
});
