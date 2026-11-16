import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquareQuote, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { TemplatePicker } from "@/components/shared/TemplatePicker";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { InterviewSheet } from "@/features/interview/InterviewSheet";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys, useSettings } from "@/lib/api/queries";
import type { JobSummary, Project, TemplateKey } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { jsKeys, useReadiness } from "./api";
import type { Posting } from "./types";

type Mode = "generate" | "draft" | "interview";

/** Start a resume project from a found posting. No copying or pasting: the server builds the posting text. */
export function TailorDialog({
  posting,
  open,
  onOpenChange,
}: {
  posting: Pick<Posting, "id" | "title" | "company"> | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { track } = useJobs();
  const { data: settings } = useSettings();
  const { data: readiness } = useReadiness();
  const [template, setTemplate] = useState<TemplateKey | null>(null);
  const [coverLetter, setCoverLetter] = useState<boolean | null>(null);
  const [interview, setInterview] = useState<boolean | null>(null);
  const [interviewFor, setInterviewFor] = useState<Project | null>(null);

  const effectiveTemplate = template ?? (settings?.default_template as TemplateKey | undefined) ?? "classic";
  const effectiveCover = coverLetter ?? settings?.cover_letter_default ?? false;
  const effectiveInterview = interview ?? settings?.interview_default ?? false;
  const needsSetup = !!readiness && (!readiness.has_profile || !readiness.has_resume);

  const finish = (project: Project, job: JobSummary | null) => {
    qc.invalidateQueries({ queryKey: keys.projects });
    qc.invalidateQueries({ queryKey: jsKeys.all });
    if (job) {
      track(job, { title: `Tailoring for ${project.company || project.name}`, coverLetter: effectiveCover, successMessage: "Your tailored resume is ready" });
    }
    onOpenChange(false);
    navigate(ROUTES.project(project.id));
  };

  const create = useMutation({
    mutationFn: (mode: Mode) =>
      api.post<{ project: Project; job: JobSummary | null }>(`/api/job-search/postings/${posting?.id}/tailor`, {
        generate: mode === "generate",
        template: effectiveTemplate,
        cover_letter: effectiveCover,
      }),
    onSuccess: ({ project, job }, mode) => {
      if (mode === "interview") {
        qc.invalidateQueries({ queryKey: keys.projects });
        qc.invalidateQueries({ queryKey: jsKeys.all });
        setInterviewFor(project);
        return;
      }
      finish(project, job);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const generateAfterInterview = async (project: Project) => {
    try {
      const job = await api.post<JobSummary>(`/api/projects/${project.id}/generate`);
      finish(project, job);
    } catch (e) {
      toast.error((e as Error).message);
      navigate(ROUTES.project(project.id));
    }
  };

  return (
    <>
      <Dialog open={open && !interviewFor} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Tailor a resume for this role</DialogTitle>
            <DialogDescription>
              {posting ? `${posting.title} at ${posting.company}. ` : ""}The posting text comes straight from the careers page, so there is nothing to paste.
            </DialogDescription>
          </DialogHeader>

          {needsSetup ? (
            <Callout
              tone="warning"
              title="Set up your profile and base resume first"
              action={
                <Button asChild size="sm" variant="outline">
                  <Link to={readiness && !readiness.has_profile ? ROUTES.profile : ROUTES.resume}>
                    {readiness && !readiness.has_profile ? "Open Profile" : "Open Base resume"}
                  </Link>
                </Button>
              }
            >
              A tailored resume can only use what is really in your history. This posting stays in your Interested list until you are ready.
            </Callout>
          ) : (
            <>
              <TemplatePicker value={effectiveTemplate} onChange={setTemplate} size="sm" />
              <div className="grid gap-3 text-sm">
                <label className="flex items-center justify-between gap-4">
                  <span>Also write a cover letter</span>
                  <Switch checked={effectiveCover} onCheckedChange={setCoverLetter} aria-label="Also write a cover letter" />
                </label>
                <label className="flex items-center justify-between gap-4">
                  <span>
                    Interview me first
                    <span className="block text-xs text-muted-foreground">A few questions about this role to surface real experience.</span>
                  </span>
                  <Switch checked={effectiveInterview} onCheckedChange={setInterview} aria-label="Interview me before generating" />
                </label>
              </div>
            </>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            {!needsSetup && (
              <>
                <Button variant="outline" onClick={() => create.mutate("draft")} disabled={create.isPending}>
                  Save without generating
                </Button>
                {effectiveInterview ? (
                  <Button variant="gradient" onClick={() => create.mutate("interview")} loading={create.isPending}>
                    <MessageSquareQuote /> Interview, then generate
                  </Button>
                ) : (
                  <Button variant="gradient" onClick={() => create.mutate("generate")} loading={create.isPending}>
                    <Wand2 /> Generate resume
                  </Button>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {interviewFor && (
        <InterviewSheet
          projectId={interviewFor.id}
          open
          onOpenChange={(o) => {
            if (!o) {
              const project = interviewFor;
              setInterviewFor(null);
              onOpenChange(false);
              navigate(ROUTES.project(project.id));
            }
          }}
          onDone={() => {
            const project = interviewFor;
            setInterviewFor(null);
            void generateAfterInterview(project);
          }}
        />
      )}
    </>
  );
}
