import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, CheckCircle2, Save, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Callout } from "@/components/shared/Callout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { keys, useGuardrails } from "@/lib/api/queries";
import type { GuardrailsPayload } from "@/lib/api/types";
import { useDebounced } from "@/lib/useDebounced";

export function Guardrails() {
  const { data, isLoading } = useGuardrails();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [phrase, setPhrase] = useState("");
  useEffect(() => {
    if (data) setText(data.text);
  }, [data]);

  const debouncedText = useDebounced(text, 300);
  const debouncedPhrase = useDebounced(phrase, 250);
  const check = useQuery({
    queryKey: ["guardrails-test", debouncedText, debouncedPhrase],
    queryFn: () =>
      api.post<{ matches: string[]; patterns: GuardrailsPayload["patterns"] }>("/api/guardrails/test", {
        text: debouncedText,
        phrase: debouncedPhrase,
      }),
    enabled: !!data,
    placeholderData: (prev) => prev,
  });
  const patterns = check.data?.patterns ?? data?.patterns ?? [];
  const invalid = patterns.filter((p) => p.error);

  const save = useMutation({
    mutationFn: () => api.put<GuardrailsPayload>("/api/guardrails", { text }),
    onSuccess: (r) => {
      qc.setQueryData(keys.guardrails, r);
      qc.invalidateQueries({ queryKey: keys.system });
      toast.success("Never-claim list saved");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  if (isLoading) return <Skeleton className="h-80" />;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
      <Card className="p-5">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-primary" />
          <h3 className="text-sm font-semibold">Phrases that must never appear</h3>
          <Badge variant="secondary" className="ml-auto">
            {patterns.length - invalid.length} active
          </Badge>
        </div>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          One case-insensitive regular expression per line; lines starting with # are comments. Claude is told about them, and any
          match in a generated or edited resume blocks it from being written.
        </p>
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          className="mt-4 min-h-[420px] font-mono text-[12.5px] leading-6"
          aria-label="Never-claim patterns"
        />
        {invalid.length > 0 && (
          <div className="mt-3 grid gap-1">
            {invalid.map((p) => (
              <p key={p.line} className="flex items-center gap-1.5 text-xs text-destructive">
                <XCircle className="size-3.5" /> Line {p.line}: {p.error}
              </p>
            ))}
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <Button disabled={text === data?.text || invalid.length > 0} loading={save.isPending} onClick={() => save.mutate()}>
            <Save /> Save list
          </Button>
        </div>
      </Card>

      <div className="grid content-start gap-4">
        <Card className="p-5">
          <h3 className="text-sm font-semibold">Test a phrase</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">Try a sentence to see whether it would be blocked.</p>
          <Textarea
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder="e.g. AWS certified machine learning engineer"
            className="mt-3 min-h-[90px]"
            aria-label="Phrase to test"
          />
          {phrase.trim() &&
            (check.data?.matches.length ? (
              <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/[0.06] p-3 text-sm">
                <div className="flex items-center gap-1.5 font-medium text-destructive">
                  <Ban className="size-4" /> Blocked
                </div>
                <ul className="mt-1.5 grid gap-1">
                  {check.data.matches.map((m) => (
                    <li key={m} className="font-mono text-xs text-muted-foreground">
                      {m}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="mt-3 flex items-center gap-1.5 rounded-lg border border-success/30 bg-success/[0.07] p-3 text-sm font-medium text-success">
                <CheckCircle2 className="size-4" /> Allowed
              </div>
            ))}
        </Card>
        <Callout title="Tip: use phrases, not bare words">
          Block "as a software engineer", not "engineer", so "partnered with engineers" still reads fine.
        </Callout>
      </div>
    </div>
  );
}
