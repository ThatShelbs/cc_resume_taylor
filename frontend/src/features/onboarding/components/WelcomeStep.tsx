import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, FileText, ShieldCheck, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { BeadBracelet } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import { ROUTES } from "@/lib/routes";
import { StepHeader } from "./StepHeader";

export function WelcomeStep({ onNext }: { onNext: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const sample = useMutation({
    mutationFn: () => api.post("/api/demo/load"),
    onSuccess: async () => {
      await qc.invalidateQueries();
      toast.success("Sample data loaded. Clear it from the banner when you're ready for your own.");
      navigate(ROUTES.projects);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const points = [
    { icon: FileText, title: "Your real history, nothing else", text: "Every bullet is selected and rephrased from your own resume and profile. Titles, employers, and dates are copied exactly." },
    { icon: ShieldCheck, title: "Checked before it's written", text: "Numbers are verified against your materials, bullets cite their facts, and a never-claim list blocks overreach." },
    { icon: Sparkles, title: "Tailored to each posting", text: "Emphasis, ordering, and wording follow the job you paste, using your Claude subscription. Nothing leaves this computer otherwise." },
  ];
  return (
    <div>
      <BeadBracelet text="tailored" className="mb-5" />
      <StepHeader eyebrow="Welcome to Resume Taylor" title="Truthful resumes, tailored to every job">
        Setup takes about two minutes: upload the resume you already have, confirm your profile, and you're ready to paste your first
        job posting.
      </StepHeader>
      <div className="grid gap-3 sm:grid-cols-3">
        {points.map(({ icon: Icon, title, text }) => (
          <Card key={title} className="p-5">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10">
              <Icon className="size-4 text-primary" />
            </div>
            <div className="mt-4 text-sm font-semibold">{title}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{text}</p>
          </Card>
        ))}
      </div>
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Button variant="gradient" size="lg" onClick={onNext}>
          Get started <ArrowRight />
        </Button>
        <Button variant="outline" size="lg" disabled={sample.isPending} onClick={() => sample.mutate()}>
          <Sparkles /> {sample.isPending ? "Loading sample..." : "Try it with sample data"}
        </Button>
      </div>
      <p className="mt-3 max-w-xl text-xs text-muted-foreground">
        The sample is a made-up applicant (Jordan Rivera) with a profile, resume, and three example jobs, so you can look around
        without entering anything about yourself. You can remove it at any time.
      </p>
    </div>
  );
}
