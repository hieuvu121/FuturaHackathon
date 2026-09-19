import { useEffect, useState } from "react";

import { CheckIcon, ExternalIcon } from "@/components/Icons";
import { getCapstone, submitCapstone } from "@/lib/data";
import type { CapstoneState, RequirementVerdict } from "@/lib/types";

const VERDICT_LABEL: Record<RequirementVerdict, string> = {
  met: "Met",
  partial: "Partly",
  missing: "Not yet",
};

const POLL_MS = 3000;

/**
 * The roadmap's last stop: build one project, submit the repository, read the review.
 *
 * The brief comes from the user's own roadmap, so it is there at once. A review
 * takes a clone and a model call, so submitting returns immediately and this
 * polls until the status leaves `reviewing`.
 */
export default function CapstonePanel() {
  const [state, setState] = useState<CapstoneState | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [resubmitting, setResubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    getCapstone()
      .then((next) => active && setState(next))
      .catch((cause: unknown) =>
        active && setError(cause instanceof Error ? cause.message : "The final project could not be loaded.")
      );
    return () => {
      active = false;
    };
  }, []);

  const status = state?.submission?.status;
  useEffect(() => {
    if (status !== "reviewing") return;
    let active = true;
    const timer = window.setInterval(() => {
      getCapstone()
        .then((next) => active && setState(next))
        .catch(() => undefined); // A missed poll is retried by the next tick.
    }, POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [status]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!repoUrl.trim() || sending) return;
    setSending(true);
    setError("");
    try {
      setState(await submitCapstone(repoUrl.trim(), notes.trim()));
      setResubmitting(false);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "That could not be submitted.");
    } finally {
      setSending(false);
    }
  }

  if (!state) {
    return error ? (
      <div className="error-state" role="alert">{error}</div>
    ) : (
      <div className="capstone-loading" aria-busy="true">Preparing your final project…</div>
    );
  }

  const { brief, submission } = state;
  const review = submission?.status === "reviewed" ? submission.review : null;
  const verdicts = new Map(review?.requirements.map((row) => [row.requirement_id, row]));
  const showForm = !submission || resubmitting || submission.status === "failed";

  return (
    <div className="capstone" data-testid="capstone-panel">
      <header className="capstone-brief">
        <h3>{brief.title}</h3>
        <p>{brief.summary}</p>
        <p className={`capstone-readiness${brief.ready ? " ready" : ""}`}>{brief.readiness_note}</p>
      </header>

      <div className="capstone-columns">
        <section>
          <h4>What it has to show</h4>
          <ul className="capstone-requirements">
            {brief.requirements.map((requirement) => {
              const verdict = verdicts.get(requirement.id);
              return (
                <li
                  key={requirement.id}
                  className={verdict ? `verdict-${verdict.verdict}` : undefined}
                  data-testid="capstone-requirement"
                >
                  <div className="requirement-head">
                    {requirement.skill_name ? (
                      <span className="requirement-skill">{requirement.skill_name}</span>
                    ) : (
                      <span className="requirement-skill baseline">Baseline</span>
                    )}
                    {verdict && (
                      <span className={`verdict-chip verdict-${verdict.verdict}`}>
                        {verdict.verdict === "met" && <CheckIcon width="10" height="10" />}
                        {VERDICT_LABEL[verdict.verdict]}
                      </span>
                    )}
                  </div>
                  <p>{requirement.text}</p>
                  {verdict && (
                    <p className="requirement-comment">
                      {verdict.comment}
                      {verdict.files.length > 0 && (
                        <span className="requirement-files"> {verdict.files.join(" · ")}</span>
                      )}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>

        <section>
          <h4>What to hand in</h4>
          <ul className="capstone-deliverables">
            {brief.deliverables.map((item) => <li key={item}>{item}</li>)}
          </ul>

          {submission?.status === "reviewing" && (
            <div className="capstone-status" role="status" data-testid="capstone-reviewing">
              <span className="capstone-spinner" aria-hidden="true" />
              <div>
                <strong>Reviewing your repository</strong>
                <p>Reading {submission.repo_url.replace("https://github.com/", "")} against the brief. This takes about a minute.</p>
              </div>
            </div>
          )}

          {submission?.status === "failed" && (
            <div className="error-state" role="alert">{submission.error ?? "The review failed."}</div>
          )}

          {review && submission && (
            <div className="capstone-review" data-testid="capstone-review">
              <div className="review-score">
                <b>{Math.round(review.score * 100)}%</b>
                <span>of the brief met{review.sample ? " · sample review" : ` · ${review.files_reviewed} files read`}</span>
              </div>
              <p>{review.summary}</p>
              {review.strengths.length > 0 && (
                <>
                  <h5>What works</h5>
                  <ul>{review.strengths.map((item) => <li key={item}>{item}</li>)}</ul>
                </>
              )}
              {review.improvements.length > 0 && (
                <>
                  <h5>What to improve next</h5>
                  <ul>{review.improvements.map((item) => <li key={item}>{item}</li>)}</ul>
                </>
              )}
              <div className="question-actions">
                <a className="resource-link" href={submission.repo_url} target="_blank" rel="noopener noreferrer">
                  {submission.repo_url.replace("https://github.com/", "")}
                  <ExternalIcon width="12" height="12" />
                </a>
                {!resubmitting && (
                  <button type="button" className="ghost-button" onClick={() => setResubmitting(true)}>
                    Submit a new version
                  </button>
                )}
              </div>
            </div>
          )}

          {showForm && (
            <form className="capstone-form" onSubmit={(event) => void submit(event)}>
              <label htmlFor="capstone-repo">GitHub repository</label>
              <input
                id="capstone-repo"
                data-testid="capstone-repo"
                type="url"
                inputMode="url"
                placeholder="https://github.com/you/your-project"
                value={repoUrl}
                onChange={(event) => setRepoUrl(event.target.value)}
                required
              />
              <label htmlFor="capstone-notes">Anything the reviewer should know <span>(optional)</span></label>
              <textarea
                id="capstone-notes"
                value={notes}
                maxLength={2000}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Trade-offs you made, what you would do with more time…"
              />
              {error && <div className="error-state" role="alert">{error}</div>}
              <div className="question-actions">
                <button
                  type="submit"
                  className="primary-button"
                  data-testid="capstone-submit"
                  disabled={!repoUrl.trim() || sending}
                >
                  {sending ? "Submitting…" : "Submit for AI review"}
                </button>
                <span>Reviewed against the brief above, with files cited.</span>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
