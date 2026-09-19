import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import type { GradeResult, Question } from "@/lib/types";

export interface QuestionCardProps {
  question: Question;
  onSubmit: (submission: string) => Promise<GradeResult>;
  result?: GradeResult;
  answer?: string;
  onAnswerChange?: (answer: string) => void;
  onResult?: (result: GradeResult) => void;
}

export default function QuestionCard({ question, onSubmit, result: suppliedResult, answer, onAnswerChange, onResult }: QuestionCardProps) {
  const reduceMotion = useReducedMotion();
  const [localSubmission, setLocalSubmission] = useState("");
  const [localResult, setLocalResult] = useState<GradeResult | undefined>();
  const [checking, setChecking] = useState(false);
  const codeAnswer = question.type === "debug" || question.type === "extend";
  const submission = answer ?? localSubmission;

  function updateSubmission(value: string) {
    if (onAnswerChange) onAnswerChange(value);
    else setLocalSubmission(value);
  }

  async function handleSubmit() {
    if (!submission.trim() || checking) return;
    setChecking(true);
    try {
      const nextResult = await onSubmit(submission);
      setLocalResult(nextResult);
      onResult?.(nextResult);
    } finally { setChecking(false); }
  }

  const result = suppliedResult ?? localResult;

  return (
    <article className="question-card surface">
      <div className="question-meta">
        <strong>{question.type} question</strong>
      </div>
      <h2>{question.prompt}</h2>
      <label htmlFor={`answer-${question.id}`} className="sr-only">Your answer</label>
      <textarea
        id={`answer-${question.id}`}
        value={submission}
        onChange={(event) => updateSubmission(event.target.value)}
        className={codeAnswer ? "code-answer" : undefined}
        placeholder={codeAnswer ? "Write the corrected line or implementation" : "Describe your thinking in a sentence or two"}
      />
      <div className="question-actions">
        <button type="button" className="primary-button" disabled={!submission.trim() || checking} onClick={handleSubmit}>
          {checking ? "Checking..." : result ? "Check again" : "Check my answer"}
        </button>
        <span>{codeAnswer ? "Checked by unit tests" : "Compared against a rubric"}</span>
      </div>
      <AnimatePresence>
        {result && (
          <motion.div
            className="gentle-feedback"
            role="status"
            initial={reduceMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            {result.feedback}
            {Object.keys(result.tier_change).length > 0 && <strong> Skill tier updated.</strong>}
          </motion.div>
        )}
      </AnimatePresence>
    </article>
  );
}
