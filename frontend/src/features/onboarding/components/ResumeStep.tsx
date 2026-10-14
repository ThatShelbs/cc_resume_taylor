import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ResumeFlow, type Prefill } from "@/features/resume/components/ResumeFlow";
import { useSystem } from "@/lib/api/queries";
import { StepHeader } from "./StepHeader";

export function ResumeStep({ onNext, onBack }: { onNext: (p: Prefill | null) => void; onBack: () => void }) {
  const { data: system } = useSystem();
  const [replace, setReplace] = useState(false);
  return (
    <div>
      <StepHeader eyebrow="Step 1" title="Upload the resume you already have">
        This defines your official employers, titles, and dates. PDF or Word both work; you'll review what was read before it's saved.
      </StepHeader>
      {system?.inputs.resume && !replace ? (
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <div className="flex size-10 items-center justify-center rounded-xl bg-success/10">
            <Check className="size-5 text-success" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="font-medium">You already have a base resume</div>
            <div className="truncate text-sm text-muted-foreground">{system.inputs.resume}</div>
          </div>
          <Button variant="outline" onClick={() => setReplace(true)}>
            Replace it
          </Button>
          <Button onClick={() => onNext(null)}>
            Continue <ArrowRight />
          </Button>
        </Card>
      ) : (
        <ResumeFlow confirmLabel="Save and continue" onConfirmed={(p) => onNext(p)} onCancel={system?.inputs.resume ? () => setReplace(false) : undefined} />
      )}
      <Button variant="ghost" className="mt-6" onClick={onBack}>
        <ArrowLeft /> Back
      </Button>
    </div>
  );
}
