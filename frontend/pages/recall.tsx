import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import PageSkeleton from "@/components/PageSkeleton";
import { ApiError, answerDrill, getNextDrill, getRoadmapGraph, redoRecall } from "@/lib/data";
import type { AdaptiveGrade, NextQuestion } from "@/lib/types";

const LEVEL_LABEL: Record<number, string> = {
  1: "Name it",
  2: "Explain it",
  3: "Reason about it",
  4: "Design with it",
};

function LevelPips({ level }: { level: number }) {
  return (
    <span className="level-pips" aria-label={`Level ${level} of 4`}>
      {[1, 2, 3, 4].map((step) => (
        <i key={step} className={step <= level ? "on" : undefined} />
      ))}
    </span>
  );
}

const GENERATING_STEPS = [
  "Scoring your five answers",
  "Placing each skill at its level",
  "Finding what is still missing",
  "Drawing your roadmap",
];
const STEP_MS = 850;

/**
 * The pause between the last answer and the roadmap. The roadmap is fetched
 * underneath it, so the page it leads to is already warm; the steps pace the
 * wait rather than measure it.
 */
function GeneratingRoadmap({ onDone }: { onDone: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  // Held in a ref so a parent re-render cannot restart the timers below.
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  }, [onDone]);

  useEffect(() => {
    let active = true;
    const ticker = window.setInterval(
      () => setStepIndex((current) => Math.min(current + 1, GENERATING_STEPS.length - 1)),
      STEP_MS,
    );
    const minimum = new Promise((resolve) => window.setTimeout(resolve, STEP_MS * GENERATING_STEPS.length));
    // A failed prefetch is not this screen's problem: the roadmap page reports it.
    void Promise.all([minimum, getRoadmapGraph().catch(() => undefined)]).then(() => active && done.current());
    return () => {
      active = false;
      window.clearInterval(ticker);
    };
  }, []);

  return (
    <main className="page">
      <section className="generating surface" role="status" aria-live="polite" data-testid="generating-roadmap">
        <span className="generating-spinner" aria-hidden="true" />
        <p className="eyebrow">Recall complete</p>
        <h1>Building your roadmap</h1>
        <ol className="generating-steps">
          {GENERATING_STEPS.map((label, index) => (
            <li key={label} className={index < stepIndex ? "done" : index === stepIndex ? "current" : undefined}>
              {label}
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}

/**
 * The pop-up that ends a session. It is a real dialog -- focus moves into it,
 * and the page behind it is inert -- because it is the one moment in recall
 * where the user has to decide where to go next.
 */
function SessionComplete({
  answered,
  heldUp,
  onSeeRoadmap,
}: {
  answered: number;
  heldUp: number | null;
  onSeeRoadmap: () => void;
}) {
  const action = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    action.current?.focus();
  }, []);

  return (
    <div className="modal-backdrop" data-testid="session-complete">
      <motion.section
        className="modal-card surface"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-complete-title"
        initial={{ opacity: 0, y: 18, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.28, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <span className="modal-badge" aria-hidden="true"><CheckMark /></span>
        <p className="eyebrow">Recall</p>
        <h2 id="session-complete-title">Session complete</h2>
        <p>
          You answered all {answered} questions
          {heldUp != null && `, and ${heldUp} of them held up`}. Your roadmap is built from these
          answers and from your code — it is ready when you are.
        </p>
        <button
          ref={action}
          type="button"
          className="primary-button"
          data-testid="see-roadmap"
          onClick={onSeeRoadmap}
        >
          See my roadmap
        </button>
      </motion.section>
    </div>
  );
}

function CheckMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  );
}

export default function RecallPage() {
  const reduceMotion = useReducedMotion();
  const router = useRouter();
  const [generating, setGenerating] = useState(false);
  const [complete, setComplete] = useState(false);
  const [restarting, setRestarting] = useState(false);
  // Answers given in THIS visit, so the pop-up can say how they went. A session
  // resumed after a refresh has fewer than five here, and then it says nothing.
  const [results, setResults] = useState<boolean[]>([]);
  const [step, setStep] = useState<NextQuestion | null>(null);
  const [submission, setSubmission] = useState("");
  const [grade, setGrade] = useState<AdaptiveGrade | null>(null);
  const [checking, setChecking] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function load() {
      try {
        const next = await getNextDrill();
        if (!active) return;
        setStep(next);
        setSubmission(next.question?.starter ?? "");
        setLoaded(true);
      } catch (error: unknown) {
        if (!active) return;
        // 404/409 mean the analysis has not finished yet, so keep waiting.
        if (error instanceof ApiError && [404, 409].includes(error.status)) {
          timer = window.setTimeout(load, 1800);
        } else {
          setLoadError(error instanceof Error ? error.message : "This session could not be started.");
          setLoaded(true);
        }
      }
    }
    void load();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  async function check() {
    if (!step?.question || !submission.trim() || checking) return;
    setChecking(true);
    try {
      const graded = await answerDrill({ question_id: step.question.id, submission });
      setGrade(graded);
      setResults((current) => [...current, graded.passed]);
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "That answer could not be checked.");
    } finally {
      setChecking(false);
    }
  }

  /** The grade already carries the next question, so advancing costs no request. */
  function advance() {
    if (!grade?.next) return;
    if (!grade.next.question) {
      // That was the last of the five: say so, and let the user choose to go on.
      setComplete(true);
      return;
    }
    setStep(grade.next);
    setSubmission(grade.next.question?.starter ?? "");
    setGrade(null);
  }

  /** A finished session is not a dead end: start another and the questions come back. */
  async function startNewSession() {
    setRestarting(true);
    try {
      await redoRecall();
      const next = await getNextDrill();
      setResults([]);
      setGrade(null);
      setComplete(false);
      setStep(next);
      setSubmission(next.question?.starter ?? "");
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "A new session could not be started.");
    } finally {
      setRestarting(false);
    }
  }

  if (generating) return <GeneratingRoadmap onDone={() => void router.push("/roadmap")} />;
  if (loadError) return <main className="page"><div className="error-state" role="alert">{loadError}</div></main>;
  if (!loaded) return <PageSkeleton label="Preparing a revision session" />;

  const question = step?.question ?? null;

  if (!question) {
    return (
      <main className="page">
        <section className="empty-state surface">
          <p className="eyebrow">Recall</p>
          <h1>{(step?.asked ?? 0) > 0 ? "Session complete" : "Nothing to revise yet"}</h1>
          <p>
            {(step?.asked ?? 0) > 0
              ? `You answered all ${step?.asked} questions, and your roadmap was built from them. If it does not look like you, dispute it there and you can sit the test again.`
              : "Analyse a repository first, then return when there is evidence worth revisiting."}
          </p>
          <div className="question-actions empty-actions">
            <Link className="primary-button" href="/roadmap">See your roadmap</Link>
            {(step?.asked ?? 0) > 0 && (
              <button
                type="button"
                className="ghost-button"
                data-testid="new-session"
                disabled={restarting}
                onClick={() => void startNewSession()}
              >
                {restarting ? "Starting…" : "Answer five new questions"}
              </button>
            )}
          </div>
        </section>
      </main>
    );
  }

  const coding = question.type === "coding";
  // Drills written against the user's own repository carry the code they are about.
  const fromRepo = Boolean(question.code_context);
  const choices = question.choices ?? [];
  const multipleChoice = choices.length > 0;

  return (
    <motion.main
      className="page recall-page"
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.4, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <header className="page-header">
        <p className="eyebrow">Recall</p>
        <h1 className="page-title">Find the edge of what you know</h1>
        <p className="page-copy">
          Each answer picks the next question. Get one right and it gets harder; miss one and it
          gets easier. This is how the gaps get found — there is no score to protect.
        </p>
      </header>

      <div className="drill-progress" role="status">
        <span data-testid="drill-count">
          Question {Math.min((step?.asked ?? 0) + 1, step?.session_length ?? 5)} of {step?.session_length ?? 5}
        </span>
        <span className="drill-dots" aria-hidden="true">
          {Array.from({ length: step?.session_length ?? 5 }, (_, index) => (
            <i key={index} className={index < (step?.asked ?? 0) ? "done" : index === (step?.asked ?? 0) ? "current" : undefined} />
          ))}
        </span>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.section
          key={question.id}
          className="drill-card surface"
          data-testid="drill-card"
          data-level={question.level}
          initial={reduceMotion ? false : { opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={reduceMotion ? undefined : { opacity: 0, x: -40 }}
          transition={{ duration: reduceMotion ? 0 : 0.32, ease: [0.77, 0, 0.18, 1] }}
        >
          <div className="drill-meta">
            <span className={`drill-kind kind-${question.type}`}>
              {fromRepo ? "Your code" : coding ? "Coding task" : "Concept"}
            </span>
            <span className="drill-skill">{question.skill_ids.join(", ").replace(/_/g, " ")}</span>
            <span className="drill-level">
              <LevelPips level={question.level} />
              {LEVEL_LABEL[question.level]}
            </span>
          </div>

          {step?.reason && <p className="drill-reason" data-testid="drill-reason">{step.reason}</p>}

          <h2 data-testid="drill-prompt">{question.prompt}</h2>

          {fromRepo && (
            <figure className="drill-context" data-testid="drill-context">
              <figcaption>
                {question.target_name}
                {question.target && ` · lines ${question.target.lines[0]}–${question.target.lines[1]}`}
              </figcaption>
              <pre>{question.code_context}</pre>
            </figure>
          )}

          {multipleChoice ? (
            <fieldset className="drill-choices" data-testid="drill-choices" disabled={Boolean(grade)}>
              <legend className="sr-only">Choose one answer</legend>
              {choices.map((choice, index) => {
                const picked = submission === choice;
                // After grading, the model answer is the right option: mark it, and the miss.
                const verdict = !grade
                  ? ""
                  : choice === grade.model_answer
                    ? " correct"
                    : picked
                      ? " wrong"
                      : "";
                return (
                  <label key={choice} className={`drill-choice${picked ? " picked" : ""}${verdict}`}>
                    <input
                      type="radio"
                      name={`drill-${question.id}`}
                      data-testid={`drill-choice-${index}`}
                      checked={picked}
                      onChange={() => setSubmission(choice)}
                    />
                    <span className="drill-choice-letter" aria-hidden="true">{"ABCD"[index] ?? index + 1}</span>
                    <span>{choice}</span>
                  </label>
                );
              })}
            </fieldset>
          ) : (
            <>
              <label htmlFor="drill-answer" className="sr-only">Your answer</label>
              <textarea
                id="drill-answer"
                data-testid="drill-answer"
                value={submission}
                spellCheck={!coding}
                onChange={(event) => setSubmission(event.target.value)}
                className={coding ? "code-answer" : undefined}
                placeholder={coding ? "Write the implementation" : "A sentence or two is enough"}
                disabled={Boolean(grade)}
              />
            </>
          )}

          {!grade ? (
            <div className="question-actions">
              <button
                type="button"
                className="primary-button"
                data-testid="drill-check"
                disabled={!submission.trim() || checking}
                onClick={() => void check()}
              >
                {checking ? "Checking..." : "Check my answer"}
              </button>
              <span>
                {multipleChoice
                  ? "Pick the best answer"
                  : coding
                    ? "Compared against a reference solution"
                    : "Compared against the key points"}
              </span>
            </div>
          ) : (
            <motion.div
              className={`drill-result ${grade.passed ? "passed" : "missed"}`}
              data-testid="drill-result"
              role="status"
              initial={reduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <strong>{grade.passed ? "That holds up" : "Not there yet"}</strong>
              <p>{grade.feedback}</p>
              {/* For multiple choice the right option is already highlighted in the list. */}
              {grade.model_answer && !multipleChoice && (
                <pre className="drill-model-answer">{grade.model_answer}</pre>
              )}
              {Object.keys(grade.tier_change).length > 0 && (
                <p className="drill-promotion">Verified — this skill moved up on your roadmap.</p>
              )}
              <div className="question-actions">
                <button type="button" className="primary-button" data-testid="drill-next" onClick={advance}>
                  {grade.next?.question ? "Next question" : "Finish session"}
                </button>
                {grade.next?.question && (
                  <span data-testid="drill-move">
                    {/* A level change only means harder or easier within the SAME
                        skill; across skills the number says nothing. */}
                    {grade.next.question.skill_ids[0] !== question.skill_ids[0]
                      ? "Moving to the next skill"
                      : grade.next.question.level > grade.level
                        ? "Going one level harder"
                        : grade.next.question.level < grade.level
                          ? "Easing off one level"
                          : "Another at this level"}
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </motion.section>
      </AnimatePresence>
      {complete && (
        <SessionComplete
          answered={grade?.next?.asked ?? step?.session_length ?? 5}
          heldUp={results.length === (step?.session_length ?? 5) ? results.filter(Boolean).length : null}
          onSeeRoadmap={() => setGenerating(true)}
        />
      )}
    </motion.main>
  );
}
