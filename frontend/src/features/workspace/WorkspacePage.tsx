import { CircleAlert, Eye, FileText, Gauge, History, LayoutTemplate, NotebookPen, PenLine, ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { AlertDialog, AlertDialogContent } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useJobs, useJobState } from "@/features/jobs/JobCenter";
import { ContentEditor } from "@/features/workspace/components/ContentEditor";
import { HistoryPanel } from "@/features/workspace/components/HistoryPanel";
import { InsightsPanel } from "@/features/workspace/components/InsightsPanel";
import { PostingPanel } from "@/features/workspace/components/PostingPanel";
import { PreviewPane } from "@/features/workspace/components/PreviewPane";
import { ReadyCard } from "@/features/workspace/components/ReadyCard";
import { StatusBanners } from "@/features/workspace/components/StatusBanners";
import { TemplateTab } from "@/features/workspace/components/TemplateTab";
import { TrackingPanel } from "@/features/workspace/components/TrackingPanel";
import { WorkspaceHeader } from "@/features/workspace/components/WorkspaceHeader";
import { WorkspaceSkeleton } from "@/features/workspace/components/WorkspaceSkeleton";
import { useProjectActions } from "@/features/workspace/hooks/useProjectActions";
import { useWorkspaceDraft } from "@/features/workspace/hooks/useWorkspaceDraft";
import { projectFileUrl } from "@/lib/api/client";
import { useProject, useProjectFacts, useSystem } from "@/lib/api/queries";
import { usePatchProject } from "@/lib/api/queries";
import { isDone } from "@/lib/api/sse";
import type { JobSummary, ProjectDetail, TemplateKey } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";

/** One job application: edit the tailored resume beside its rendered PDF. */
export default function WorkspacePage() {
  const { id = "" } = useParams();
  const { data, isLoading, error } = useProject(id);

  if (isLoading) return <WorkspaceSkeleton />;
  if (error || !data)
    return (
      <div className="mx-auto max-w-2xl p-6 pt-16">
        <EmptyState
          icon={CircleAlert}
          title="Project not found"
          description={(error as Error)?.message ?? "It may have been moved to the trash."}
          action={
            <Button asChild>
              <Link to={ROUTES.projects}>Back to projects</Link>
            </Button>
          }
        />
      </div>
    );
  return <Workspace key={id} detail={data} />;
}

function Workspace({ detail }: { detail: ProjectDetail }) {
  const { project, result, outputs } = detail;
  const pid = project.id;
  const { open: openJob } = useJobs();
  const { data: system } = useSystem();
  const { data: facts } = useProjectFacts(pid);
  const patch = usePatchProject(pid);

  const { draft, update, save, saveState, lint, resetSaved } = useWorkspaceDraft(detail);
  const { startJob, duplicate, remove, restoreVersion } = useProjectActions(project, resetSaved);
  const [tab, setTab] = useState("content");
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Latest job for this project (live if it's running).
  const jobState = useJobState(detail.job?.id);
  const job: JobSummary | null = jobState?.job ?? detail.job ?? null;
  const running = !!job && !isDone(job);

  const render = useCallback(
    async (template?: TemplateKey) => {
      if (!draft) return;
      if (lint?.counts.error) {
        toast.error("Remove the blocked content first", { description: "A line matches your never-claim list." });
        return;
      }
      if (!(await save(draft))) return;
      startJob.mutate({ kind: "render", template });
    },
    [draft, lint, save, startJob],
  );

  // Ctrl/Cmd+S: save now and re-render.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "s" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        if (!running && draft) render();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [render, running, draft]);

  const pdf = outputs.find((f) => f.name.startsWith("out_resume_") && f.name.endsWith(".pdf"));
  const pdfUrl = pdf ? projectFileUrl(pid, pdf.name, { bust: project.rendered_at ?? pdf.modified }) : null;
  const stale = saveState !== "saved" || project.outputs_stale;
  const blockedInputs = system?.onboarding_needed;
  const generate = () => startJob.mutate({ kind: "generate" });

  const preview = <PreviewPane project={project} result={result} draft={draft} pdfUrl={pdfUrl} stale={stale} wordAvailable={system?.word} />;

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
      <Button asChild variant="ghost" size="sm" className="-ml-2 mb-2 text-muted-foreground">
        <Link to={ROUTES.projects}>
          <ArrowLeft /> Projects
        </Link>
      </Button>

      <WorkspaceHeader
        project={project}
        outputs={outputs}
        job={job}
        hasDraft={!!draft}
        saveState={saveState}
        running={running}
        stale={stale}
        blockedInputs={blockedInputs}
        rendering={startJob.isPending && startJob.variables?.kind === "render"}
        generating={startJob.isPending && startJob.variables?.kind === "generate"}
        onRender={() => render()}
        onGenerate={() => (draft ? setConfirmRegen(true) : generate())}
        onDuplicate={() => duplicate.mutate()}
        onDelete={() => setConfirmDelete(true)}
        onOpenJob={openJob}
      />

      <StatusBanners
        project={project}
        job={job}
        running={running}
        hasDraft={!!draft}
        blockedInputs={blockedInputs}
        onOpenJob={openJob}
        onRegenerate={() => setConfirmRegen(true)}
      />

      <Tabs value={tab} onValueChange={setTab} className="mt-6">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList>
            <TabsTrigger value="content">
              <PenLine /> Content
              {!!lint?.counts.error && <span className="ml-0.5 size-1.5 rounded-full bg-destructive" />}
            </TabsTrigger>
            <TabsTrigger value="preview" className="lg:hidden">
              <Eye /> Preview
            </TabsTrigger>
            <TabsTrigger value="template">
              <LayoutTemplate /> Template
            </TabsTrigger>
            <TabsTrigger value="insights" disabled={!draft}>
              <Gauge /> Insights
            </TabsTrigger>
            <TabsTrigger value="posting">
              <FileText /> Posting
            </TabsTrigger>
            <TabsTrigger value="history">
              <History /> History
            </TabsTrigger>
            <TabsTrigger value="tracking">
              <NotebookPen /> Tracking
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="mt-4 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(380px,44%)] 2xl:grid-cols-[minmax(0,1fr)_600px]">
          <div className="min-w-0">
            <TabsContent value="content" className="mt-0">
              {draft ? (
                <ContentEditor draft={draft} update={update} lint={lint} facts={facts} />
              ) : (
                <ReadyCard project={project} running={running} disabled={blockedInputs} onGenerate={generate} />
              )}
            </TabsContent>
            <TabsContent value="preview" className="mt-0 lg:hidden">
              {preview}
            </TabsContent>
            <TabsContent value="template" className="mt-0">
              <TemplateTab
                value={project.template}
                disabled={running}
                onChange={(t) => {
                  if (t === project.template) return;
                  patch.mutate({ template: t });
                  if (draft) render(t);
                }}
              />
            </TabsContent>
            <TabsContent value="insights" className="mt-0">
              {result && <InsightsPanel pid={pid} result={result} lint={lint} />}
            </TabsContent>
            <TabsContent value="posting" className="mt-0">
              <PostingPanel project={project} jobText={detail.job_text} result={result} />
            </TabsContent>
            <TabsContent value="history" className="mt-0">
              {result ? (
                <HistoryPanel pid={pid} current={result} onRestore={(vid) => restoreVersion.mutate(vid)} />
              ) : (
                <EmptyState icon={History} title="No versions yet" description="Generate a resume to start its history." />
              )}
            </TabsContent>
            <TabsContent value="tracking" className="mt-0">
              <TrackingPanel project={project} />
            </TabsContent>
          </div>
          <aside className="hidden lg:block">
            <div className="sticky top-20">{preview}</div>
          </aside>
        </div>
      </Tabs>

      <AlertDialog open={confirmRegen} onOpenChange={setConfirmRegen}>
        <AlertDialogContent
          title="Generate a fresh draft?"
          description="Claude re-tailors your materials to this posting. The current version, including any hand edits, is kept in History, and you can restore it anytime."
          confirmLabel="Regenerate"
          onConfirm={async () => {
            if (draft && !(await save(draft))) return;
            generate();
          }}
        />
      </AlertDialog>
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent
          title="Move this project to the trash?"
          description="You can restore it from the Projects page."
          confirmLabel="Move to trash"
          destructive
          onConfirm={() => remove.mutate()}
        />
      </AlertDialog>
    </div>
  );
}
