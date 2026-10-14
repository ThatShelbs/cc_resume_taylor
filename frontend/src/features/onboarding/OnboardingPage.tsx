import { AnimatePresence, motion } from "framer-motion";
import { BookCheck, Check, FileText, Plus, Sparkles, UserRound } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/layout/Logo";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Button } from "@/components/ui/button";
import { DoneStep } from "@/features/onboarding/components/DoneStep";
import { FactsStep } from "@/features/onboarding/components/FactsStep";
import { ProfileStep } from "@/features/onboarding/components/ProfileStep";
import { ResumeStep } from "@/features/onboarding/components/ResumeStep";
import { WelcomeStep } from "@/features/onboarding/components/WelcomeStep";
import { type Prefill } from "@/features/resume/components/ResumeFlow";
import { useSystem } from "@/lib/api/queries";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";

const STEPS = [
  { key: "welcome", label: "Welcome", icon: Sparkles },
  { key: "resume", label: "Base resume", icon: FileText },
  { key: "profile", label: "Profile", icon: UserRound },
  { key: "facts", label: "Fact bank", icon: BookCheck },
  { key: "done", label: "First project", icon: Plus },
] as const;

export default function OnboardingPage() {
  const [step, setStep] = useState(0);
  const [prefill, setPrefill] = useState<Prefill | null>(null);
  const { data: system } = useSystem();
  const go = (i: number) => setStep(Math.max(0, Math.min(STEPS.length - 1, i)));

  return (
    <div className="min-h-screen bg-canvas">
      <header className="flex h-16 items-center justify-between px-5 sm:px-8">
        <Logo />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button asChild variant="ghost" size="sm">
            <Link to={ROUTES.projects}>Exit setup</Link>
          </Button>
        </div>
      </header>
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-5 pb-16 pt-4 sm:px-8 md:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="Setup steps" className="min-w-0 md:sticky md:top-8 md:self-start">
          <ol className="flex gap-2 overflow-x-auto md:grid md:gap-1">
            {STEPS.map((s, i) => {
              const done =
                (s.key === "resume" && system?.inputs.resume) ||
                (s.key === "profile" && system?.inputs.profile) ||
                (s.key === "facts" && system?.inputs.fact_bank) ||
                (s.key === "welcome" && step > 0);
              return (
                <li key={s.key}>
                  <button
                    type="button"
                    onClick={() => go(i)}
                    className={cn(
                      "flex w-full shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-secondary",
                      step === i && "bg-card font-medium shadow-soft ring-1 ring-border",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium",
                        done ? "border-success bg-success text-success-foreground" : step === i ? "border-primary text-primary" : "text-muted-foreground",
                      )}
                    >
                      {done ? <Check className="size-3.5" strokeWidth={3} /> : i + 1}
                    </span>
                    <span className="whitespace-nowrap">{s.label}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -12 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="min-w-0"
          >
            {step === 0 && <WelcomeStep onNext={() => go(1)} />}
            {step === 1 && <ResumeStep onNext={(p) => (p && setPrefill(p), go(2))} onBack={() => go(0)} />}
            {step === 2 && <ProfileStep prefill={prefill} onNext={() => go(3)} onBack={() => go(1)} />}
            {step === 3 && <FactsStep onNext={() => go(4)} onBack={() => go(2)} />}
            {step === 4 && <DoneStep />}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
