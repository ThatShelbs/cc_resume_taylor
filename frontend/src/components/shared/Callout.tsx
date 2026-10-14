import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Callout({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: "info" | "warning" | "error" | "success";
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const tones = {
    info: "border-info/25 bg-brand-sky/[0.18] [&_.callout-icon]:text-info dark:bg-info/[0.07]",
    warning: "border-warning/30 bg-warning/[0.07] [&_.callout-icon]:text-warning",
    error: "border-destructive/30 bg-destructive/[0.06] [&_.callout-icon]:text-destructive",
    success: "border-success/30 bg-success/[0.07] [&_.callout-icon]:text-success",
  } as const;
  const Icon = tone === "error" ? AlertCircle : tone === "warning" ? AlertTriangle : Info;
  return (
    <div className={cn("flex gap-3 rounded-lg border px-4 py-3 text-sm", tones[tone], className)}>
      <Icon className="callout-icon mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 leading-relaxed">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={cn("text-muted-foreground", title && "mt-0.5")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
