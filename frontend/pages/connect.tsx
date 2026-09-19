import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";

import { ArrowRightIcon, CheckIcon } from "@/components/Icons";
import { getRepos, getStatus, startAnalysis } from "@/lib/data";
import type { Repo } from "@/lib/types";

const PIPELINE = [
  ["Shallow clone", "INGEST"],
  ["Filter vendor and generated files", "INGEST"],
  ["Parse with tree-sitter", "INGEST"],
  ["Compute complexity and call graph", "INGEST"],
  ["Read git log and blame", "INGEST"],
  ["Rank files by complexity x churn x size", "ANALYZE"],
  ["Scan top files", "ANALYZE"],
  ["Validate findings against file:lines", "ANALYZE"],
  ["Score six dimensions", "ANALYZE"],
] as const;

const languageClass: Record<string, string> = {
  Python: "language-python", TypeScript: "language-typescript", Go: "language-go", Jupyter: "language-jupyter",
};

export default function ConnectPage() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [panel, setPanel] = useState<"select" | "pipeline">("select");
  const [direction, setDirection] = useState(1);
  const [currentStep, setCurrentStep] = useState(-1);
  const [loadError, setLoadError] = useState("");
  const [reposLoaded, setReposLoaded] = useState(false);
  const [selectionNotice, setSelectionNotice] = useState("");

  useEffect(() => {
    getRepos()
      .then((data) => { setRepos(data); setReposLoaded(true); })
      .catch((error: unknown) => { setLoadError(error instanceof Error ? error.message : "Could not load repositories."); setReposLoaded(true); });
  }, []);

  useEffect(() => {
    if (panel !== "pipeline" || currentStep >= PIPELINE.length) return;
    let cancelled = false;
    async function poll() {
      try {
        const status = await getStatus("orders-api");
        if (cancelled) return;
        setCurrentStep(status.done ? PIPELINE.length : status.step);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : "Analysis status could not be loaded.");
      }
    }
    void poll();
    return () => { cancelled = true; };
  }, [currentStep, panel]);

  const selectedCount = selected.size;
  const statusHint = useMemo(() => {
    if (selectedCount < 3) return `Pick ${3 - selectedCount} more to continue`;
    if (selectedCount === 5) return "Maximum reached";
    return "Ready to analyse";
  }, [selectedCount]);

  function toggleRepo(repo: Repo) {
    if (repo.is_fork && !repo.has_original_commits) return;
    const next = new Set(selected);
    if (next.has(repo.id)) {
      next.delete(repo.id);
      setSelectionNotice("");
    } else if (next.size < 5) {
      next.add(repo.id);
      setSelectionNotice("");
    } else {
      setSelectionNotice("You can select up to 5 repositories. Remove one before adding another.");
      return;
    }
    setSelected(next);
  }

  function retryRepositories() {
    setLoadError("");
    setReposLoaded(false);
    getRepos()
      .then((data) => { setRepos(data); setReposLoaded(true); })
      .catch((error: unknown) => { setLoadError(error instanceof Error ? error.message : "Could not load repositories."); setReposLoaded(true); });
  }

  async function analyse() {
    if (selectedCount < 3) return;
    setLoadError("");
    await startAnalysis([...selected]);
    setDirection(1);
    setCurrentStep(-1);
    setPanel("pipeline");
  }

  function goBack() {
    setDirection(-1);
    setPanel("select");
  }

  const enter = { hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } };
  const item = { hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : .5, ease: [.2, .8, .2, 1] as const } } };

  return (
    <motion.main className="page connect-page" variants={enter} initial="hidden" animate="show">
      <motion.header className="page-header" variants={item}>
        <p className="eyebrow">Connect</p>
        <h1 className="page-title">Pick the repos that show <span className="gradient-text">your real work.</span></h1>
        <p className="page-copy">Choose 3 to 5. Dependencies, generated code, build output, and forks with no original commits are filtered out before anything is scored.</p>
      </motion.header>

      {loadError && <div className="error-state" role="alert">{loadError}</div>}

      <motion.div variants={item}>
        <AnimatePresence mode="popLayout" initial={false} custom={direction}>
          {panel === "select" ? (
            <motion.section
              key="selection"
              className="connect-layout"
              custom={direction}
              initial={reduceMotion ? false : { opacity: 0, x: direction > 0 ? 70 : -70 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, x: -70 }}
              transition={{ duration: reduceMotion ? 0 : .5, ease: [.77, 0, .18, 1] }}
            >
              <div className="repo-grid">
                {!reposLoaded && [1, 2, 3, 4].map((itemIndex) => <div key={itemIndex} className="repo-card repo-skeleton" aria-hidden="true" />)}
                {reposLoaded && repos.length === 0 && (
                  <section className="empty-state repo-empty surface">
                    <h2>No repositories found</h2>
                    <p>Reconnect GitHub or refresh after granting access to the repositories you want to analyse.</p>
                    <button type="button" className="secondary-button" onClick={retryRepositories}>Refresh repositories</button>
                  </section>
                )}
                {reposLoaded && repos.map((repo) => {
                  const isSelected = selected.has(repo.id);
                  const disabled = repo.is_fork && !repo.has_original_commits;
                  return (
                    <button
                      key={repo.id}
                      type="button"
                      className={`repo-card interactive-card${isSelected ? " selected" : ""}`}
                      aria-pressed={isSelected}
                      disabled={disabled}
                      onClick={() => toggleRepo(repo)}
                    >
                      <span className="repo-toggle">{isSelected && <CheckIcon width="15" height="15" />}</span>
                      <span className="repo-details">
                        <strong>{repo.full_name.split("/")[1]}</strong>
                        <small>
                          <i className={languageClass[repo.language ?? ""]} aria-hidden="true" />
                          {disabled ? "Fork with no original commits, excluded" : `${repo.language} · ${repo.function_count} functions · ${repo.pushed_label}`}
                        </small>
                      </span>
                    </button>
                  );
                })}
              </div>
              <aside className="selection-summary surface">
                <div><strong>{selectedCount}</strong><span>of 5 selected</span></div>
                <div className="selection-progress" aria-label={`${selectedCount} of 5 selected`}><motion.span animate={{ scaleX: selectedCount / 5 }} transition={{ duration: reduceMotion ? 0 : .45, ease: [.2,.8,.2,1] }} /></div>
                <h2 role="status" aria-live="polite">{selectionNotice || statusHint}</h2>
                <p>Excluded automatically: node_modules, vendor, venv, build output, lock and minified files. You will see the full exclusion list after ingest.</p>
                <button type="button" className="primary-button" disabled={selectedCount < 3} onClick={() => void analyse()}>
                  Analyse repositories <ArrowRightIcon width="20" height="20" />
                </button>
              </aside>
            </motion.section>
          ) : (
            <motion.section
              key="pipeline"
              className="pipeline-layout"
              custom={direction}
              initial={reduceMotion ? false : { opacity: 0, x: direction > 0 ? 70 : -70 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduceMotion ? undefined : { opacity: 0, x: 70 }}
              transition={{ duration: reduceMotion ? 0 : .5, ease: [.77, 0, .18, 1] }}
            >
              <aside className="pipeline-summary surface">
                <h2>{currentStep >= PIPELINE.length ? "Analysis complete" : "Analysing your work"}</h2>
                <div className="pipeline-progress"><motion.span animate={{ scaleX: Math.max(0.03, currentStep / PIPELINE.length) }} /></div>
                <p>Ingest is deterministic: tree-sitter and git only. The model joins at the scan step, and every finding must point at a valid file and line range.</p>
                <div className="pipeline-actions">
                  <button type="button" className="secondary-button" onClick={goBack}>Back</button>
                  {currentStep >= PIPELINE.length && (
                    <button type="button" className="primary-button" onClick={() => void router.push("/profile")}>Open profile <ArrowRightIcon width="19" height="19" /></button>
                  )}
                </div>
              </aside>
              <ol className="pipeline-steps surface">
                {PIPELINE.map(([label, stage], index) => {
                  const done = index < currentStep || currentStep >= PIPELINE.length;
                  const running = index === currentStep && currentStep < PIPELINE.length;
                  return (
                    <li key={label} className={running ? "running" : ""}>
                      <span className={done ? "step-dot done" : running ? "step-dot running" : "step-dot"}>{done && <CheckIcon width="13" height="13" />}</span>
                      <strong>{label}</strong>
                      <em>{stage}</em>
                      <small>{done ? "Done" : running ? "Running" : "Waiting"}</small>
                    </li>
                  );
                })}
              </ol>
            </motion.section>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.main>
  );
}
