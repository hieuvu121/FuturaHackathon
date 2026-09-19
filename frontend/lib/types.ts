/**
 * Hand-written ONLY until the backend is live. See OVERALL.md:
 *   "lib/types.ts -- Generated from the OpenAPI schema; never hand-written."
 *
 * Once the backend runs, regenerate with:
 *   npm run gen:types
 * and delete everything below the marker.
 */

// --- BEGIN placeholder (delete after first `npm run gen:types`) ---

export interface Evidence {
  file: string;
  lines: [number, number];
  commit?: string | null;
}

export type SourceKind = "seeded" | "scraped" | "external";

export interface Provenance {
  source_kind: SourceKind;
  source_name: string;
  confidence: number;
  sample_size?: number | null;
  collected_at?: string | null;
}

export interface FunctionNode {
  name: string;
  file: string;
  lines: [number, number];
  complexity: number;
  nesting_depth: number;
  loc: number;
  has_test: boolean;
  calls: string[];
  times_modified: number;
  last_modified?: string | null;
  created_commit?: string | null;
  author_ratio: number;
}

export interface RepoMap {
  repo: string;
  language: string;
  analyzed_at: string;
  total_files: number;
  excluded_files: string[];
  functions: FunctionNode[];
}

export type Severity = "low" | "medium" | "high";

export interface Finding {
  id: string;
  dimension: string;
  severity: Severity;
  observation: string;
  evidence: Evidence;
  confidence: number;
}

export type Tier = "touched" | "verified";

export interface DimensionScore {
  dimension: string;
  level: 1 | 2 | 3 | 4;
  rationale: string;
  evidence: Evidence[];
  metric_basis: Record<string, number | string>;
}

export interface SkillStatus {
  skill_id: string;
  tier: Tier;
  evidence: Evidence[];
}

export interface Scores {
  repo: string;
  dimensions: DimensionScore[];
  skills: SkillStatus[];
}

export type QuestionType = "recall" | "justify" | "transfer" | "debug" | "extend";

export interface Question {
  id: string;
  type: QuestionType;
  target: Evidence;
  target_name: string;
  prompt: string;
  code_context: string;
  skill_ids: string[];
}

export interface Answer {
  question_id: string;
  submission: string;
}

export interface GradeResult {
  question_id: string;
  passed: boolean;
  score: number;
  feedback: string;
  tier_change: Record<string, Tier>;
}

export type BucketName = "revise" | "deepen" | "learn_new";

export interface RoadmapItem {
  skill_id: string;
  skill_name: string;
  bucket: BucketName;
  reason: string;
  evidence: Evidence[];
  market_frequency: number | null;
  provenance: Provenance | null;
  priority: number;
}

export interface Buckets {
  role: string;
  region: string;
  revise: RoadmapItem[];
  deepen: RoadmapItem[];
  learn_new: RoadmapItem[];
}

export interface Repo {
  id: string;
  full_name: string;
  language: string | null;
  is_fork: boolean;
  stars: number;
  pushed_at: string;
}

export interface CodeSlice {
  file: string;
  start: number;
  end: number;
  lines: string[];
}

// --- END placeholder ---
