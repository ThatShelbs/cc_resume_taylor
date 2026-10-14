import { BookCheck, Ban } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FactBank } from "@/features/evidence/components/FactBank";
import { Guardrails } from "@/features/evidence/components/Guardrails";

export default function EvidencePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Evidence"
        description="The guardrails that keep every resume truthful: a fact bank that every bullet must cite, and phrases that must never appear."
      />
      <Tabs defaultValue="facts" className="mt-6">
        <TabsList>
          <TabsTrigger value="facts">
            <BookCheck /> Fact bank
          </TabsTrigger>
          <TabsTrigger value="deny">
            <Ban /> Never-claim list
          </TabsTrigger>
        </TabsList>
        <TabsContent value="facts" className="mt-5">
          <FactBank />
        </TabsContent>
        <TabsContent value="deny" className="mt-5">
          <Guardrails />
        </TabsContent>
      </Tabs>
    </div>
  );
}
