/** Text inputs: Input, Textarea and AutoTextarea (a textarea that grows with its content). */
import * as React from "react";
import { cn } from "@/lib/utils";

const fieldBase =
  "w-full rounded-md border border-input bg-background px-3 text-sm shadow-sm transition-[border-color,box-shadow] placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/20 focus-visible:ring-offset-0 disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive/20";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input type={type} ref={ref} className={cn(fieldBase, "h-9 py-1", className)} {...props} />
  ),
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(fieldBase, "min-h-[80px] py-2 leading-relaxed", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";

/** A textarea that grows with its content. */
export const AutoTextarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, value, ...props }, forwarded) => {
    const inner = React.useRef<HTMLTextAreaElement>(null);
    React.useImperativeHandle(forwarded, () => inner.current as HTMLTextAreaElement);
    React.useLayoutEffect(() => {
      const el = inner.current;
      if (!el) return;
      el.style.height = "0px";
      el.style.height = `${el.scrollHeight + 2}px`;
    }, [value]);
    return (
      <textarea
        ref={inner}
        value={value}
        rows={1}
        className={cn(fieldBase, "min-h-[36px] resize-none overflow-hidden py-2 leading-relaxed", className)}
        {...props}
      />
    );
  },
);
AutoTextarea.displayName = "AutoTextarea";
