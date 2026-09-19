/**
 * The only mock/live boundary in the frontend.
 * Components import this module and never fetch or import mock files themselves.
 */

import codeMock from "../../backend/mock/code.json";
import findingsMock from "../../backend/mock/findings.json";
import questionsMock from "../../backend/mock/questions.json";
import repoMapMock from "../../backend/mock/repo_map.json";
import reposMock from "../../backend/mock/repos.json";
import roadmapMock from "../../backend/mock/roadmap.json";
import scoresMock from "../../backend/mock/scores.json";

import type {
  AdaptiveGrade, AnalysisStatus, Answer, Buckets, CapstoneState, CodeSlice, CurrentUser, Evidence, Finding, GradeResult, NextQuestion, PortfolioProfile, PortfolioSelection, Question, Repo, RepoMap, RoadmapGraph, RoadmapReview, Scores,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
const PIPELINE_STEPS = 9;
let mockStep = -1;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ?? detail;
    } catch { /* The response was not JSON. */ }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export const loginUrl = `${API}/auth/login`;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

export async function getRepos(): Promise<Repo[]> {
  return USE_MOCK ? clone(reposMock as Repo[]) : request<Repo[]>("/repos");
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return USE_MOCK ? { user: "demo-user", mock_mode: true } : request<CurrentUser>("/auth/me");
}

export async function getPortfolio(): Promise<PortfolioSelection> {
  if (USE_MOCK) {
    return { repositories: clone((reposMock as Repo[]).slice(0, 3)).map((repo) => ({
      id: repo.id, full_name: repo.full_name, language: repo.language, stage: "done", progress: 100,
    })) };
  }
  return request<PortfolioSelection>("/repos/portfolio");
}

export async function setPortfolio(repoIds: string[]): Promise<PortfolioSelection> {
  if (USE_MOCK) return getPortfolio();
  return request<PortfolioSelection>("/repos/portfolio", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_ids: repoIds }),
  });
}

function withMockRepo<T extends Evidence>(evidence: T): T {
  return { ...evidence, repo_id: evidence.repo_id ?? "orders-api" };
}

export async function getPortfolioProfile(): Promise<PortfolioProfile> {
  if (!USE_MOCK) return request<PortfolioProfile>("/repos/portfolio/profile");
  const scores = clone(scoresMock as unknown as Scores);
  scores.dimensions = scores.dimensions.map((item) => ({ ...item, evidence: item.evidence.map(withMockRepo) }));
  scores.skills = scores.skills.map((item) => ({ ...item, evidence: item.evidence.map(withMockRepo) }));
  const findings = clone(findingsMock as Finding[]).map((item) => ({ ...item, evidence: withMockRepo(item.evidence) }));
  return {
    repositories: (await getPortfolio()).repositories,
    total_files: (repoMapMock as RepoMap).total_files,
    total_functions: (repoMapMock as RepoMap).functions.length,
    excluded_files: (repoMapMock as RepoMap).excluded_files.length,
    scores,
    findings,
  };
}

export async function getRepoMap(repoId: string): Promise<RepoMap> {
  return USE_MOCK ? clone(repoMapMock as RepoMap) : request<RepoMap>(`/repos/${repoId}/repo_map`);
}

export async function getScores(repoId: string): Promise<Scores> {
  return USE_MOCK ? clone(scoresMock as unknown as Scores) : request<Scores>(`/repos/${repoId}/scores`);
}

export async function getFindings(repoId: string): Promise<Finding[]> {
  return USE_MOCK ? clone(findingsMock as Finding[]) : request<Finding[]>(`/repos/${repoId}/findings`);
}

export async function getQuestions(repoId: string): Promise<Question[]> {
  return USE_MOCK ? clone(questionsMock as Question[]) : request<Question[]>(`/repos/${repoId}/questions`);
}

export async function getPortfolioQuestions(): Promise<Question[]> {
  if (USE_MOCK) return clone(questionsMock as Question[]).map((question) => ({
    // Seeded drills carry no target; only code-derived questions have one.
    ...question, target: question.target ? withMockRepo(question.target) : null,
  }));
  return request<Question[]>("/repos/portfolio/questions");
}

export async function getRoadmap(repoId: string, role = "backend", region = "AU"): Promise<Buckets> {
  if (USE_MOCK) {
    const roadmaps = roadmapMock as unknown as Record<string, Buckets>;
    const roleData = roadmaps[role] ?? roadmaps.backend;
    return clone(roleData);
  }
  return request<Buckets>(`/repos/${repoId}/roadmap?role=${encodeURIComponent(role)}&region=${encodeURIComponent(region)}`);
}

export async function getPortfolioRoadmap(role = "backend", region = "AU"): Promise<Buckets> {
  if (USE_MOCK) return getRoadmap("orders-api", role, region);
  return request<Buckets>(`/repos/portfolio/roadmap?role=${encodeURIComponent(role)}&region=${encodeURIComponent(region)}`);
}

export async function getRoadmapReview(): Promise<RoadmapReview> {
  return request<RoadmapReview>("/repos/portfolio/roadmap/review");
}

export async function acceptRoadmap(): Promise<RoadmapReview> {
  return request<RoadmapReview>("/repos/portfolio/roadmap/review/accept", { method: "POST" });
}

/** Dispute by retesting: starts a fresh five-question recall session. */
export async function redoRecall(): Promise<RoadmapReview> {
  return request<RoadmapReview>("/repos/portfolio/roadmap/review/redo", { method: "POST" });
}

/** Dispute by editing: replaces the set of skills removed from the roadmap. */
export async function tailorRoadmap(hiddenSkills: string[]): Promise<RoadmapReview> {
  return request<RoadmapReview>("/repos/portfolio/roadmap/review/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hidden_skills: hiddenSkills }),
  });
}

export async function getRoadmapGraph(
  role = "software_engineer",
  region = "AU",
  includeHidden = false,
): Promise<RoadmapGraph> {
  // Always served by the API, in both modes. Grouping skills into concepts needs
  // the taxonomy in skills.yaml, which only the backend has -- and the backend
  // has its own mock mode, so this still works with no database behind it.
  const query = new URLSearchParams({ role, region, include_hidden: String(includeHidden) });
  return request<RoadmapGraph>(`/repos/portfolio/roadmap/graph?${query}`);
}

export async function getCapstone(): Promise<CapstoneState> {
  return request<CapstoneState>("/repos/portfolio/capstone");
}

export async function submitCapstone(repoUrl: string, notes: string): Promise<CapstoneState> {
  return request<CapstoneState>("/repos/portfolio/capstone/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl, notes }),
  });
}

export async function getNextDrill(): Promise<NextQuestion> {
  return request<NextQuestion>("/recall/next");
}

export async function answerDrill(answer: Answer): Promise<AdaptiveGrade> {
  return request<AdaptiveGrade>("/recall/answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });
}

export async function getCode(repoId: string, file: string, start: number, end: number): Promise<CodeSlice> {
  if (USE_MOCK) {
    const segment = codeMock.find((item) => item.repo_id === repoId && item.file === file);
    if (!segment) throw new Error(`No mock source available for ${file}`);
    const offsetStart = Math.max(0, start - segment.start);
    const offsetEnd = Math.min(segment.lines.length, end - segment.start + 1);
    return {
      file,
      start: segment.start + offsetStart,
      end: segment.start + offsetEnd - 1,
      lines: segment.lines.slice(offsetStart, offsetEnd),
      commit: segment.commit,
    };
  }
  const query = new URLSearchParams({ file, start: String(start), end: String(end) });
  return request<CodeSlice>(`/repos/${repoId}/code?${query}`);
}

export async function startAnalysis(repoIds: string[]): Promise<{ status: string }> {
  mockStep = -1;
  if (USE_MOCK) return { status: "queued" };
  await setPortfolio(repoIds);
  const queued = await Promise.allSettled(
    repoIds.map((repoId) => request(`/repos/${repoId}/analyze`, { method: "POST" }))
  );
  const failure = queued.find(
    (result): result is PromiseRejectedResult =>
      result.status === "rejected" && !(result.reason instanceof ApiError && result.reason.status === 409)
  );
  if (failure) throw failure.reason;
  return { status: "queued" };
}

export async function getStatus(repoId: string): Promise<AnalysisStatus> {
  if (USE_MOCK) {
    await wait(700);
    mockStep = Math.min(mockStep + 1, PIPELINE_STEPS);
    return {
      stage: mockStep < 5 ? "ingest" : "analyze",
      step: mockStep,
      progress: Math.round((Math.max(0, mockStep) / PIPELINE_STEPS) * 100),
      done: mockStep >= PIPELINE_STEPS,
    };
  }
  const status = await request<{ repo_id: string; stage: string; progress: number; error?: string | null }>(`/repos/${repoId}/status`);
  return {
    ...status,
    step: Math.min(PIPELINE_STEPS, Math.floor((status.progress / 100) * PIPELINE_STEPS)),
    done: status.stage === "done",
  };
}

export async function submitAnswer(answer: Answer): Promise<GradeResult> {
  if (USE_MOCK) {
    await wait(420);
    const debug = answer.question_id === "q-debug";
    return {
      question_id: answer.question_id,
      passed: true,
      score: 0.86,
      feedback: debug
        ? "Tests pass. Line 52 had its comparison flipped. Conditional logic is now verified."
        : "That captures the key trade-off. You connected the original choice to how the code behaves today.",
      tier_change: debug ? { refactoring_conditionals: "verified" } : {},
    };
  }
  return request<GradeResult>("/answers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(answer),
  });
}

export const dataMode = USE_MOCK ? "mock" : "live";
