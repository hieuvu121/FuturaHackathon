import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import PageSkeleton from "@/components/PageSkeleton";
import { ApiError, answerDrill, getNextDrill } from "@/lib/data";
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

export default function RecallPage() {
  const reduceMotion = useReducedMotion();
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
      setGrade(await answerDrill({ question_id: step.question.id, submission }));
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "That answer could not be checked.");
    } finally {
      setChecking(false);
    }
  }

  /** The grade already carries the next question, so advancing costs no request. */
  function advance() {
    if (!grade?.next) return;
    setStep(grade.next);
    setSubmission(grade.next.question?.starter ?? "");
    setGrade(null);
  }

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
              ? `You answered ${step?.asked} questions. Every skill has been placed, so there is nothing left to learn from asking more.`
              : "Analyse a repository first, then return when there is evidence worth revisiting."}
          </p>
          <Link className="primary-button" href="/roadmap">See your roadmap</Link>
        </section>
      </main>
    );
  }

  const coding = question.type === "coding";

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
        <span>{step?.asked ?? 0} answered</span>
        <span>{step?.remaining_skills ?? 0} skills left to place</span>
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
            <span className={`drill-kind kind-${question.type}`}>{coding ? "Coding task" : "Concept"}</span>
            <span className="drill-skill">{question.skill_ids.join(", ").replace(/_/g, " ")}</span>
            <span className="drill-level">
              <LevelPips level={question.level} />
              {LEVEL_LABEL[question.level]}
            </span>
          </div>

          {step?.reason && <p className="drill-reason" data-testid="drill-reason">{step.reason}</p>}

          <h2 data-testid="drill-prompt">{question.prompt}</h2>

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
              <span>{coding ? "Compared against a reference solution" : "Compared against the key points"}</span>
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
              {grade.model_answer && (
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
    </motion.main>
  );
}
