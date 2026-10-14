import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { Project, ResumeResult } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The posting, with the terms you genuinely have highlighted (read mode) or editable. */
export function PostingPanel({ project, jobText, result }: { project: Project; jobText: string; result: ResumeResult | null }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(jobText);
  const qc = useQueryClient();
  useEffect(() => setText(jobText), [jobText]);

  const save = useMutation({
    mutationFn: () => api.put(`/api/projects/${project.id}/job`, { text }),
    onSuccess: () => {
      toast.success("Posting saved", { description: "Regenerate to tailor against the updated text." });
      setEditing(false);
      qc.invalidateQueries({ queryKey: keys.project(project.id) });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const coverage = result?.coverage;
  const covered = useMemo(() => coverage?.covered ?? [], [coverage]);
  const missing = useMemo(() => coverage?.missing ?? [], [coverage]);
  const highlighted = useMemo(() => {
    const terms = [...covered.map((t) => [t, "c"] as const), ...missing.map((t) => [t, "m"] as const)].sort((a, b) => b[0].length - a[0].length);
    if (!terms.length) return [jobText];
    const re = new RegExp(`(?<![\\w])(${terms.map(([t]) => escapeRe(t)).join("|")})(?![\\w])`, "gi");
    const kind = new Map(terms.map(([t, k]) => [t.toLowerCase(), k]));
    return jobText.split(re).map((part, i) => {
      const k = kind.get(part.toLowerCase());
      if (!k || i % 2 === 0) return part;
      return (
        <mark
          key={i}
          className={cn(
            "rounded px-0.5",
            k === "c" ? "bg-success/15 text-foreground" : "bg-warning/15 text-foreground underline decoration-warning/60 decoration-dashed underline-offset-2",
          )}
        >
          {part}
        </mark>
      );
    });
  }, [jobText, covered, missing]);

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold">Job posting</h3>
        {project.url && (
          <a href={project.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary hover:underline">
            Original <ExternalLink className="size-3" />
          </a>
        )}
        <div className="ml-auto flex gap-2">
          {editing ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => (setText(jobText), setEditing(false))}>
                Cancel
              </Button>
              <Button size="sm" loading={save.isPending} onClick={() => save.mutate()}>
                <Save /> Save
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
              Edit
            </Button>
          )}
        </div>
      </div>
      {!editing && (covered.length > 0 || missing.length > 0) && (
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-success/30" /> In your resume
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-warning/30" /> You have it, but the resume doesn't use it
          </span>
        </div>
      )}
      {editing ? (
        <Textarea value={text} onChange={(e) => setText(e.target.value)} className="mt-3 min-h-[480px]" aria-label="Job posting text" />
      ) : (
        <div className="mt-4 max-h-[640px] overflow-auto whitespace-pre-wrap text-[13.5px] leading-relaxed">{highlighted}</div>
      )}
    </Card>
  );
}
