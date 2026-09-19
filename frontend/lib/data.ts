/**
 * The single switch between mock JSON and the live API.
 * NO COMPONENT MAY KNOW WHICH IS IN USE -- that is this file's whole job.
 *
 * Flip with NEXT_PUBLIC_USE_MOCK in .env.local.
 */

import type {
  Answer, Buckets, CodeSlice, Finding, GradeResult, Question, Repo, RepoMap, Scores,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

async function get<T>(path: string, mockFile: string): Promise<T> {
  const url = USE_MOCK ? `/mock/${mockFile}.json` : `${API}${path}`;
  const res = await fetch(url, USE_MOCK ? {} : { credentials: "include" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json() as Promise<T>;
}

export const getRepos = () => get<Repo[]>("/repos", "repos");

export const getRepoMap = (repoId: string) =>
  get<RepoMap>(`/repos/${repoId}/repo_map`, "repo_map");

export const getScores = (repoId: string) =>
  get<Scores>(`/repos/${repoId}/scores`, "scores");

export const getFindings = (repoId: string) =>
  get<Finding[]>(`/repos/${repoId}/findings`, "findings");

export const getQuestions = (repoId: string) =>
  get<Question[]>(`/repos/${repoId}/questions`, "questions");

export const getRoadmap = (repoId: string, role = "backend", region = "AU") =>
  get<Buckets>(`/repos/${repoId}/roadmap?role=${role}&region=${region}`, "roadmap");

export async function getCodeSlice(
  repoId: string, file: string, start: number, end: number,
): Promise<CodeSlice> {
  if (USE_MOCK) {
    return {
      file, start, end,
      lines: Array.from({ length: end - start + 1 }, (_, i) => `# mock line ${start + i} of ${file}`),
    };
  }
  const qs = new URLSearchParams({ file, start: String(start), end: String(end) });
  const res = await fetch(`${API}/repos/${repoId}/code?${qs}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Code slice failed: ${res.status}`);
  return res.json();
}

export async function startAnalysis(repoId: string): Promise<{ status: string }> {
  if (USE_MOCK) return { status: "queued" };
  const res = await fetch(`${API}/repos/${repoId}/analyze`, { method: "POST", credentials: "include" });
  return res.json();
}

export async function getStatus(repoId: string): Promise<{ stage: string; progress: number }> {
  if (USE_MOCK) return { stage: "done", progress: 100 };
  const res = await fetch(`${API}/repos/${repoId}/status`, { credentials: "include" });
  return res.json();
}

export async function submitAnswer(answer: Answer): Promise<GradeResult> {
  if (USE_MOCK) {
    return {
      question_id: answer.question_id, passed: true, score: 0.8,
      feedback: "Mock grading. Real grading arrives with Track B's grader.py.",
      tier_change: {},
    };
  }
  const res = await fetch(`${API}/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(answer),
  });
  return res.json();
}
