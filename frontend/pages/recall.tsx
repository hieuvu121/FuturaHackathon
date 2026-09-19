/**
 * The revision loop. Owner: Track C.
 *
 * FRAMING RULE (OVERALL.md): framed as revision, never as an exam.
 * No failing grade. No ranking. No score shown as a mark out of anything.
 */

import { useEffect, useState } from "react";

import QuestionCard from "@/components/QuestionCard";
import { getQuestions, submitAnswer } from "@/lib/data";
import type { Question } from "@/lib/types";

const REPO_ID = "1";

export default function Recall() {
  const [questions, setQuestions] = useState<Question[]>([]);

  useEffect(() => {
    getQuestions(REPO_ID).then(setQuestions).catch(console.error);
  }, []);

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <h1 className="text-2xl font-medium">Revisit your code</h1>
      {questions.map((q) => (
        <QuestionCard
          key={q.id}
          repoId={REPO_ID}
          question={q}
          onSubmit={(submission) => submitAnswer({ question_id: q.id, submission })}
        />
      ))}
    </main>
  );
}
