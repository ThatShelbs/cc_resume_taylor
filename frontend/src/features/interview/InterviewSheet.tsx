import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquareQuote, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useJobState, useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { JobSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { buildPayload, describePayload, emptyDraft, hasContent, type InterviewData, type InterviewDraft, type SkillAnswer } from "./interview";

const CHOICES: { value: SkillAnswer; label: string }[] = [
  { value: "have", label: "Yes, I have" },
  { value: "no", label: "No" },
  { value: "unsure", label: "Skip" },
];

/**
 * An optional, short interview before generating: a few questions about this posting plus the
 * skills worth confirming. Answers are saved to the fact bank and profile, so later applications
 * reuse them, then `onDone` starts the generation.
 */
export function InterviewSheet({
  projectId,
  open,
  onOpenChange,
  onDone,
}: {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after answers are saved (or the interview is skipped). The parent closes the sheet and starts the generation. */
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const { track } = useJobs();
  const [jobId, setJobId] = useState<string | null>(null);
  const [draft, setDraft] = useState<InterviewDraft>(emptyDraft);
  const [startError, setStartError] = useState<string | null>(null);
  const started = useRef(false);
  const stream = useJobState(jobId);

  // Prepare fresh questions each time the sheet opens, since the posting may have changed.
  useEffect(() => {
    if (!open) {
      started.current = false;
      setJobId(null);
      setDraft(emptyDraft());
      setStartError(null);
      return;
    }
    if (started.current) return;
    started.current = true;
    api
      .post<JobSummary>(`/api/projects/${projectId}/interview/questions`)
      .then((job) => {
        setJobId(job.id);
        track(job, { open: false, successMessage: "Your questions are ready" });
      })
      .catch((e: Error) => setStartError(e.message));
  }, [open, projectId, track]);

  const job = stream?.job ?? null;
  const data = job?.status === "succeeded" ? ((job.result as unknown as InterviewData | null) ?? null) : null;
  const failed = !!startError || job?.status === "failed" || job?.status === "cancelled";
  const payload = data ? buildPayload(data, draft) : null;

  const save = useMutation({
    mutationFn: () => api.post<{ facts_added: number; skills_added: string[] }>(`/api/projects/${projectId}/interview/answers`, payload),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: keys.facts });
      qc.invalidateQueries({ queryKey: keys.profile });
      qc.invalidateQueries({ queryKey: keys.projects });
      if (r.facts_added || r.skills_added.length) toast.success("Added to your profile and fact bank for future applications");
      onDone();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const skip = () => onDone();

  const setAnswer = (id: string, patch: Partial<{ text: string; employer: string }>) =>
    setDraft((d) => {
      const cur = d.answers[id] ?? { text: "", employer: "general" };
      return { ...d, answers: { ...d.answers, [id]: { ...cur, ...patch } } };
    });
  const setSkill = (name: string, patch: Partial<{ answer: SkillAnswer; note: string }>) =>
    setDraft((d) => {
      const cur = d.skills[name] ?? { answer: "unsure" as SkillAnswer, note: "" };
      return { ...d, skills: { ...d.skills, [name]: { ...cur, ...patch } } };
    });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-2xl" aria-describedby={undefined}>
        <div className="border-b px-6 py-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <MessageSquareQuote className="size-5 text-primary" /> A few quick questions
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Answer only what is true. Short answers are fine, and anything you skip is left out. What you share is saved so your next
            applications can use it too.
          </p>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          {!data && !failed && (
            <div className="flex items-center gap-3 rounded-lg border px-4 py-6 text-sm text-muted-foreground" role="status">
              <Loader2 className="size-4 animate-spin" /> Reading the posting and your materials to write your questions...
            </div>
          )}

          {failed && (
            <Callout tone="warning" title="Couldn't prepare questions">
              {startError ?? job?.hint ?? job?.error ?? "Something went wrong."} You can still generate without the interview.
            </Callout>
          )}

          {data && (
            <>
              {data.questions.map((q, i) => (
                <div key={q.id} className="grid gap-2">
                  <Field label={`${i + 1}. ${q.question}`} hint={q.why} htmlFor={`iv-${q.id}`}>
                    <Textarea
                      id={`iv-${q.id}`}
                      value={draft.answers[q.id]?.text ?? ""}
                      onChange={(e) => setAnswer(q.id, { text: e.target.value })}
                      placeholder="What was the situation, what did you do, and what changed? Leave blank if it doesn't apply."
                      className="min-h-[96px]"
                    />
                  </Field>
                  {(draft.answers[q.id]?.text ?? "").trim() && data.companies.length > 0 && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>This happened at</span>
                      <Select
                        aria-label="Employer for this answer"
                        value={draft.answers[q.id]?.employer ?? "general"}
                        onValueChange={(v) => setAnswer(q.id, { employer: v })}
                        options={[{ value: "general", label: "Not sure / several roles" }, ...data.companies.map((c) => ({ value: c, label: c }))]}
                        className="h-8 w-60"
                      />
                    </div>
                  )}
                </div>
              ))}

              {data.skills.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold">Confirm skills</h3>
                  <p className="mb-3 mt-0.5 text-sm text-muted-foreground">
                    The posting mentions these and your materials don't clearly show them. Tools and technologies stay off your resume unless
                    you confirm them here.
                  </p>
                  <ul className="grid gap-2">
                    {data.skills.map((s) => {
                      const entry = draft.skills[s.name] ?? { answer: "unsure" as SkillAnswer, note: "" };
                      return (
                        <li key={s.name} className="rounded-lg border px-3 py-2.5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="text-sm font-medium">
                              {s.name}
                              <span className="ml-2 text-xs font-normal text-muted-foreground">{s.kind === "hard" ? "tool or method" : "leadership"}</span>
                            </span>
                            <div role="radiogroup" aria-label={`Do you have ${s.name}?`} className="inline-flex gap-1 rounded-lg bg-secondary p-1">
                              {CHOICES.map((c) => (
                                <button
                                  key={c.value}
                                  type="button"
                                  role="radio"
                                  aria-checked={entry.answer === c.value}
                                  onClick={() => setSkill(s.name, { answer: c.value })}
                                  className={cn(
                                    "rounded-md px-3 py-1 text-[13px] font-medium text-muted-foreground transition-all",
                                    entry.answer === c.value && "bg-background text-foreground shadow-soft",
                                  )}
                                >
                                  {c.label}
                                </button>
                              ))}
                            </div>
                          </div>
                          {entry.answer === "have" && (
                            <Textarea
                              value={entry.note}
                              onChange={(e) => setSkill(s.name, { note: e.target.value })}
                              aria-label={`Where you used ${s.name}`}
                              placeholder={s.kind === "soft" ? "A sentence or two: when and how you did this." : "Optional: where you used it."}
                              className="mt-2 min-h-[64px]"
                            />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t px-6 py-4">
          <span className="max-w-[16rem] text-xs text-muted-foreground">{payload ? describePayload(payload) : ""}</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={skip} disabled={save.isPending}>
              Skip and generate
            </Button>
            {data && (
              <Button
                variant="gradient"
                loading={save.isPending}
                onClick={() => (payload && hasContent(payload) ? save.mutate() : skip())}
              >
                <Sparkles /> Save and generate
              </Button>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
