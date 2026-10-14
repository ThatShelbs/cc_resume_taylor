import type { Profile } from "@/lib/api/types";

/** Drop blank items so they don't count as unsaved changes or get written. */
export function cleanProfile(p: Profile): Profile {
  return { ...p, sections: p.sections.map((s) => ({ ...s, items: s.items.filter((i) => i.trim()) })) };
}
