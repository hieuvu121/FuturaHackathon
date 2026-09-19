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
  AnalysisStatus,
  Answer,
  Buckets,
  CodeSlice,
  Finding,
  GradeResult,
  Question,
  Repo,
  RepoMap,
  Scores,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
const PIPELINE_STEPS = 9;
let mockStep = -1;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

export async function getRepos(): Promise<Repo[]> {
  return USE_MOCK ? clone(reposMock as Repo[]) : request<Repo[]>("/repos");
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

export async function getRoadmap(repoId: string, role = "backend", region = "AU"): Promise<Buckets> {
  if (USE_MOCK) {
    const roadmaps = roadmapMock as unknown as Record<string, Buckets>;
    const roleData = roadmaps[role] ?? roadmaps.backend;
    return clone(roleData);
  }
  return request<Buckets>(`/repos/${repoId}/roadmap?role=${encodeURIComponent(role)}&region=${encodeURIComponent(region)}`);
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
  await Promise.all(repoIds.map((repoId) => request(`/repos/${repoId}/analyze`, { method: "POST" })));
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
  return request<AnalysisStatus>(`/repos/${repoId}/status`);
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

export async function updateShareVisibility(shareId: string, isPublic: boolean): Promise<{ is_public: boolean }> {
  if (USE_MOCK) {
    await wait(350);
    return { is_public: isPublic };
  }
  return request<{ is_public: boolean }>(`/shares/${encodeURIComponent(shareId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_public: isPublic }),
  });
}

export const dataMode = USE_MOCK ? "mock" : "live";
