import { NavLink, Outlet } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";

const TABS = [
  { to: ROUTES.jobSearch, label: "Discover", end: true },
  { to: ROUTES.jobSearchPipeline, label: "Pipeline" },
  { to: ROUTES.jobSearchCompanies, label: "Companies" },
  { to: ROUTES.jobSearchPreferences, label: "Preferences" },
];

export default function JobSearchLayout() {
  return (
    <div className="mx-auto grid max-w-6xl gap-6 p-6">
      <PageHeader
        eyebrow="Job search"
        title="Find the roles worth applying to"
        description="Pulls postings straight from company career pages, where applicant pools are smaller, then ranks them by fit and freshness. Start a resume from any result with one click."
      />
      <nav aria-label="Job search sections" className="flex gap-1 border-b">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
