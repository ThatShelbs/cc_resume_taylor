import { AlertCircle, AlertTriangle, Info, type LucideIcon } from "lucide-react";
import type { Severity } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const SEVERITY_ICON: Record<Severity, LucideIcon> = { error: AlertCircle, warning: AlertTriangle, info: Info };
const SEVERITY_TONE: Record<Severity, string> = {
  error: "text-destructive",
  warning: "text-warning",
  info: "text-muted-foreground",
};

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  const Icon = SEVERITY_ICON[severity];
  return <Icon className={cn("size-3.5 shrink-0", SEVERITY_TONE[severity], className)} />;
}
