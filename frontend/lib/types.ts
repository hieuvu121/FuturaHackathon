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

export type QuestionType =
  | "recall" | "justify" | "transfer" | "debug" | "extend"
  // Seeded drills from the adaptive loop. These carry no code target.
  | "concept" | "coding" | "explain";

export interface Question {
  id: string;
  type: QuestionType;
  target: Evidence | null;
  target_name: string;
  prompt: string;
  code_context: string;
  skill_ids: string[];
  /** 1 name it, 2 explain it, 3 reason about it, 4 design with it. */
  level: number;
  /** Opening lines for a coding task. */
  starter: string;
  /** Options for a multiple-choice concept drill; the submission is the chosen text. Empty otherwise. */
  choices: string[];
}

/** A topic in the practice section, with how many questions of each kind it has. */
export interface PracticeTopic {
  skill_id: string;
  name: string;
  summary: string;
  counts: Record<string, number>;
}

/** The result of one practice question. Practice never changes the roadmap. */
export interface PracticeGrade {
  question_id: string;
  passed: boolean;
  score: number;
  feedback: string;
  missing: string[];
  model_answer: string;
}

export interface NextQuestion {
  question: Question | null;
  asked: number;
  /** How many questions one recall session asks. */
  session_length: number;
  remaining_skills: number;
  reason: string;
}

export interface AdaptiveGrade extends GradeResult {
  level: number;
  next_level: number | null;
  model_answer: string;
  next: NextQuestion | null;
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

export interface LearningResource {
  title: string;
  url: string;
  /** docs | guide | course | practice | reference */
  kind: string;
}

/** Where a PERSON stands in a skill. Not a question's difficulty (1-4), which describes questions. */
export type Proficiency = "beginner" | "intermediate" | "expert";

export interface ConceptSkill {
  skill_id: string;
  skill_name: string;
  status: NodeStatus;
  /** The person's level, read off the same number as the bar. */
  proficiency: Proficiency;
  /** False while the level rests on code or a survey answer alone; true once recall has tested it. */
  proficiency_tested: boolean;
  /** Short next step, grounded in a real finding where one exists. */
  focus: string;
  /** Untested: new 0, familiar 0.5, verified 1. Once recall has tested it: hardest level passed / 4. */
  mastery: number;
  /** What stands between the user and this skill, from their evidence, findings and recall results. */
  missing: string;
  /** External study material for this skill. */
  resources: LearningResource[];
  /** The user tailored this skill out. Only ever true when hidden skills were asked for. */
  hidden: boolean;
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
  /** Which step of the learning order this concept belongs to. */
  stage: number;
  verified_count: number;
  familiar_count: number;
  new_count: number;
  priority: number;
  skills: ConceptSkill[];
}

/** One step of the learning order. Concepts in the same stage are learnt side by side. */
export interface RoadmapStage {
  index: number;
  title: string;
  note: string;
  concept_ids: string[];
}

export interface RoadmapGraph {
  role: string;
  region: string;
  /** The role in words, when the roadmap was built for one. */
  role_name: string;
  /** "repos" when built from analysed code, "survey" when built from the onboarding survey. */
  source: "repos" | "survey";
  concepts: RoadmapConcept[];
  /** The order to learn the concepts in. Every concept appears in exactly one stage. */
  stages: RoadmapStage[];
}

/** Whether the user has agreed that this roadmap describes them. */
export interface RoadmapReview {
  status: "pending" | "accepted";
  hidden_skills: string[];
  recall_answered: number;
  recall_session_length: number;
}

/* --- The roadmap's final stage: one project, submitted and reviewed ------- */

export interface CapstoneRequirement {
  id: string;
  /** null for the baseline every project must meet. */
  skill_id: string | null;
  skill_name: string;
  text: string;
}

export interface CapstoneBrief {
  title: string;
  summary: string;
  target_skills: string[];
  requirements: CapstoneRequirement[];
  deliverables: string[];
  ready: boolean;
  readiness_note: string;
}

export type RequirementVerdict = "met" | "partial" | "missing";

export interface RequirementReview {
  requirement_id: string;
  verdict: RequirementVerdict;
  comment: string;
  /** Files in the submission that back the verdict. */
  files: string[];
}

export interface CapstoneReview {
  summary: string;
  strengths: string[];
  improvements: string[];
  requirements: RequirementReview[];
  /** Counted from the verdicts by the server, never asked of the model. */
  score: number;
  files_reviewed: number;
  /** True for the canned review served in mock mode. */
  sample: boolean;
}

export interface CapstoneSubmission {
  id: number;
  repo_url: string;
  notes: string;
  status: "reviewing" | "reviewed" | "failed";
  error: string | null;
  review: CapstoneReview | null;
  submitted_at: string | null;
}

export interface CapstoneState {
  brief: CapstoneBrief;
  submission: CapstoneSubmission | null;
}

/* --- Community: shared roadmaps and the reviews they collect --------------- */

/** Why a reviewer's word carries weight. Earned or granted, never self-declared. */
export type CommunityStanding = "mentor" | "experienced" | "member";
export type CommunityVerdict = "validates" | "suggests" | "comment";

export interface SharedStage {
  title: string;
  concepts: { name: string; mastery: number }[];
}

export interface CommunityComment {
  id: number;
  author: string;
  standing: CommunityStanding;
  verdict: CommunityVerdict;
  body: string;
  created_at: string | null;
  mine: boolean;
}

/** A snapshot, not a live view: reviews are about the roadmap as it was shared. */
export interface CommunityRoadmap {
  id: number;
  /** The role this roadmap is for, in the author's words. */
  title: string;
  summary: string;
  author: string;
  author_standing: CommunityStanding;
  overall: number;
  stages: SharedStage[];
  /** Reviews from mentors or experienced users only. */
  validations: number;
  suggestions: number;
  comment_count: number;
  is_sample: boolean;
  mine: boolean;
  created_at: string | null;
}

export interface CommunityRoadmapDetail extends CommunityRoadmap {
  comments: CommunityComment[];
  /** What badge the viewer's own review would carry. */
  my_standing: CommunityStanding;
}
/* --- Onboarding: the two ways in ------------------------------------------- */

export interface RolePath {
  id: string;
  name: string;
  summary: string;
  skills: { skill_id: string; name: string }[];
}

/** How this person came in. `path` is null until they have chosen. */
export interface LearnerProfile {
  path: "survey" | "repos" | null;
  role: string | null;
  role_name: string | null;
  known_skills: string[];
  user: string | null;
  /** Signed in by the survey, without a GitHub account. */
  guest: boolean;
  /** A GitHub token is on file. False for guests, and after GitHub rejected the last one. */
  github_connected: boolean;
}

