/**
 * Temporary handwritten contracts mirroring backend/app/schemas.
 * This file will be replaced by openapi-typescript output when the backend OpenAPI schema is available.
 */

export interface Evidence {
  repo_id?: string | null;
  file: string;
  lines: [number, number];
  commit?: string | null;
}
export type SourceKind = "seeded" | "scraped" | "external" | "estimated";

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

export interface DimensionScore {
  dimension: string;
  level: 1 | 2 | 3 | 4;
  rationale: string;
  evidence: Evidence[];
  metric_basis: Record<string, number | string>;
}

export type Tier = "touched" | "verified";

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

export interface MarketSkill {
  skill_id: string;
  frequency: number | null;
  role: string;
  region: string;
  provenance: Provenance;
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
  has_original_commits?: boolean;
  function_count?: number;
  pushed_label?: string;
  stars?: number;
  pushed_at?: string;
  clone_url?: string;
  default_branch?: string;
  private?: boolean;
}

export interface PortfolioRepo {
  id: string;
  full_name: string;
  language: string | null;
  stage: string;
  progress: number;
}

export interface PortfolioSelection {
  repositories: PortfolioRepo[];
}

export interface PortfolioProfile {
  repositories: PortfolioRepo[];
  total_files: number;
  total_functions: number;
  excluded_files: number;
  scores: Scores;
  findings: Finding[];
}

export interface CurrentUser {
  user: string;
  mock_mode: boolean;
}

export interface CodeSlice {
  file: string;
  start: number;
  end: number;
  lines: string[];
  commit?: string | null;
}

export interface AnalysisStatus {
  repo_id?: string;
  stage: string;
  step: number;
  progress: number;
  done: boolean;
  error?: string | null;
}

export type NodeStatus = "verified" | "familiar" | "new";

export interface ConceptSkill {
  skill_id: string;
  skill_name: string;
  status: NodeStatus;
  /** Short next step, grounded in a real finding where one exists. */
  focus: string;
  /** new 0, familiar 0.5, verified 1 -- drives the node's bar. */
  mastery: number;
  /** The line the finding behind `focus` points at, when there is one. */
  gap_evidence: Evidence | null;
  related_to: string[];
  evidence: Evidence[];
  market_frequency: number | null;
  provenance: Provenance | null;
  priority: number;
}

export interface RoadmapConcept {
  concept_id: string;
  concept_name: string;
  summary: string;
  /** Mean mastery of this concept's skills. */
  mastery: number;
  verified_count: number;
  familiar_count: number;
  new_count: number;
  priority: number;
  skills: ConceptSkill[];
}

export interface RoadmapGraph {
  role: string;
  region: string;
  concepts: RoadmapConcept[];
}
