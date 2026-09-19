import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRef } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import CodeViewer from "@/components/CodeViewer";
import PageSkeleton from "@/components/PageSkeleton";
import QuestionCard from "@/components/QuestionCard";
import { getQuestions, getRepoMap, submitAnswer } from "@/lib/data";
import type { FunctionNode, GradeResult, Question } from "@/lib/types";

const REPO_ID = "orders-api";
const TYPES = ["recall", "justify", "transfer", "debug", "extend"] as const;

export default function RecallPage() {
  const reduceMotion = useReducedMotion();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [target, setTarget] = useState<FunctionNode | null>(null);
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, GradeResult>>({});
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    Promise.all([getQuestions(REPO_ID), getRepoMap(REPO_ID)])
      .then(([questionData, mapData]) => {
        setQuestions(questionData);
        setTarget(mapData.functions.find((node) => node.name === "apply_discounts") ?? mapData.functions[0] ?? null);
        setLoaded(true);
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof Error ? error.message : "Revision questions could not be loaded.");
        setLoaded(true);
      });
  }, []);

  const question = questions[index];
  const shownLines = useMemo(() => question?.type === "debug" ? question.code_context.split("\n") : 18, [question]);

  function goTo(nextIndex: number) {
    if (nextIndex < 0 || nextIndex >= questions.length || nextIndex === index) return;
    setDirection(nextIndex > index ? 1 : -1);
    setIndex(nextIndex);
  }

  function handleTabKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>, tabIndex: number) {
    let nextIndex = tabIndex;
    if (event.key === "ArrowRight") nextIndex = (tabIndex + 1) % questions.length;
    else if (event.key === "ArrowLeft") nextIndex = (tabIndex - 1 + questions.length) % questions.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = questions.length - 1;
    else return;
    event.preventDefault();
    goTo(nextIndex);
    window.requestAnimationFrame(() => tabRefs.current[nextIndex]?.focus());
  }

  if (loadError) return <main className="page"><div className="error-state" role="alert">{loadError}</div></main>;
  if (!loaded) return <PageSkeleton label="Preparing a revision session" />;
  if (!question || !target) return (
    <main className="page">
      <section className="empty-state surface">
        <p className="eyebrow">Recall</p>
        <h1>No revision questions yet</h1>
        <p>Analyse a repository first, then return when there is evidence worth revisiting.</p>
        <Link className="primary-button" href="/connect">Choose repositories</Link>
      </section>
    </main>
  );

  const container = { hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } };
  const item = { hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : .5, ease: [.2,.8,.2,1] as const } } };
  const answeredCount = Object.keys(results).length;
  const completed = answeredCount === questions.length;

  return (
    <motion.main className="page recall-page" variants={container} initial="hidden" animate="show">
      <motion.header className="page-header" variants={item}>
        <p className="eyebrow">Recall</p>
        <h1 className="page-title">Revisit code you wrote 7 weeks ago</h1>
        <p className="page-copy">This is revision, not an exam. There is no failing grade, and nothing here is ranked or shared.</p>
      </motion.header>

      <div className="recall-layout">
        <motion.section className="recall-source" variants={item}>
          <CodeViewer
            file={question.target.file}
            startLine={41}
            lines={shownLines}
            highlight={question.type === "debug" ? [50, 54] : [46, 54]}
            commit={question.target.commit}
          />
          <div className="recall-metadata" aria-label="Function metadata">
            <span className="chip">complexity {target.complexity}</span>
            <span className="chip">no test coverage</span>
            <span className="chip">author ratio {target.author_ratio.toFixed(2)}</span>
            <span className="chip">modified {target.times_modified} times</span>
          </div>
        </motion.section>

        <motion.section className="recall-flow" variants={item}>
          <div className="question-tabs" role="tablist" aria-label="Question types">
            {TYPES.map((type, tabIndex) => {
              const active = tabIndex === index;
              return (
                <button
                  key={type}
                  ref={(node) => { tabRefs.current[tabIndex] = node; }}
                  id={`recall-tab-${type}`}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  aria-controls="recall-question-panel"
                  tabIndex={active ? 0 : -1}
                  onKeyDown={(event) => handleTabKeyDown(event, tabIndex)}
                  onClick={() => goTo(tabIndex)}
                >
                  {active && <motion.span layoutId="question-tab-pill" transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 330, damping: 31 }} />}
                  <strong>{type}</strong>
                </button>
              );
            })}
          </div>

          <AnimatePresence mode="popLayout" initial={false} custom={direction}>
            <motion.div
              key={question.id}
              className="recall-card-wrap"
              id="recall-question-panel"
              role="tabpanel"
              aria-labelledby={`recall-tab-${question.type}`}
              custom={direction}
              initial={reduceMotion ? false : { opacity: 0, x: direction > 0 ? 64 : -64 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, x: direction > 0 ? -64 : 64 }}
              transition={{ duration: reduceMotion ? 0 : .5, ease: [.77,0,.18,1] }}
            >
              <span className="recall-count">{index + 1} of {questions.length}</span>
              <QuestionCard
                question={question}
                onSubmit={(submission) => submitAnswer({ question_id: question.id, submission })}
                answer={answers[question.id] ?? ""}
                result={results[question.id]}
                onAnswerChange={(answer) => setAnswers((current) => ({ ...current, [question.id]: answer }))}
                onResult={(result) => setResults((current) => ({ ...current, [question.id]: result }))}
              />
            </motion.div>
          </AnimatePresence>

          <div className="recall-navigation">
            <div>
              <button type="button" className="secondary-button" disabled={index === 0} onClick={() => goTo(index - 1)}>Previous</button>
              <button type="button" className="secondary-button" disabled={index === questions.length - 1} onClick={() => goTo(index + 1)}>Next</button>
            </div>
            <div className="recall-progress">
              <span>{answeredCount} of {questions.length} checked</span>
              <div className="progress-dots" aria-label={`Question ${index + 1} of ${questions.length}`}>
                {questions.map((itemQuestion, dotIndex) => (
                  <button
                    key={itemQuestion.id}
                    type="button"
                    aria-label={`Go to question ${dotIndex + 1}${results[itemQuestion.id] ? ", answered" : ""}`}
                    className={`${dotIndex === index ? "active" : ""}${results[itemQuestion.id] ? " answered" : ""}`}
                    onClick={() => goTo(dotIndex)}
                  />
                ))}
              </div>
            </div>
          </div>
          <AnimatePresence>
            {completed && (
              <motion.section className="recall-complete" role="status" initial={reduceMotion ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
                <div><strong>Revision complete</strong><p>You checked all five perspectives. Your answers stay available while you review this session.</p></div>
                <button type="button" className="secondary-button" onClick={() => goTo(0)}>Review from the start</button>
              </motion.section>
            )}
          </AnimatePresence>
        </motion.section>
      </div>
    </motion.main>
  );
}
