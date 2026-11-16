import { Copy, FileText, FolderOpen, MessageSquareQuote, MoreHorizontal, RefreshCcw, Sparkles, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Monogram } from "@/components/shared/Monogram";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api/client";
import { usePatchProject } from "@/lib/api/queries";
import type { FileInfo, JobSummary, Project } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";
import { formatDate, isMac, relativeTime } from "@/lib/utils";
import { DownloadMenu } from "./DownloadMenu";
import { EditableTitle } from "./EditableTitle";
import { SaveIndicator, type SaveState } from "./SaveIndicator";
import { StatusMenu } from "./StatusMenu";

/** Title, status and the primary actions (re-render, regenerate, more) for one project. */
export function WorkspaceHeader({
  project,
  outputs,
  job,
  hasDraft,
  saveState,
  running,
  stale,
  blockedInputs,
  rendering,
  generating,
  onRender,
  onGenerate,
  onInterview,
  onDuplicate,
  onDelete,
  onOpenJob,
}: {
  project: Project;
  outputs: FileInfo[];
  job: JobSummary | null;
  hasDraft: boolean;
  saveState: SaveState;
  running: boolean;
  stale: boolean;
  blockedInputs: boolean | undefined;
  rendering: boolean;
  generating: boolean;
  onRender: () => void;
  onGenerate: () => void;
  onInterview: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onOpenJob: (jobId: string) => void;
}) {
  const patch = usePatchProject(project.id);
  const onError = (e: unknown) => toast.error((e as Error).message);

  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3.5">
        <Monogram text={project.company || project.name} className="size-12 text-base" />
        <div className="min-w-0">
          <EditableTitle value={project.name} onSave={(name) => patch.mutate({ name }, { onError })} />
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <StatusMenu project={project} onChange={(status) => patch.mutate({ status })} />
            {project.company && <span>{project.company}</span>}
            {project.posting_id && (
              <Link to={ROUTES.jobSearchPipeline} className="rounded-full border px-2 py-0.5 text-[11px] font-medium hover:bg-secondary">
                From job search
              </Link>
            )}
            <span className="hidden sm:inline">·</span>
            <span>Created {formatDate(project.created_at)}</span>
            {project.last_generate?.ok && (
              <>
                <span className="hidden sm:inline">·</span>
                <span>Generated {relativeTime(project.last_generate.when)}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {hasDraft && <SaveIndicator state={saveState} />}
        {hasDraft && <DownloadMenu pid={project.id} outputs={outputs} />}
        {hasDraft && (
          <Tooltip content={<span>Apply your edits to the Word and PDF files <Kbd className="ml-1 border-background/30 bg-background/15 text-background">{isMac ? "⌘" : "Ctrl"} S</Kbd></span>}>
            <Button variant={stale ? "default" : "outline"} onClick={onRender} disabled={running} loading={rendering}>
              <RefreshCcw /> Re-render
            </Button>
          </Tooltip>
        )}
        <Button variant={hasDraft ? "outline" : "gradient"} onClick={onGenerate} disabled={running || blockedInputs} loading={generating}>
          <Sparkles /> {hasDraft ? "Regenerate" : "Generate"}
        </Button>
        {hasDraft && (
          <Tooltip content="Answer a few questions about this role, then regenerate with what you share">
            <Button variant="outline" onClick={onInterview} disabled={running || blockedInputs}>
              <MessageSquareQuote /> Improve with interview
            </Button>
          </Tooltip>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="More actions">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onDuplicate}>
              <Copy /> Duplicate for a similar role
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => api.post(`/api/projects/${project.id}/open-folder`).catch(onError)}>
              <FolderOpen /> Open project folder
            </DropdownMenuItem>
            {job && (
              <DropdownMenuItem onSelect={() => onOpenJob(job.id)}>
                <FileText /> Last run details
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem destructive onSelect={onDelete}>
              <Trash2 /> Move to trash
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
