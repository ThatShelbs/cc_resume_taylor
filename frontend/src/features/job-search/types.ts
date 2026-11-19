/** Shapes the job search API returns. Named "posting" (not "job") because "job" already means a background task here. */

export type Tier = "full" | "partial" | "quick";
export type Depth = "quick" | "standard" | "deep";
export type Source =
  | "targets" | "ideated" | "boards" | "roberthalf" | "linkedin"
  | "linkedin_account" | "indeed_account" | "ziprecruiter_account";
export type AccountSite = "linkedin" | "indeed" | "ziprecruiter";
export interface AccountStatus {
  site: AccountSite;
  label: string;
  connected: boolean;
  /** The site's job search works without signing in (signing in is still offered). */
  login_optional: boolean;
  /** Usable in the next search: signed in (or login optional) and not paused. */
  ready: boolean;
  connected_at: string | null;
  last_used: string | null;
  cooldown_until: string | null;
  cooldown_reason: string;
  /** Per search run; there is no daily cap. */
  budget: { search: number; detail: number };
  last_run: { search: number; detail: number; at: string } | null;
}
export type FreshnessBand = "fresh" | "active" | "aging" | "late" | "unknown";
export type PostingStage = "prospect" | "interested" | "dismissed";

export interface Readiness {
  tier: Tier;
  has_profile: boolean;
  has_resume: boolean;
  has_fact_bank: boolean;
  targets: number;
  max_targets: number;
  new_strong: number;
  accounts: AccountStatus[];
  options: { counts: number[]; depths: Depth[]; sources: Source[]; clusters: Record<string, string> };
}

export interface Preferences {
  titles: string[];
  equivalent_titles: string[];
  min_level: string;
  skill_terms: string[];
  industries: string[];
  admired_companies: string[];
  about_me: string;
  home_location: string;
  radius_miles: number;
  anchor_cities: string[];
  allowed_cities: string[];
  remote_states: string[];
  relocation: "yes" | "no";
  remote_country: string;
  base_floor: number;
  exclusions: string[];
  recency_days: number;
  count: number;
  depth: Depth;
  sources: Source[];
  linkedin_direct: boolean;
}

export interface TargetRoute {
  status: "resolved" | "failed" | "unresolved";
  ats: string;
  job_count: number | null;
  verified_at: string | null;
  note: string;
  careers_url: string;
  board_url: string;
  search_url: string;
}

export interface Target {
  id: string;
  name: string;
  careers_url: string;
  cluster: string;
  rationale: string;
  notes: string;
  added_by: "user" | "suggested";
  route: TargetRoute;
}

export interface Suggestion {
  name: string;
  cluster: string;
  rationale: string;
  careers_url: string;
}

export interface SubScore {
  score: number;
  max: number;
  quotes?: string[];
  evidence?: string[];
}

export interface Fit {
  total: number;
  kind: "evidence" | "preference_match";
  subscores: Record<string, SubScore>;
  gaps: string[];
  angle: string;
  verdict: string;
  thin_description: boolean;
}

export interface Posting {
  id: string;
  title: string;
  company: string;
  locations: string[];
  work_mode: "remote" | "hybrid" | "onsite" | "unknown";
  url: string;
  apply_url: string;
  ats: string;
  source: string;
  also_listed_on: string[];
  aggregator_only: boolean;
  read_by_claude?: boolean;
  /** Set for a staffing agency's own posting (Robert Half); the hiring company is not named. */
  agency?: string;
  employment_type?: string;
  /** The company's own careers page, and its job search run for this title when the site has one. */
  company_careers_url?: string;
  company_search_url?: string;
  pay_min: number | null;
  pay_max: number | null;
  pay_text: string;
  posted_at: string | null;
  age_days: number | null;
  freshness: FreshnessBand;
  freshness_note: string;
  date_estimated: boolean;
  closes_at: string | null;
  verified?: "live" | "unconfirmed" | "closed";
  last_verified_at?: string;
  fit?: Fit;
  flags?: string[];
  stage: PostingStage;
  dismiss_reason: string;
  is_new: boolean;
  project_id: string;
  origin?: string;
  ideated_cluster?: string;
  work_mode_evidence?: string;
  bonus_equity?: string;
  description_text?: string;
}

export interface Rejection {
  id: string;
  title: string;
  company: string;
  url: string;
  reason: string;
  evidence: string;
}

export interface CoverageRow {
  company: string;
  origin: string;
  ats: string;
  count: number;
  status: "ok" | "failed";
  note: string;
  careers_url?: string;
  search_url?: string;
}

export interface RunReport {
  started: string;
  finished?: string;
  count: number;
  depth: Depth;
  tier: Tier;
  window_days?: number;
  results: Posting[];
  rejected: Rejection[];
  coverage: CoverageRow[];
  ideated: Suggestion[];
  notes: string[];
  source_counts: Record<string, number>;
  careers_only_share?: number;
  postings_seen?: number;
  timings?: Record<string, number>;
}

export interface RunSummary {
  id: string;
  started: string | null;
  finished: string | null;
  count: number | null;
  depth: Depth | null;
  found: number;
  rejected: number;
  tier: Tier | null;
  total_seconds: number | null;
}

export type Column = "prospect" | "interested" | "tailoring" | "resume_ready" | "applied" | "interviewing" | "offer" | "closed";

export interface BoardCard {
  kind: "posting" | "project";
  id: string;
  column: Column;
  title: string;
  company: string;
  url: string;
  fit: number | null;
  freshness: FreshnessBand | null;
  age_days: number | null;
  is_new?: boolean;
  dismiss_reason?: string;
  outcome_stage?: number;
  status?: string;
  posting_id?: string | null;
  active_job?: boolean;
  work_mode?: string;
  locations?: string[];
  updated_at: string;
}
