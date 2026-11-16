/** Every URL path in the app, in one place. `App.tsx` declares the routes; everything else links through here. */
export const ROUTES = {
  projects: "/",
  newProject: "/projects/new",
  project: (id: string) => `/projects/${id}`,
  progress: "/progress",
  profile: "/profile",
  resume: "/resume",
  evidence: "/evidence",
  jobSearch: "/job-search",
  jobSearchPipeline: "/job-search/pipeline",
  jobSearchCompanies: "/job-search/companies",
  jobSearchPreferences: "/job-search/preferences",
  settings: "/settings",
  welcome: "/welcome",
} as const;
