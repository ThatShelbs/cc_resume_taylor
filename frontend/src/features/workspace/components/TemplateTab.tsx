import { TemplatePicker } from "@/components/shared/TemplatePicker";
import { Card } from "@/components/ui/card";
import type { TemplateKey } from "@/lib/api/types";

export function TemplateTab({ value, disabled, onChange }: { value: TemplateKey; disabled: boolean; onChange: (t: TemplateKey) => void }) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold">Template</h3>
      <p className="mb-4 mt-0.5 text-sm text-muted-foreground">
        Switching re-renders instantly from your current content. No new draft, no Claude call.
      </p>
      <TemplatePicker value={value} disabled={disabled} onChange={onChange} />
      <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
        Every template is single-column with standard fonts and nothing in headers or footers, which is what applicant
        tracking systems parse reliably.
      </p>
    </Card>
  );
}
