import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { JobSummary, Project, TemplateKey } from "@/lib/api/types";
import { ROUTES } from "@/lib/routes";

/** The server-side actions a project page can take: run a job, duplicate, trash, restore a version. */
export function useProjectActions(project: Project, onVersionRestored: () => void) {
  const pid = project.id;
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { track } = useJobs();

  const startJob = useMutation({
    mutationFn: ({ kind, template }: { kind: "generate" | "render"; template?: TemplateKey }) =>
      api.post<JobSummary>(`/api/projects/${pid}/${kind}`, kind === "render" && template ? { template } : undefined),
    onSuccess: (j, { kind }) => {
      qc.invalidateQueries({ queryKey: keys.project(pid) });
      if (kind === "generate") {
        track(j, {
          title: `Tailoring for ${project.company || project.name}`,
          coverLetter: project.cover_letter,
          successMessage: "Your tailored resume is ready",
        });
      } else {
        track(j, { open: false, successMessage: "Preview updated" });
      }
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const duplicate = useMutation({
    mutationFn: () => api.post<Project>(`/api/projects/${pid}/duplicate`),
    onSuccess: (copy) => {
      qc.invalidateQueries({ queryKey: keys.projects });
      navigate(ROUTES.project(copy.id));
      toast.success("Duplicated. You're now editing the copy.");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const remove = useMutation({
    mutationFn: () => api.del<{ trash_id: string }>(`/api/projects/${pid}`),
    onSuccess: ({ trash_id }) => {
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: keys.trash });
      navigate(ROUTES.projects);
      toast("Moved to trash", {
        description: project.name,
        action: { label: "Undo", onClick: () => api.post(`/api/trash/${trash_id}/restore`).then(() => qc.invalidateQueries({ queryKey: keys.projects })) },
      });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const restoreVersion = useMutation({
    mutationFn: (vid: string) => api.post<JobSummary>(`/api/projects/${pid}/versions/${vid}/restore`),
    onSuccess: (j) => {
      qc.invalidateQueries({ queryKey: ["project", pid] });
      track(j, { open: false, successMessage: "Version restored" });
      onVersionRestored();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return { startJob, duplicate, remove, restoreVersion };
}
