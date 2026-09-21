import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CheckIcon } from "@/components/Icons";
import PageSkeleton from "@/components/PageSkeleton";
import {
  ApiError, commentOnRoadmap, deleteCommunityRoadmap, getCommunityRoadmap, getCommunityRoadmaps, shareRoadmap,
} from "@/lib/data";
import type { CommunityRoadmap, CommunityRoadmapDetail, CommunityStanding, CommunityVerdict } from "@/lib/types";

const STANDING_LABEL: Record<CommunityStanding, string> = {
  mentor: "Mentor",
  experienced: "Experienced",
  member: "Member",
};

const VERDICTS: { id: CommunityVerdict; label: string; note: string }[] = [
  { id: "validates", label: "Validate", note: "This roadmap is right for that role" },
  { id: "suggests", label: "Suggest a change", note: "Something should move, go, or be added" },
  { id: "comment", label: "Just comment", note: "A question or a reply" },
];

const VERDICT_TAG: Record<CommunityVerdict, string> = {
  validates: "Validates",
  suggests: "Suggests a change",
  comment: "",
};

function StandingBadge({ standing }: { standing: CommunityStanding }) {
  return <span className={`standing standing-${standing}`}>{STANDING_LABEL[standing]}</span>;
}

/** Validation only counts reviews from mentors and experienced users, and says so. */
function ValidationLine({ roadmap }: { roadmap: CommunityRoadmap }) {
  if (roadmap.validations === 0 && roadmap.suggestions === 0) {
    return <span className="validation waiting">Awaiting review</span>;
  }
  return (
    <span className="validation">
      {roadmap.validations > 0 && (
        <span className="validation-ok"><CheckIcon width="11" height="11" /> Validated by {roadmap.validations}</span>
      )}
      {roadmap.suggestions > 0 && (
        <span className="validation-change">{roadmap.suggestions} suggested change{roadmap.suggestions === 1 ? "" : "s"}</span>
      )}
    </span>
  );
}

/** The shared roadmap, drawn small: the steps in order, each concept with its bar. */
function MiniRoadmap({ roadmap }: { roadmap: CommunityRoadmap }) {
  return (
    <ol className="mini-roadmap" aria-label={`Roadmap for ${roadmap.title}`}>
      {roadmap.stages.map((stage, index) => (
        <li key={`${stage.title}-${index}`}>
          <span className="flow-label"><b>{index + 1}</b>{stage.title}</span>
          <ul>
            {stage.concepts.map((concept) => (
              <li key={concept.name}>
                <span>{concept.name}</span>
                <span className="mini-bar" role="img" aria-label={`${Math.round(concept.mastery * 100)}% mastered`}>
                  <i style={{ transform: `scaleX(${concept.mastery})` }} />
                </span>
                <b>{Math.round(concept.mastery * 100)}%</b>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function when(value: string | null) {
  return value ? new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
}

export default function CommunityPage() {
  const reduceMotion = useReducedMotion();
  const [roadmaps, setRoadmaps] = useState<CommunityRoadmap[]>([]);
  const [open, setOpen] = useState<CommunityRoadmapDetail | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [body, setBody] = useState("");
  const [verdict, setVerdict] = useState<CommunityVerdict>("validates");

  const refresh = useCallback(async () => {
    setRoadmaps(await getCommunityRoadmaps());
  }, []);

  useEffect(() => {
    let active = true;
    getCommunityRoadmaps()
      .then((found) => active && setRoadmaps(found))
      .catch((cause: unknown) => active && setError(cause instanceof Error ? cause.message : "The community could not be loaded."))
      .finally(() => active && setLoaded(true));
    return () => {
      active = false;
    };
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (cause: unknown) {
      setError(
        cause instanceof ApiError && cause.status === 409
          ? "You do not have a roadmap to share yet. Finish the recall evaluation first."
          : cause instanceof Error ? cause.message : "That could not be saved."
      );
    } finally {
      setBusy(false);
    }
  }

  const view = (id: number) => run(async () => {
    const detail = await getCommunityRoadmap(id);
    setOpen(detail);
    setBody("");
    // Your own roadmap cannot be validated by you, so the form starts on "comment".
    setVerdict(detail.mine ? "comment" : "validates");
  });

  const share = (event: React.FormEvent) => {
    event.preventDefault();
    return run(async () => {
      const created = await shareRoadmap(title.trim(), summary.trim());
      setTitle("");
      setSummary("");
      setSharing(false);
      setOpen(created);
      setVerdict("comment");
      await refresh();
    });
  };

  const post = (event: React.FormEvent) => {
    event.preventDefault();
    if (!open) return Promise.resolve();
    return run(async () => {
      setOpen(await commentOnRoadmap(open.id, body.trim(), verdict));
      setBody("");
      await refresh();
    });
  };

  const remove = () => open && run(async () => {
    await deleteCommunityRoadmap(open.id);
    setOpen(null);
    await refresh();
  });

  if (!loaded) return <PageSkeleton label="Loading the community" />;

  return (
    <motion.main
      className="page community-page"
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.4, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <header className="page-header">
        <p className="eyebrow">Community</p>
        <h1 className="page-title">Is this the right roadmap for the role?</h1>
        <p className="page-copy">
          Share your roadmap under the role you are aiming for. Anyone can comment, but only reviews
          from mentors and experienced users count towards validating it.
        </p>
      </header>

      {error && <div className="error-state" role="alert">{error}</div>}

      {open ? (
        <section className="community-detail surface" data-testid="community-detail">
          <button type="button" className="detail-back" onClick={() => setOpen(null)}>← All roadmaps</button>
          <header className="community-detail-head">
            <div>
              <h2>{open.title}</h2>
              <p className="community-byline">
                @{open.author} <StandingBadge standing={open.author_standing} />
                {open.is_sample && <span className="sample-tag">Sample</span>}
                <span>{when(open.created_at)}</span>
              </p>
            </div>
            <div className="community-score">
              <b>{Math.round(open.overall * 100)}%</b>
              <span>overall</span>
            </div>
          </header>
          {open.summary && <p className="community-summary">{open.summary}</p>}
          <ValidationLine roadmap={open} />
          <MiniRoadmap roadmap={open} />

          <h3 className="community-subhead">Reviews <small>{open.comment_count}</small></h3>
          {open.comments.length === 0 && <p className="community-empty">No reviews yet. Be the first.</p>}
          <ul className="review-list">
            {open.comments.map((comment) => (
              <li key={comment.id} className={`review review-${comment.verdict}`} data-testid="community-comment">
                <p className="review-head">
                  <strong>@{comment.author}</strong>
                  <StandingBadge standing={comment.standing} />
                  {VERDICT_TAG[comment.verdict] && <span className={`verdict-tag verdict-${comment.verdict}`}>{VERDICT_TAG[comment.verdict]}</span>}
                  <span className="review-date">{when(comment.created_at)}</span>
                </p>
                <p>{comment.body}</p>
              </li>
            ))}
          </ul>

          <form className="review-form" onSubmit={(event) => void post(event)}>
            <p className="review-as">
              You are reviewing as <StandingBadge standing={open.my_standing} />
              {open.my_standing === "member" && " — your comment is welcome, but only mentors and experienced users move the validated count."}
            </p>
            {!open.mine && (
              <div className="verdict-picker" role="radiogroup" aria-label="What is your review?">
                {VERDICTS.map((option) => (
                  <label key={option.id} className={`verdict-option${verdict === option.id ? " picked" : ""}`}>
                    <input type="radio" name="verdict" checked={verdict === option.id} onChange={() => setVerdict(option.id)} />
                    <strong>{option.label}</strong>
                    <span>{option.note}</span>
                  </label>
                ))}
              </div>
            )}
            <label htmlFor="review-body" className="sr-only">Your review</label>
            <textarea
              id="review-body"
              data-testid="community-body"
              value={body}
              maxLength={1200}
              onChange={(event) => setBody(event.target.value)}
              placeholder={open.mine ? "Reply to your reviewers…" : "What is right about this roadmap, or what would you change, and why?"}
            />
            <div className="question-actions">
              <button type="submit" className="primary-button" data-testid="community-post" disabled={body.trim().length < 2 || busy}>
                {busy ? "Posting…" : "Post review"}
              </button>
              {open.mine && (
                <button type="button" className="ghost-button" disabled={busy} onClick={() => void remove()}>Take this roadmap down</button>
              )}
            </div>
          </form>
        </section>
      ) : (
        <>
          {sharing ? (
            <form className="share-form surface" onSubmit={(event) => void share(event)}>
              <h2>Share your roadmap</h2>
              <p>A snapshot of your roadmap is shared: the steps, the concepts and how far along you are. Your code and the scanner findings are never included.</p>
              <label htmlFor="share-title">The role you are aiming for</label>
              <input
                id="share-title"
                data-testid="share-title"
                value={title}
                maxLength={80}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="e.g. Backend engineer (junior)"
                required
              />
              <label htmlFor="share-summary">What do you want reviewers to look at? <span>(optional)</span></label>
              <textarea id="share-summary" value={summary} maxLength={600} onChange={(event) => setSummary(event.target.value)} placeholder="Your background, and the question you most want answered." />
              <div className="question-actions">
                <button type="submit" className="primary-button" data-testid="share-submit" disabled={title.trim().length < 3 || busy}>
                  {busy ? "Sharing…" : "Share for review"}
                </button>
                <button type="button" className="ghost-button" onClick={() => setSharing(false)}>Cancel</button>
              </div>
            </form>
          ) : (
            <div className="community-actions">
              <button type="button" className="primary-button" data-testid="share-open" onClick={() => setSharing(true)}>Share my roadmap</button>
              <Link className="ghost-button" href="/roadmap">See my roadmap</Link>
            </div>
          )}

          <ul className="community-list">
            {roadmaps.map((roadmap) => (
              <li key={roadmap.id}>
                <button type="button" className="community-card surface interactive-card" data-testid="community-card" onClick={() => void view(roadmap.id)}>
                  <span className="community-card-head">
                    <strong>{roadmap.title}</strong>
                    <b>{Math.round(roadmap.overall * 100)}%</b>
                  </span>
                  <span className="community-byline">
                    @{roadmap.author} <StandingBadge standing={roadmap.author_standing} />
                    {roadmap.is_sample && <span className="sample-tag">Sample</span>}
                    {roadmap.mine && <span className="sample-tag mine">Yours</span>}
                  </span>
                  {roadmap.summary && <span className="community-card-summary">{roadmap.summary}</span>}
                  <span className="community-card-foot">
                    <ValidationLine roadmap={roadmap} />
                    <span>{roadmap.stages.length} steps · {roadmap.comment_count} review{roadmap.comment_count === 1 ? "" : "s"}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {roadmaps.length === 0 && <div className="empty-bucket"><strong>Nothing shared yet</strong><span>Be the first to share a roadmap.</span></div>}
        </>
      )}
    </motion.main>
  );
}
