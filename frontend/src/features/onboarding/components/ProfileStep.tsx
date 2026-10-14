import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cleanProfile } from "@/features/profile/cleanProfile";
import { ProfileEditor } from "@/features/profile/components/ProfileEditor";
import { type Prefill } from "@/features/resume/components/ResumeFlow";
import { api } from "@/lib/api/client";
import { keys, useProfile } from "@/lib/api/queries";
import type { Profile, ProfilePayload } from "@/lib/api/types";
import { uid } from "@/lib/utils";
import { StepHeader } from "./StepHeader";

function profileFromPrefill(p: Prefill | null): Profile {
  return {
    contact: { name: p?.name ?? "", email: p?.email ?? "", phone: p?.phone ?? "", location: p?.location ?? "", linkedin: p?.linkedin ?? "" },
    sections: [
      { id: uid(), title: "Skills", items: p?.skills?.length ? p.skills : [""] },
      { id: uid(), title: "Software/Tools", items: [""] },
      { id: uid(), title: "Projects", items: [""] },
      { id: uid(), title: "Recent Awards", items: [""] },
    ],
  };
}

export function ProfileStep({ prefill, onNext, onBack }: { prefill: Prefill | null; onNext: () => void; onBack: () => void }) {
  const { data, isLoading } = useProfile();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<Profile | null>(null);

  useEffect(() => {
    if (!data || draft) return;
    setDraft(data.exists ? data.profile : profileFromPrefill(prefill));
  }, [data, prefill, draft]);

  const save = useMutation({
    mutationFn: (p: Profile) => api.put<ProfilePayload>("/api/profile", cleanProfile(p)),
    onSuccess: (r) => {
      qc.setQueryData(keys.profile, r);
      qc.invalidateQueries({ queryKey: keys.system });
      toast.success("Profile saved");
      onNext();
    },
    onError: (e) => toast.error("Couldn't save", { description: (e as Error).message }),
  });

  return (
    <div>
      <StepHeader eyebrow="Step 2" title="Confirm your profile">
        {data?.exists
          ? "Here's your current profile. Add anything true that isn't on your resume."
          : "We pre-filled what we could from your resume. Add accomplishments, projects, and tools that aren't on it: the tailoring can only use what's here or in your resume."}
      </StepHeader>
      {isLoading || !draft ? <Skeleton className="h-96" /> : <ProfileEditor value={draft} onChange={setDraft} />}
      <div className="mt-6 flex items-center gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft /> Back
        </Button>
        <Button className="ml-auto" loading={save.isPending} onClick={() => draft && save.mutate(draft)}>
          Save and continue <ArrowRight />
        </Button>
      </div>
    </div>
  );
}
