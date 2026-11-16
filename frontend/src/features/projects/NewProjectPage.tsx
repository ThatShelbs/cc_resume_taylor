import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ClipboardPaste, FileUp, MessageSquareQuote, Sparkles, Wand2 } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { PageHeader } from "@/components/shared/PageHeader";
import { TemplatePicker } from "@/components/shared/TemplatePicker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { InterviewSheet } from "@/features/interview/InterviewSheet";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys, useSettings, useSystem } from "@/lib/api/queries";
import type { JobSummary, Project, TemplateKey } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";

const MIN_POSTING = 40;

export default function NewProjectPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { track } = useJobs();
  const { data: system } = useSystem();
  const { data: settings } = useSettings();

  const [jobText, setJobText] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [url, setUrl] = useState("");
  const [template, setTemplate] = useState<TemplateKey | null>(null);
  const [coverLetter, setCoverLetter] = useState<boolean | null>(null);
  const [interview, setInterview] = useState<boolean | null>(null);
  const [interviewFor, setInterviewFor] = useState<Project | null>(null);
  const [dragging, setDragging] = useState(false);
  const touched = useRef({ company: false, role: false });
  const fileInput = useRef<HTMLInputElement>(null);

  const effectiveTemplate = template ?? ((settings?.default_template as TemplateKey) || "classic");
  const effectiveCover = coverLetter ?? settings?.cover_letter_default ?? false;
  const effectiveInterview = interview ?? settings?.interview_default ?? false;
  const ready = !system?.onboarding_needed;
  const tooShort = jobText.trim().length < MIN_POSTING;

  // Suggest company and role from the posting, without overwriting edits.
  useEffect(() => {
    if (tooShort || (touched.current.company && touched.current.role)) return;
    const t = window.setTimeout(async () => {
      try {
        const g = await api.post<{ company: string; role: string }>("/api/projects/guess", { text: jobText });
        if (!touched.current.company && g.company) setCompany(g.company);
        if (!touched.current.role && g.role) setRole(g.role);
      } catch {
        /* suggestions are optional */
      }
    }, 450);
    return () => window.clearTimeout(t);
  }, [jobText, tooShort]);

  // "interview" saves the project first, then asks a few questions before generating.
  const create = useMutation({
    mutationFn: (mode: "generate" | "draft" | "interview") =>
      api.post<{ project: Project; job: JobSummary | null }>("/api/projects", {
        job_text: jobText,
        company,
        role,
        url,
        template: effectiveTemplate,
        cover_letter: effectiveCover,
        generate: mode === "generate",
      }),
    onSuccess: ({ project, job }, mode) => {
      qc.invalidateQueries({ queryKey: keys.projects });
      if (mode === "interview") {
        setInterviewFor(project);
        return;
      }
      if (job) {
        track(job, { title: `Tailoring for ${project.company || project.name}`, coverLetter: effectiveCover, successMessage: "Your tailored resume is ready" });
      } else {
        toast.success("Project saved");
      }
      navigate(ROUTES.project(project.id));
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const generateAfterInterview = async (project: Project) => {
    try {
      const job = await api.post<JobSummary>(`/api/projects/${project.id}/generate`);
      qc.invalidateQueries({ queryKey: keys.projects });
      track(job, { title: `Tailoring for ${project.company || project.name}`, coverLetter: project.cover_letter, successMessage: "Your tailored resume is ready" });
    } catch (e) {
      toast.error((e as Error).message);
    }
    navigate(ROUTES.project(project.id));
  };

  const loadFile = async (file: File) => {
    try {
      const r = await api.upload<{ text: string; company: string; role: string }>("/api/projects/extract-posting", file);
      setJobText(r.text);
      if (!touched.current.company && r.company) setCompany(r.company);
      if (!touched.current.role && r.role) setRole(r.role);
      toast.success(`Loaded ${file.name}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) loadFile(file);
  };

  const pasteFromClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text.trim()) setJobText(text);
      else toast("Your clipboard is empty");
    } catch {
      toast("Press Ctrl+V in the box to paste");
    }
  };

  const words = jobText.trim() ? jobText.trim().split(/\s+/).length : 0;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 mb-3 text-muted-foreground">
        <Link to={ROUTES.projects}>
          <ArrowLeft /> Projects
        </Link>
      </Button>
      <PageHeader
        title="New project"
        description="Paste the job posting you're applying to. Resume Taylor tailors your real experience to it, and every claim stays traceable to your own materials."
      />

      {!ready && (
        <Callout
          tone="warning"
          className="mt-6"
          title="Finish setup to generate"
          action={
            <Button asChild size="sm" variant="outline">
              <Link to={ROUTES.welcome}>Start setup</Link>
            </Button>
          }
        >
          You can save this posting now. Generating needs your base resume and profile.
        </Callout>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card>
          <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
            <div>
              <CardTitle>Job posting</CardTitle>
              <CardDescription>Paste the full text, including requirements and responsibilities.</CardDescription>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <Button variant="outline" size="sm" onClick={pasteFromClipboard}>
                <ClipboardPaste /> Paste
              </Button>
              <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
                <FileUp /> File
              </Button>
              <input
                ref={fileInput}
                type="file"
                accept=".txt,.md,.pdf,.docx"
                className="hidden"
                onChange={(e) => e.target.files?.[0] && loadFile(e.target.files[0])}
              />
            </div>
          </CardHeader>
          <CardContent>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              className={cn("relative rounded-lg transition-shadow", dragging && "ring-2 ring-primary ring-offset-2 ring-offset-background")}
            >
              <Textarea
                autoFocus
                value={jobText}
                onChange={(e) => setJobText(e.target.value)}
                placeholder={"Director, Customer Analytics\n\nAbout the role\nYou will lead a team of analysts...\n\nTip: you can also drop a .docx, .pdf, or .txt file here."}
                className="min-h-[420px] resize-y font-[450] leading-relaxed"
                aria-label="Job posting text"
              />
              {dragging && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg bg-primary/5 text-sm font-medium text-primary">
                  Drop to load the posting
                </div>
              )}
            </div>
            <div className="mt-2 flex justify-between text-xs text-muted-foreground">
              <span>{tooShort && jobText ? "Keep going: that looks shorter than a full posting." : " "}</span>
              <span className="tabular-nums">{words.toLocaleString()} words</span>
            </div>
          </CardContent>
        </Card>

        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                Details
                {(company || role) && !tooShort && (
                  <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                    <Wand2 className="size-3" /> suggested from the posting
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4">
              <Field label="Company" htmlFor="company">
                <Input
                  id="company"
                  value={company}
                  onChange={(e) => {
                    touched.current.company = true;
                    setCompany(e.target.value);
                  }}
                  placeholder="Example Co."
                />
              </Field>
              <Field label="Role" htmlFor="role">
                <Input
                  id="role"
                  value={role}
                  onChange={(e) => {
                    touched.current.role = true;
                    setRole(e.target.value);
                  }}
                  placeholder="Director, Customer Analytics"
                />
              </Field>
              <Field label="Posting link" hint="Optional, for your records." htmlFor="url">
                <Input id="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" />
              </Field>
              <label className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
                <span>
                  <span className="block text-sm font-medium">Cover letter</span>
                  <span className="block text-xs text-muted-foreground">Built only from the validated resume</span>
                </span>
                <Switch checked={effectiveCover} onCheckedChange={setCoverLetter} aria-label="Also write a cover letter" />
              </label>
              <label className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5">
                <span>
                  <span className="block text-sm font-medium">Interview me first</span>
                  <span className="block text-xs text-muted-foreground">3 or 4 quick questions for a stronger match</span>
                </span>
                <Switch checked={effectiveInterview} onCheckedChange={setInterview} aria-label="Interview me before generating" />
              </label>
            </CardContent>
          </Card>

          <div className="grid gap-2">
            <Button
              variant="gradient"
              size="lg"
              disabled={tooShort || !ready}
              loading={create.isPending && create.variables !== "draft"}
              onClick={() => create.mutate(effectiveInterview ? "interview" : "generate")}
            >
              {effectiveInterview ? <MessageSquareQuote /> : <Sparkles />} {effectiveInterview ? "Interview, then generate" : "Save and generate"}
            </Button>
            <Button variant="outline" disabled={tooShort} loading={create.isPending && create.variables === "draft"} onClick={() => create.mutate("draft")}>
              Save as draft
            </Button>
            <p className="px-1 text-center text-xs leading-relaxed text-muted-foreground">
              Generation takes a minute or two and uses your Claude subscription through the Claude Code CLI.
            </p>
          </div>
        </div>
      </div>

      {interviewFor && (
        <InterviewSheet
          projectId={interviewFor.id}
          open
          onOpenChange={(o) => {
            // Dismissing without choosing keeps the saved project as a draft.
            if (!o) {
              const project = interviewFor;
              setInterviewFor(null);
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

      <div className="mt-8">
        <h2 className="text-sm font-semibold tracking-tight">Template</h2>
        <p className="mb-3 mt-0.5 text-sm text-muted-foreground">
          All three are single-column and ATS-friendly. You can switch any time without regenerating.
        </p>
        <TemplatePicker value={effectiveTemplate} onChange={setTemplate} />
      </div>
    </div>
  );
}
