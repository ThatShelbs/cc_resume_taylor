import type React from "react";
import { cn, hueFor, initials } from "@/lib/utils";
import { SWATCHES } from "./brand";

export function Monogram({ text, className }: { text: string; className?: string }) {
  const swatch = SWATCHES[hueFor(text || "?") % SWATCHES.length];
  return (
    <div
      aria-hidden
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--mono)/0.5)] text-sm font-semibold tracking-tight text-brand-navy ring-1 ring-inset ring-[hsl(var(--mono))] dark:bg-[hsl(var(--mono)/0.14)] dark:text-[hsl(var(--mono))] dark:ring-[hsl(var(--mono)/0.3)]",
        className,
      )}
      style={{ "--mono": `var(--brand-${swatch})` } as React.CSSProperties}
    >
      {initials(text)}
    </div>
  );
}
