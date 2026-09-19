/**
 * Presents a question with its code context and the input mode appropriate to
 * its type: prose for recall/justify/transfer, a code editor for debug/extend.
 * Owner: Track C.
 */

import { useState } from "react";

import type { GradeResult, Question } from "@/lib/types";

export interface QuestionCardProps {
  repoId: string;
  question: Question;
  onSubmit: (submission: string) => Promise<GradeResult>;
}

export default function QuestionCard({ repoId, question, onSubmit }: QuestionCardProps) {
  const [submission, setSubmission] = useState("");
  const [result, setResult] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState(false);

  const isCode = question.type === "debug" || question.type === "extend";

  async function handleSubmit() {
    setBusy(true);
    try {
      setResult(await onSubmit(submission));
    } finally {
      setBusy(false);
    }
  }

  // TODO(Track C): render CodeViewer for question.target, code editor when isCode.
  // Framing rule: this is revision, never an exam. No score out of 10, no ranking.
  return (
    <section className="space-y-3 rounded-xl border border-neutral-200 p-5">
      <span className="text-xs uppercase tracking-wide text-neutral-500">{question.type}</span>
      <p className="text-neutral-800">{question.prompt}</p>
      <textarea
        className="h-40 w-full rounded-lg border border-neutral-300 p-3 font-mono text-sm"
        value={submission}
        onChange={(e) => setSubmission(e.target.value)}
        placeholder={isCode ? "Your fix…" : "Your answer…"}
      />
      <button
        type="button"
        disabled={busy || !submission.trim()}
        onClick={handleSubmit}
        className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-40"
      >
        {busy ? "Checking…" : "Submit"}
      </button>
      {result && <p className="text-sm text-neutral-700">{result.feedback}</p>}
    </section>
  );
}
