import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { SaveState } from "../components/SaveIndicator";
import { fingerprint, fromDraft, toDraft, type Draft } from "../draft";
import { api } from "@/lib/api/client";
import { keys } from "@/lib/api/queries";
import type { LintResult, Project, ProjectDetail } from "@/lib/api/types";

/**
 * The editable copy of a project's result and everything that keeps it honest:
 * debounced autosave, live truthfulness checks (lint), adopting a newer result from
 * the server, and a warning before leaving with unsaved edits.
 */
export function useWorkspaceDraft(detail: ProjectDetail) {
  const { result } = detail;
  const pid = detail.project.id;
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(() => (result ? toDraft(result) : null));
  const savedFp = useRef(fingerprint(draft));
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [lint, setLint] = useState<LintResult>();

  // Adopt a new result from the server (after a generation or render) unless
  // there are local edits in flight.
  useEffect(() => {
    if (!result) {
      setDraft(null);
      savedFp.current = "";
      return;
    }
    const incoming = toDraft(result);
    const fp = fingerprint(incoming);
    if (fp === savedFp.current) return;
    if (saveState === "dirty" || saveState === "saving") return;
    savedFp.current = fp;
    setDraft(incoming);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const update = useCallback((fn: (d: Draft) => Draft) => {
    setDraft((d) => (d ? fn(d) : d));
  }, []);

  const save = useCallback(
    async (d: Draft) => {
      const fp = fingerprint(d);
      if (fp === savedFp.current) {
        setSaveState("saved");
        return true;
      }
      setSaveState("saving");
      try {
        const summary = await api.put<Project>(`/api/projects/${pid}/result`, fromDraft(d));
        savedFp.current = fp;
        qc.setQueryData<ProjectDetail>(keys.project(pid), (old) => (old ? { ...old, project: summary, result: fromDraft(d) } : old));
        setSaveState("saved");
        return true;
      } catch (e) {
        setSaveState("error");
        toast.error("Couldn't save your edits", { description: (e as Error).message });
        return false;
      }
    },
    [pid, qc],
  );

  // Autosave (debounced) whenever the draft really changes.
  useEffect(() => {
    if (!draft) return;
    if (fingerprint(draft) === savedFp.current) return;
    setSaveState("dirty");
    const t = window.setTimeout(() => save(draft), 900);
    return () => window.clearTimeout(t);
  }, [draft, save]);

  // Live truthfulness checks (debounced).
  useEffect(() => {
    if (!draft) return;
    const t = window.setTimeout(() => {
      api
        .post<LintResult>(`/api/projects/${pid}/lint`, fromDraft(draft))
        .then(setLint)
        .catch(() => undefined);
    }, 350);
    return () => window.clearTimeout(t);
  }, [draft, pid]);

  // Don't lose edits that haven't reached the server yet.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (saveState === "dirty" || saveState === "saving") e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [saveState]);

  /** Forget what was last saved, so the next result from the server replaces the draft. */
  const resetSaved = useCallback(() => {
    setSaveState("saved");
    savedFp.current = "";
  }, []);

  return { draft, update, save, saveState, lint, resetSaved };
}
