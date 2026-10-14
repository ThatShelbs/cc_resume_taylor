import { useState } from "react";
import { Callout } from "@/components/shared/Callout";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import type { Draft } from "../draft";
import type { ProjectDetail } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { PdfPreview } from "./PdfPreview";
import { ResumePaper } from "./ResumePaper";

/** The resume on paper: the exact rendered PDF, or a live draft that updates as you type. */
export function PreviewPane({
  project,
  result,
  draft,
  pdfUrl,
  stale,
  wordAvailable,
}: {
  project: ProjectDetail["project"];
  result: ProjectDetail["result"];
  draft: Draft | null;
  pdfUrl: string | null;
  stale: boolean;
  wordAvailable: boolean | undefined;
}) {
  const [mode, setMode] = useState<"pdf" | "live">("pdf");

  // grid-cols-1 (minmax(0,1fr)) lets the column shrink; otherwise the PDF's
  // own width would size the track and the viewer could never fit it.
  return (
    <div className="grid min-w-0 grid-cols-1 gap-3">
      <div className="flex items-center gap-2">
        <div role="tablist" aria-label="Preview mode" className="inline-flex rounded-lg bg-secondary p-0.5">
          {(["pdf", "live"] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition-all",
                mode === m && "bg-background text-foreground shadow-soft",
              )}
            >
              {m === "pdf" ? "Exact PDF" : "Live draft"}
            </button>
          ))}
        </div>
        {mode === "pdf" && stale && pdfUrl && (
          <Tooltip content="The PDF shows the last render. Re-render to include your latest edits.">
            <Badge variant="warning" className="cursor-default">
              Edits not rendered
            </Badge>
          </Tooltip>
        )}
        {mode === "live" && <span className="text-xs text-muted-foreground">Updates as you type</span>}
        {result?.page_count ? <Badge variant="outline" className="ml-auto">{result.page_count} {result.page_count === 1 ? "page" : "pages"}</Badge> : null}
      </div>
      <div className="paper-canvas rounded-xl border p-4 sm:p-6">
        {mode === "live" && draft ? (
          <ResumePaper draft={draft} template={project.template} />
        ) : pdfUrl ? (
          <PdfPreview url={pdfUrl} />
        ) : draft ? (
          <div className="grid gap-3">
            <Callout tone="warning" title="No PDF for this version">
              {wordAvailable ? "Re-render to create one." : "PDF export needs Microsoft Word. Showing the live draft instead."}
            </Callout>
            <ResumePaper draft={draft} template={project.template} />
          </div>
        ) : (
          <div className="flex aspect-[8.5/11] items-center justify-center rounded-sm border border-dashed bg-background/60 text-sm text-muted-foreground">
            Your resume will appear here
          </div>
        )}
      </div>
    </div>
  );
}
