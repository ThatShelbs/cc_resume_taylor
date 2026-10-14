import { cn } from "@/lib/utils";

export function Logo({ className, withText = true }: { className?: string; withText?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <img src="/favicon.svg" alt="" className="size-8 rounded-[10px] shadow-soft" />
      {withText && (
        <div className="leading-none">
          <div className="text-[15.5px] font-semibold tracking-tight">
            Resume <span className="font-display font-semibold italic text-primary">Taylor</span>
          </div>
          <div className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-muted-foreground">Truthfully tailored</div>
        </div>
      )}
    </div>
  );
}
