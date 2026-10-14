import { useMutation } from "@tanstack/react-query";
import { ArrowLeft, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useJobs } from "@/features/jobs/JobCenter";
import { api } from "@/lib/api/client";
import { useSystem } from "@/lib/api/queries";
import type { JobSummary } from "@/lib/api/types";
import { StepHeader } from "./StepHeader";

export function FactsStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { data: system } = useSystem();
  const { track } = useJobs();
  const draft = useMutation({
    mutationFn: () => api.post<JobSummary>("/api/facts/draft", { force: !!system?.inputs.fact_bank }),
    onSuccess: (job) => {
      track(job, { title: "Drafting your fact bank", open: false, successMessage: "Fact bank ready. Review it under Evidence." });
      toast("Drafting your fact bank in the background", { description: "You can keep going." });
      onNext();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <div>
      <StepHeader eyebrow="Step 3 · Optional" title="Add a fact bank for provenance checks">
        Claude splits your profile and resume into atomic facts, each tagged with its employer. From then on, every bullet must cite the
        facts it's built from, and a bullet that borrows another employer's fact is dropped automatically.
      </StepHeader>
      <Card className="p-5">
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          {[
            ["F012", "Northwind Traders", "Built a churn model that cut churn 12% in one year."],
            ["F013", "Northwind Traders", "Led a team of 4 analysts."],
            ["F021", "general", "Python, SQL, and Tableau."],
          ].map(([id, emp, text]) => (
            <div key={id} className="rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <span className="font-mono font-medium text-primary">{id}</span>
                {emp}
              </div>
              <p className="mt-1.5 text-[13px] leading-snug">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">Example facts. You can edit, add, or remove any of them later.</p>
      </Card>
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft /> Back
        </Button>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" onClick={onNext}>
            {system?.inputs.fact_bank ? "Keep my current bank" : "Skip for now"}
          </Button>
          <Button variant="gradient" loading={draft.isPending} disabled={system?.onboarding_needed} onClick={() => draft.mutate()}>
            <Sparkles /> {system?.inputs.fact_bank ? "Redraft it" : "Draft it for me"}
          </Button>
        </div>
      </div>
    </div>
  );
}
