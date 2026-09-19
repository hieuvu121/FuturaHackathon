import { useEffect, useState } from "react";

import { answerPractice, getPracticeQuestions, getPracticeTopics } from "@/lib/data";
import type { PracticeGrade, PracticeTopic, Question, QuestionType } from "@/lib/types";

type Kind = Extract<QuestionType, "concept" | "coding" | "explain">;

const KINDS: { id: Kind; label: string; hint: string }[] = [
  { id: "concept", label: "Multiple choice", hint: "Pick the best answer" },
  { id: "coding", label: "Write code", hint: "Compared against a reference solution" },
  { id: "explain", label: "Explain code", hint: "Say what it does, and why" },
];

/**
 * Practice: pick a topic, pick a kind of question, work through them.
 *
 * Nothing here feeds the roadmap -- that is the evaluation's job -- so there is
 * no session, no counter to protect, and a question can be retried at once.
 */
export default function PracticePanel() {
  const [topics, setTopics] = useState<PracticeTopic[]>([]);
  const [topicId, setTopicId] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("concept");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [index, setIndex] = useState(0);
  const [submission, setSubmission] = useState("");
  const [grade, setGrade] = useState<PracticeGrade | null>(null);
  const [checking, setChecking] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getPracticeTopics()
      .then((found) => {
        if (!active) return;
        setTopics(found);
        setTopicId(found[0]?.skill_id ?? null);
        if (found.length === 0) setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Practice topics could not be loaded.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!topicId) return;
    let active = true;
    getPracticeQuestions(topicId, kind)
      .then((found) => {
        if (!active) return;
        setQuestions(found);
        setIndex(0);
        setGrade(null);
        setSubmission(found[0]?.starter ?? "");
        setError("");
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "Those questions could not be loaded.");
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [topicId, kind]);

  const question = questions[index] ?? null;
  const topic = topics.find((item) => item.skill_id === topicId) ?? null;
  const choices = question?.choices ?? [];

  function show(next: number) {
    const target = questions[next];
    setIndex(next);
    setGrade(null);
    setSubmission(target?.starter ?? "");
  }

  async function check() {
    if (!question || !submission.trim() || checking) return;
    setChecking(true);
    try {
      setGrade(await answerPractice({ question_id: question.id, submission }));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That answer could not be checked.");
    } finally {
      setChecking(false);
    }
  }

  if (loading) return <div className="capstone-loading" aria-busy="true">Loading practice topics…</div>;
  if (topics.length === 0) {
    return error ? <div className="error-state" role="alert">{error}</div> : <p>No practice topics yet.</p>;
  }

  return (
    <div className="practice" data-testid="practice-panel">
      <div className="practice-pickers">
        <div className="practice-picker" role="group" aria-label="Topic">
          <span className="practice-picker-label">Topic</span>
          {topics.map((item) => (
            <button
              key={item.skill_id}
              type="button"
              className="topic-chip"
              data-testid="practice-topic"
              aria-pressed={item.skill_id === topicId}
              onClick={() => setTopicId(item.skill_id)}
            >
              {item.name}
            </button>
          ))}
        </div>
        <div className="practice-picker" role="group" aria-label="Kind of question">
          <span className="practice-picker-label">Practise by</span>
          {KINDS.map((item) => (
            <button
              key={item.id}
              type="button"
              className="topic-chip"
              data-testid="practice-kind"
              aria-pressed={item.id === kind}
              onClick={() => setKind(item.id)}
            >
              {item.label}
              {topic && <small>{topic.counts[item.id] ?? 0}</small>}
            </button>
          ))}
        </div>
      </div>

      {topic?.summary && <p className="practice-summary">{topic.summary}</p>}
      {error && <div className="error-state" role="alert">{error}</div>}

      {question ? (
        <section className="drill-card surface" data-testid="practice-card" data-level={question.level}>
          <div className="drill-meta">
            <span className={`drill-kind kind-${question.type}`}>{KINDS.find((item) => item.id === question.type)?.label}</span>
            <span className="drill-skill">{topic?.name}</span>
            <span className="drill-level">Question {index + 1} of {questions.length}</span>
          </div>

          <h2 data-testid="practice-prompt">{question.prompt}</h2>

          {question.code_context && (
            <figure className="drill-context">
              <figcaption>Read this code</figcaption>
              <pre>{question.code_context}</pre>
            </figure>
          )}

          {choices.length > 0 ? (
            <fieldset className="drill-choices" disabled={Boolean(grade)}>
              <legend className="sr-only">Choose one answer</legend>
              {choices.map((choice, position) => {
                const picked = submission === choice;
                const verdict = !grade ? "" : choice === grade.model_answer ? " correct" : picked ? " wrong" : "";
                return (
                  <label key={choice} className={`drill-choice${picked ? " picked" : ""}${verdict}`}>
                    <input
                      type="radio"
                      name={`practice-${question.id}`}
                      data-testid={`practice-choice-${position}`}
                      checked={picked}
                      onChange={() => setSubmission(choice)}
                    />
                    <span className="drill-choice-letter" aria-hidden="true">{"ABCD"[position] ?? position + 1}</span>
                    <span>{choice}</span>
                  </label>
                );
              })}
            </fieldset>
          ) : (
            <>
              <label htmlFor="practice-answer" className="sr-only">Your answer</label>
              <textarea
                id="practice-answer"
                data-testid="practice-answer"
                value={submission}
                spellCheck={question.type !== "coding"}
                onChange={(event) => setSubmission(event.target.value)}
                className={question.type === "coding" ? "code-answer" : undefined}
                placeholder={question.type === "coding" ? "Write the implementation" : "Say what the code does, and why it is written this way"}
                disabled={Boolean(grade)}
              />
            </>
          )}

          {!grade ? (
            <div className="question-actions">
              <button
                type="button"
                className="primary-button"
                data-testid="practice-check"
                disabled={!submission.trim() || checking}
                onClick={() => void check()}
              >
                {checking ? "Checking..." : "Check my answer"}
              </button>
              <span>{KINDS.find((item) => item.id === question.type)?.hint}</span>
            </div>
          ) : (
            <div className={`drill-result ${grade.passed ? "passed" : "missed"}`} data-testid="practice-result" role="status">
              <strong>{grade.passed ? "That holds up" : "Not there yet"}</strong>
              <p>{grade.feedback}</p>
              {grade.model_answer && choices.length === 0 && (
                <pre className="drill-model-answer">{grade.model_answer}</pre>
              )}
              <div className="question-actions">
                {index + 1 < questions.length ? (
                  <button type="button" className="primary-button" data-testid="practice-next" onClick={() => show(index + 1)}>
                    Next question
                  </button>
                ) : (
                  <button type="button" className="primary-button" data-testid="practice-next" onClick={() => show(0)}>
                    Start this set again
                  </button>
                )}
                <button type="button" className="ghost-button" onClick={() => show(index)}>Try it again</button>
              </div>
            </div>
          )}
        </section>
      ) : (
        <div className="empty-bucket"><strong>No questions of this kind yet</strong><span>Pick another kind, or another topic.</span></div>
      )}
    </div>
  );
}
