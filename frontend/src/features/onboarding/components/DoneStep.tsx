import { PartyPopper, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { BeadBracelet, Sequins } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { useSystem } from "@/lib/api/queries";
import { ROUTES } from "@/lib/routes";

export function DoneStep() {
  const navigate = useNavigate();
  const { data: system } = useSystem();
  const ready = !system?.onboarding_needed;
  return (
    <div className="grid place-items-center py-10 text-center">
      <div className="relative px-10 py-6">
        <Sequins />
        <div className="absolute inset-6 rounded-full bg-primary/25 blur-2xl" />
        <div className="bg-brand-gradient relative flex size-16 items-center justify-center rounded-2xl shadow-lift">
          <PartyPopper className="size-7" />
        </div>
      </div>
      <BeadBracelet text={ready ? "ready" : "almost"} size="sm" className="mt-2" />
      <h1 className="mt-5 text-2xl font-semibold tracking-tight">{ready ? "You're all set" : "Almost there"}</h1>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        {ready
          ? "Paste a job posting and Resume Taylor will tailor your resume to it in a minute or two."
          : "Add your base resume and profile to start generating. You can still create projects in the meantime."}
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-2">
        <Button variant="outline" onClick={() => navigate(ROUTES.projects)}>
          Go to projects
        </Button>
        <Button variant="gradient" onClick={() => navigate(ROUTES.newProject)}>
          <Plus /> Create your first project
        </Button>
      </div>
    </div>
  );
}
