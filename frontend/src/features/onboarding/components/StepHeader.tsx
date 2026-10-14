import type { ReactNode } from "react";

export function StepHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-6">
      <div className="text-xs font-medium uppercase tracking-wide text-primary">{eyebrow}</div>
      <h1 className="mt-1.5 text-balance text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
      {children && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{children}</p>}
    </div>
  );
}
