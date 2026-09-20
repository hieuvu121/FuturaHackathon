import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ArrowRightIcon, CheckIcon } from "@/components/Icons";
import { ApiError, getPortfolio, getRepos, getStatus, loginUrl, startAnalysis } from "@/lib/data";
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
const REPOS_PER_PAGE = 6;

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
  const [needsLogin, setNeedsLogin] = useState(false);
  const [page, setPage] = useState(0);
  // Set when a run stops short, so the page can offer to run it again instead of
  // sitting on "Analysing your work" with nothing behind it.
  const [failed, setFailed] = useState(false);
  // The pop-up shown when a run finishes WHILE the user is watching it.
  const [finished, setFinished] = useState(false);

  const loadRepositories = useCallback(async () => {
    try {
      const [repoData, portfolio] = await Promise.all([getRepos(), getPortfolio()]);
      setRepos(repoData);
      const restored = new Set(portfolio.repositories.map((repo) => repo.id));
      setSelected(restored);
      if (portfolio.repositories.some((repo) => !["done", "not_started"].includes(repo.stage))) {
        const average = portfolio.repositories.reduce((sum, repo) => sum + repo.progress, 0) / portfolio.repositories.length;
        setCurrentStep(Math.min(PIPELINE.length - 1, Math.floor((average / 100) * PIPELINE.length)));
        setPanel("pipeline");
      }
      setNeedsLogin(false);
    } catch (error: unknown) {
      setNeedsLogin(error instanceof ApiError && error.status === 401);
      setLoadError(error instanceof Error ? error.message : "Could not load repositories.");
    } finally {
      setReposLoaded(true);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadRepositories(), 0);
    return () => window.clearTimeout(timer);
  }, [loadRepositories]);

  useEffect(() => {
    if (panel !== "pipeline" || selected.size === 0) return;
    let cancelled = false;
    async function poll() {
      try {
        const statuses = await Promise.all([...selected].map(getStatus));
        if (cancelled) return;
        const stopped = statuses.find((status) => status.stage === "failed");
        if (stopped) {
          setLoadError(stopped.error || "Repository analysis failed.");
          setFailed(true);
          return;
        }
        const allDone = statuses.every((status) => status.done);
        if (allDone) setFinished(true);
        const average = statuses.reduce((sum, status) => sum + status.progress, 0) / statuses.length;
        setCurrentStep(allDone ? PIPELINE.length : Math.min(PIPELINE.length - 1, Math.floor((average / 100) * PIPELINE.length)));
        if (!allDone) window.setTimeout(() => { if (!cancelled) void poll(); }, 900);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : "Analysis status could not be loaded.");
      }
    }
    void poll();
    return () => { cancelled = true; };
  }, [panel, selected]);

  const selectedCount = selected.size;
  const pageCount = Math.max(1, Math.ceil(repos.length / REPOS_PER_PAGE));
  const visibleRepos = repos.slice(page * REPOS_PER_PAGE, (page + 1) * REPOS_PER_PAGE);
  const statusHint = useMemo(() => {
    if (selectedCount < 3) return `Pick ${3 - selectedCount} more to continue`;
    if (selectedCount === 5) return "Maximum reached";
    return "Ready to analyse";
  }, [selectedCount]);

  function toggleRepo(repo: Repo) {
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
    setNeedsLogin(false);
    void loadRepositories();
  }

  async function analyse() {
    if (selectedCount < 3) return;
    setLoadError("");
    setFailed(false);
    setFinished(false);
    setDirection(1);
    setCurrentStep(0);
    setPanel("pipeline");
    try {
      await startAnalysis([...selected]);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Analysis could not be started.");
      setPanel("select");
    }
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

      {loadError && !needsLogin && <div className="error-state" role="alert">{loadError}</div>}

      {needsLogin && (
        <section className="empty-state surface reconnect" role="alert" data-testid="reconnect-github">
          <h2>Connect GitHub to continue</h2>
          <p>{loadError || "Your repositories are listed from GitHub, so you need to be signed in there."}</p>
          <div className="question-actions empty-actions">
            <a className="primary-button" href={loginUrl} data-testid="reconnect-button">Connect GitHub <ArrowRightIcon width="19" height="19" /></a>
            <button type="button" className="ghost-button" onClick={() => void router.push("/start")}>I have no repositories</button>
          </div>
        </section>
      )}

      {!needsLogin && (
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
                {!reposLoaded && [1, 2, 3, 4, 5, 6].map((itemIndex) => <div key={itemIndex} className="repo-card repo-skeleton" aria-hidden="true" />)}
                {reposLoaded && repos.length === 0 && (
                  <section className="empty-state repo-empty surface">
                    <h2>No repositories found</h2>
                    <p>Reconnect GitHub or refresh after granting access to the repositories you want to analyse.</p>
                    <button type="button" className="secondary-button" onClick={retryRepositories}>Refresh repositories</button>
                  </section>
                )}
                {reposLoaded && visibleRepos.map((repo) => {
                  const isSelected = selected.has(repo.id);
                  const disabled = false;
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
                          {[repo.language ?? "Unknown language", repo.is_fork ? "fork" : null, repo.stars != null ? `${repo.stars} stars` : null, repo.pushed_at ? `updated ${new Date(repo.pushed_at).toLocaleDateString()}` : repo.pushed_label].filter(Boolean).join(" · ")}
                        </small>
                      </span>
                    </button>
                  );
                })}
                {reposLoaded && repos.length > REPOS_PER_PAGE && (
                  <nav className="repo-pagination" aria-label="Repository pages">
                    <button type="button" className="secondary-button" disabled={page === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}>Previous</button>
                    <span>Page {page + 1} of {pageCount}</span>
                    <button type="button" className="secondary-button" disabled={page + 1 >= pageCount} onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}>Next</button>
                  </nav>
                )}
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
                <h2>
                  {failed ? "Analysis stopped" : currentStep >= PIPELINE.length ? "Analysis complete" : "Analysing your work"}
                </h2>
                <div className="pipeline-progress"><motion.span animate={{ scaleX: Math.max(0.03, currentStep / PIPELINE.length) }} /></div>
                <p>Ingest is deterministic: tree-sitter and git only. The model joins at the scan step, and every finding must point at a valid file and line range.</p>
                <div className="pipeline-actions">
                  <button type="button" className="secondary-button" onClick={goBack}>Back</button>
                  {failed && (
                    <button type="button" className="primary-button" data-testid="retry-analysis" onClick={() => void analyse()}>
                      Run it again <ArrowRightIcon width="19" height="19" />
                    </button>
                  )}
                  {!failed && currentStep >= PIPELINE.length && (
                    <button type="button" className="primary-button" onClick={() => void router.push("/recall")}>Start recall <ArrowRightIcon width="19" height="19" /></button>
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
                      <small>{done ? "Done" : running ? (failed ? "Stopped" : "Running") : "Waiting"}</small>
                    </li>
                  );
                })}
              </ol>
            </motion.section>
          )}
        </AnimatePresence>
      </motion.div>
      )}
      {finished && (
        <div className="modal-backdrop" data-testid="analysis-complete">
          <motion.section
            className="modal-card surface"
            role="dialog"
            aria-modal="true"
            aria-labelledby="analysis-complete-title"
            initial={reduceMotion ? false : { opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: reduceMotion ? 0 : 0.28, ease: [0.2, 0.8, 0.2, 1] }}
          >
            <span className="modal-badge" aria-hidden="true"><CheckIcon width="24" height="24" /></span>
            <p className="eyebrow">Connect</p>
            <h2 id="analysis-complete-title">Analysis complete</h2>
            <p>
              Your {selectedCount} repositories have been read and scored. Next, five short questions
              check what you actually understand, and your roadmap is built from both.
            </p>
            <button
              type="button"
              className="primary-button"
              data-testid="go-to-recall"
              autoFocus
              onClick={() => void router.push("/recall")}
            >
              Start recall <ArrowRightIcon width="19" height="19" />
            </button>
            <button type="button" className="ghost-button" onClick={() => setFinished(false)}>Stay here</button>
          </motion.section>
        </div>
      )}
    </motion.main>
  );
}
