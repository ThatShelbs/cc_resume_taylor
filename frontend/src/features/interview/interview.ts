/** Pure helpers for the pre-generation interview: shapes from the API and the payload we send back. */

export interface InterviewQuestion {
  id: string;
  question: string;
  why: string;
}

export interface InterviewSkillCheck {
  name: string;
  kind: "hard" | "soft";
  status: string;
}

export interface InterviewData {
  exists: boolean;
  seniority?: string;
  target_title?: string;
  questions: InterviewQuestion[];
  skills: InterviewSkillCheck[];
  companies: string[];
}

export type SkillAnswer = "have" | "no" | "unsure";

export interface InterviewDraft {
  answers: Record<string, { text: string; employer: string }>;
  skills: Record<string, { answer: SkillAnswer; note: string }>;
}

export interface InterviewPayload {
  answers: { question: string; text: string; employer: string }[];
  skills: { name: string; kind: "hard" | "soft"; status: "have" | "no"; note: string }[];
}

export const emptyDraft = (): InterviewDraft => ({ answers: {}, skills: {} });

/** Only what the user actually answered is sent: blank answers and "not sure" skills are left out. */
export function buildPayload(data: Pick<InterviewData, "questions" | "skills">, draft: InterviewDraft): InterviewPayload {
  const answers = data.questions
    .map((q) => ({
      question: q.question,
      text: (draft.answers[q.id]?.text ?? "").trim(),
      employer: draft.answers[q.id]?.employer || "general",
    }))
    .filter((a) => a.text);
  const skills = data.skills.flatMap((s) => {
    const entry = draft.skills[s.name];
    if (!entry || entry.answer === "unsure") return [];
    return [{ name: s.name, kind: s.kind, status: entry.answer, note: entry.note.trim() }];
  });
  return { answers, skills };
}

export const hasContent = (p: InterviewPayload): boolean => p.answers.length > 0 || p.skills.length > 0;

/** A one-line summary of what saving will do, shown beside the button. */
export function describePayload(p: InterviewPayload): string {
  const have = p.skills.filter((s) => s.status === "have").length;
  const parts = [];
  if (p.answers.length) parts.push(`${p.answers.length} ${p.answers.length === 1 ? "story" : "stories"}`);
  if (have) parts.push(`${have} confirmed ${have === 1 ? "skill" : "skills"}`);
  return parts.length ? `Saves ${parts.join(" and ")} to your profile for future applications.` : "Nothing to save yet.";
}
