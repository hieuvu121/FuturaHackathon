import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useCallback, useEffect, useRef, useState } from "react";

import EvidenceLink from "@/components/EvidenceLink";
import { CheckIcon, ExternalIcon, InfoIcon } from "@/components/Icons";
import SourceBadge from "@/components/SourceBadge";
import {
  ApiError, acceptRoadmap, getRoadmapGraph, getRoadmapReview, redoRecall, tailorRoadmap,
} from "@/lib/data";
import type {
  ConceptSkill, NodeStatus, RoadmapConcept, RoadmapGraph, RoadmapReview, RoadmapStage,
} from "@/lib/types";

const ROLE = { id: "software_engineer", label: "Software engineer" } as const;

const RESOURCE_KIND: Record<string, string> = {
  docs: "Docs",
  guide: "Guide",
  course: "Course",
  practice: "Practice",
  reference: "Reference",
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  verified: "Verified",
  familiar: "Basics",
  new: "New",
};

/** What is selected in the diagram: a concept, or one topic inside it. */
type Selection =
  | { kind: "concept"; conceptId: string }
  | { kind: "skill"; conceptId: string; skillId: string }
  | null;

function StatusMark({ status }: { status: NodeStatus }) {
  return (
    <span className={`status-mark status-${status}`} aria-hidden="true">
      {status === "new" ? null : <CheckIcon width="10" height="10" />}
    </span>
  );
}

/** The progress bar every node carries: how far along this user is, 0–100%. */
function MasteryBar({
  mastery,
  status,
  reduceMotion,
  label,
}: {
  mastery: number;
  status?: NodeStatus;
  reduceMotion: boolean | null;
  label: string;
}) {
  const percent = Math.round(mastery * 100);
  return (
    <div className="mastery" role="img" aria-label={`${label}: ${percent}% mastered`}>
      <span className={`mastery-track${status ? ` mastery-${status}` : ""}`}>
        <motion.i
          initial={reduceMotion ? false : { scaleX: 0 }}
          animate={{ scaleX: mastery }}
          transition={{ duration: reduceMotion ? 0 : 0.6, ease: [0.2, 0.8, 0.2, 1] }}
        />
      </span>
      <b>{percent}%</b>
    </div>
  );
}

/** A skill, in full: what it is for this user, what is missing, and where to study it. */
function SkillDetail({
  skill,
  siblings,
  onPick,
  reduceMotion,
}: {
  skill: ConceptSkill;
  siblings: ConceptSkill[];
  onPick: (skillId: string) => void;
  reduceMotion: boolean | null;
}) {
  // The gap the focus line names beats the skill's own evidence: it points at
  // the problem to fix, not merely at where the skill was used.
  const evidence = skill.gap_evidence ?? skill.evidence[0];
  return (
    <div className={`skill-node node-${skill.status}`} data-testid="skill-node">
      <header>
        <StatusMark status={skill.status} />
        <h4>{skill.skill_name}</h4>
        <span className="skill-status">{STATUS_LABEL[skill.status]}</span>
      </header>
      <MasteryBar mastery={skill.mastery} status={skill.status} reduceMotion={reduceMotion} label={skill.skill_name} />
      <p className="skill-focus">{skill.focus}</p>
      {skill.missing && (
        <div className="skill-missing" data-testid="skill-missing">
          <h5>What is missing</h5>
          <p>{skill.missing}</p>
        </div>
      )}
      {skill.resources.length > 0 && (
        <div className="skill-resources" data-testid="skill-resources">
          <h5>Study this</h5>
          <ul>
            {skill.resources.map((resource) => (
              <li key={resource.url}>
                <a className="resource-link" href={resource.url} target="_blank" rel="noopener noreferrer">
                  <span className="resource-kind">{RESOURCE_KIND[resource.kind] ?? resource.kind}</span>
                  <span>{resource.title}</span>
                  <ExternalIcon width="12" height="12" />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(siblings.length > 0 || skill.related_to.length > 0) && (
        <div className="skill-resources">
          <h5>Related topics</h5>
          <div className="topic-chips">
            {siblings.map((other) => (
              <button key={other.skill_id} type="button" className="topic-chip" onClick={() => onPick(other.skill_id)}>
                {other.skill_name}
              </button>
            ))}
            {skill.related_to.map((name) => <span key={name} className="topic-chip static">{name}</span>)}
          </div>
        </div>
      )}
      <footer>
        {evidence ? <EvidenceLink evidence={evidence} compact /> : <span />}
        {skill.market_frequency != null && (
          <span className="demand-chip" title="Share of sampled job ads naming this skill">
            {Math.round(skill.market_frequency * 100)}% of roles
          </span>
        )}
      </footer>
    </div>
  );
}

/** A concept, in brief: what it covers, and the topics under it with a line on each. */
function ConceptSummary({
  concept,
  stage,
  skills,
  tailoring,
  isHidden,
  onToggle,
  onPick,
  reduceMotion,
}: {
  concept: RoadmapConcept;
  stage: RoadmapStage | null;
  skills: ConceptSkill[];
  tailoring: boolean;
  isHidden: (skill: ConceptSkill) => boolean;
  onToggle: (skillId: string) => void;
  onPick: (skillId: string) => void;
  reduceMotion: boolean | null;
}) {
  return (
    <>
      <header className="detail-header">
        {stage && <p className="detail-stage">Step {stage.index} · {stage.title}</p>}
        <h2>{concept.concept_name}</h2>
        <p>{concept.summary}</p>
        <MasteryBar mastery={concept.mastery} reduceMotion={reduceMotion} label={concept.concept_name} />
        <div className="concept-counts">
          {concept.verified_count > 0 && <span className="count count-verified">{concept.verified_count} verified</span>}
          {concept.familiar_count > 0 && <span className="count count-familiar">{concept.familiar_count} basics</span>}
          {concept.new_count > 0 && <span className="count count-new">{concept.new_count} new</span>}
        </div>
      </header>
      <h5 className="detail-subhead">Topics in this branch</h5>
      <ul className="topic-list">
        {skills.map((skill) => (
          <li key={skill.skill_id} className={`topic-item${isHidden(skill) ? " removed" : ""}`}>
            <button type="button" className="topic-row" data-testid="skill-leaf" onClick={() => onPick(skill.skill_id)}>
              <StatusMark status={skill.status} />
              <span className="topic-name">{skill.skill_name}</span>
              <span className="topic-percent">{Math.round(skill.mastery * 100)}%</span>
              <span className="topic-line">{skill.focus}</span>
            </button>
            {tailoring && (
              <button
                type="button"
                className="leaf-toggle"
                data-testid="leaf-toggle"
                aria-pressed={isHidden(skill)}
                onClick={() => onToggle(skill.skill_id)}
              >
                {isHidden(skill) ? "Add back" : "Remove"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

/** Accept the roadmap, or dispute it by retesting or by editing it. */
function ReviewBar({
  review,
  tailoring,
  busy,
  hiddenCount,
  fromSurvey,
  onAccept,
  onRedo,
  onStartTailoring,
  onCancelTailoring,
  onSaveTailoring,
}: {
  review: RoadmapReview;
  tailoring: boolean;
  busy: boolean;
  hiddenCount: number;
  fromSurvey: boolean;
  onAccept: () => void;
  onRedo: () => void;
  onStartTailoring: () => void;
  onCancelTailoring: () => void;
  onSaveTailoring: () => void;
}) {
  const [disputing, setDisputing] = useState(false);

  if (tailoring) {
    return (
      <section className="review-bar tailoring" data-testid="review-bar" aria-label="Tailor your roadmap">
        <div>
          <strong>Tailoring your roadmap</strong>
          <p>
            Select a concept, then remove any topic that does not belong on your path. Removed topics
            stay listed, dimmed, so you can bring them back.
            {hiddenCount > 0 && ` ${hiddenCount} removed so far.`}
          </p>
        </div>
        <div className="review-actions">
          <button type="button" className="ghost-button" disabled={busy} onClick={onCancelTailoring}>Cancel</button>
          <button type="button" className="primary-button" data-testid="tailor-save" disabled={busy} onClick={onSaveTailoring}>
            {busy ? "Saving…" : "Save and accept"}
          </button>
        </div>
      </section>
    );
  }

  if (review.status === "accepted" && !disputing) {
    return (
      <section className="review-bar accepted" data-testid="review-bar" aria-label="Roadmap accepted">
        <div className="review-accepted">
          <span className="status-mark status-verified" aria-hidden="true"><CheckIcon width="10" height="10" /></span>
          <strong>You accepted this roadmap.</strong>
        </div>
        <button type="button" className="ghost-button" onClick={() => setDisputing(true)}>Change it</button>
      </section>
    );
  }

  return (
    <section className="review-bar" data-testid="review-bar" aria-label="Review your roadmap">
      <div>
        <strong>{disputing ? "How do you want to fix it?" : "Does this roadmap look like you?"}</strong>
        <p>
          {disputing
            ? "Sit the five recall questions again for a fresh reading, or edit the roadmap yourself."
            : `It was built from ${fromSurvey ? "your survey answers" : "your repositories"} and your ${review.recall_answered} recall answer${review.recall_answered === 1 ? "" : "s"}. Accept it, or dispute it if something is off.`}
        </p>
      </div>
      {disputing ? (
        <div className="review-actions">
          <button type="button" className="ghost-button" disabled={busy} onClick={() => setDisputing(false)}>Back</button>
          <button type="button" className="ghost-button" data-testid="review-redo" disabled={busy} onClick={onRedo}>
            Redo the recall test
          </button>
          <button
            type="button"
            className="primary-button"
            data-testid="review-tailor"
            disabled={busy}
            onClick={() => {
              setDisputing(false);
              onStartTailoring();
            }}
          >
            Tailor it myself
          </button>
        </div>
      ) : (
        <div className="review-actions">
          <button type="button" className="ghost-button" data-testid="review-dispute" disabled={busy} onClick={() => setDisputing(true)}>
            Dispute
          </button>
          <button type="button" className="primary-button" data-testid="review-accept" disabled={busy} onClick={onAccept}>
            {busy ? "Saving…" : "Accept roadmap"}
          </button>
        </div>
      )}
    </section>
  );
}

export default function RoadmapPage() {
  const reduceMotion = useReducedMotion();
  const router = useRouter();
  const [graph, setGraph] = useState<RoadmapGraph | null>(null);
  const [review, setReview] = useState<RoadmapReview | null>(null);
  const [selection, setSelection] = useState<Selection>(null);
  const [tailoring, setTailoring] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const detailRef = useRef<HTMLElement | null>(null);

  const load = useCallback(async (includeHidden: boolean, keepSelection = false) => {
    const data = await getRoadmapGraph(ROLE.id, "AU", includeHidden);
    setGraph(data);
    if (!keepSelection) {
      const first = data.concepts[0];
      setSelection(first ? { kind: "concept", conceptId: first.concept_id } : null);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function start() {
      try {
        const [, state] = await Promise.all([load(false), getRoadmapReview()]);
        if (!active) return;
        setReview(state);
        setHidden(new Set(state.hidden_skills));
        setLoading(false);
      } catch (error: unknown) {
        if (!active) return;
        // 404/409 mean the analysis has not finished yet, so keep waiting.
        if (error instanceof ApiError && [404, 409].includes(error.status)) {
          timer = window.setTimeout(start, 1800);
        } else {
          setLoadError(error instanceof Error ? error.message : "The roadmap could not be loaded.");
          setLoading(false);
        }
      }
    }
    void start();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setLoadError("");
    try {
      await action();
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "That could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const accept = () => run(async () => setReview(await acceptRoadmap()));
  const redo = () => run(async () => {
    await redoRecall();
    await router.push("/recall");
  });
  const startTailoring = () => run(async () => {
    await load(true, true);
    setTailoring(true);
  });
  const cancelTailoring = () => run(async () => {
    setHidden(new Set(review?.hidden_skills ?? []));
    await load(false, true);
    setTailoring(false);
  });
  const saveTailoring = () => run(async () => {
    await tailorRoadmap([...hidden]);
    setReview(await acceptRoadmap());
    setTailoring(false);
    await load(false);
  });

  function toggleHidden(skillId: string) {
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      return next;
    });
  }

  function select(next: Selection) {
    setSelection(next);
    // On a narrow screen the detail sits under the tree, so bring it into view.
    window.requestAnimationFrame(() =>
      detailRef.current?.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" })
    );
  }

  const isHidden = (skill: ConceptSkill) => hidden.has(skill.skill_id);
  const shownSkills = (concept: RoadmapConcept) =>
    tailoring ? concept.skills : concept.skills.filter((skill) => !isHidden(skill));

  const openConceptId = selection?.conceptId ?? null;
  const openConcept = graph?.concepts.find((concept) => concept.concept_id === openConceptId) ?? null;
  const openSkill =
    selection?.kind === "skill" ? openConcept?.skills.find((skill) => skill.skill_id === selection.skillId) ?? null : null;

  // The learning order, with each stage's concepts attached. An older API that
  // sends no stages still draws: everything lands in one step.
  const stages: (RoadmapStage & { concepts: RoadmapConcept[] })[] = graph
    ? (graph.stages?.length
        ? graph.stages
        : [{ index: 1, title: "Learn", note: "", concept_ids: graph.concepts.map((concept) => concept.concept_id) }]
      ).map((stage) => ({
        ...stage,
        concepts: stage.concept_ids
          .map((id) => graph.concepts.find((concept) => concept.concept_id === id))
          .filter((concept): concept is RoadmapConcept => Boolean(concept)),
      }))
    : [];

  const everySkill = graph?.concepts.flatMap((concept) => concept.skills).filter((skill) => !isHidden(skill)) ?? [];
  const noMarketData = everySkill.length > 0 && everySkill.every((skill) => skill.market_frequency == null);
  const provenance = everySkill.find((skill) => skill.provenance != null)?.provenance ?? null;
  const overall = everySkill.length
    ? everySkill.reduce((sum, skill) => sum + skill.mastery, 0) / everySkill.length
    : 0;

  return (
    <motion.main
      className="page roadmap-page"
      initial={reduceMotion ? false : { opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.5, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <header className="roadmap-header">
        <div>
          <p className="eyebrow">Roadmap</p>
          <h1 className="page-title">Where your work goes next</h1>
          <p className="roadmap-lede">
            Read it left to right. Each column is a step: what to learn first, what to pick up in
            parallel, and what builds on that. Select any node for a short
            description, its topics, what is missing, and where to study it.
          </p>
        </div>
        <div className="role-controls">
          <div className="market-note">
            {noMarketData ? (
              <>
                <InfoIcon width="16" height="16" />
                <span>No market data for this role yet. Ranked by proximity to your code.</span>
              </>
            ) : provenance ? (
              <SourceBadge provenance={provenance} />
            ) : null}
          </div>
        </div>
      </header>

      {loadError && <div className="error-state" role="alert">{loadError}</div>}

      {!loading && graph && graph.concepts.length > 0 && review && (
        <ReviewBar
          review={review}
          tailoring={tailoring}
          busy={busy}
          hiddenCount={hidden.size}
          fromSurvey={graph.source === "survey"}
          onAccept={() => void accept()}
          onRedo={() => void redo()}
          onStartTailoring={() => void startTailoring()}
          onCancelTailoring={() => void cancelTailoring()}
          onSaveTailoring={() => void saveTailoring()}
        />
      )}

      {loading ? (
        <div className="roadmap-flow roadmap-skeleton" aria-busy="true" aria-label="Loading roadmap" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
          {[1, 3, 2, 1].map((count, column) => (
            <div className="flow-col" key={column}>
              <span className="flow-label" />
              <ul className="flow-nodes">
                {Array.from({ length: count }, (_, node) => (
                  <li key={node}><div className="flow-item"><span className="concept-skeleton flow-skeleton-node" /></div></li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : graph && graph.concepts.length > 0 ? (
        <div className="roadmap-layout">
          <div
            className="roadmap-flow"
            data-testid="roadmap-diagram"
            style={{ gridTemplateColumns: `minmax(124px, .8fr) repeat(${stages.length}, minmax(0, 1fr))` }}
          >
            <div className="flow-col flow-start">
              <span className="flow-label">Start</span>
              <ul className="flow-nodes">
                <li>
                  <div className="flow-item">
                    <div className="flow-node flow-root">
                      <span className="flow-root-label">Your path</span>
                      <h2>{graph.role_name || ROLE.label}</h2>
                      <MasteryBar mastery={overall} reduceMotion={reduceMotion} label="Overall roadmap" />
                    </div>
                  </div>
                </li>
              </ul>
            </div>

            {stages.map((stage) => (
              <div className="flow-col" key={stage.index} data-testid="roadmap-stage">
                <span className="flow-label" title={stage.note}>
                  <b>{stage.index}</b>
                  {stage.title}
                </span>
                <ul className="flow-nodes">
                  {stage.concepts.map((concept) => {
                    const open = openConceptId === concept.concept_id;
                    return (
                      <li key={concept.concept_id}>
                        <div className="flow-item">
                          <button
                            type="button"
                            className="flow-node concept-node"
                            data-testid="concept-node"
                            data-concept={concept.concept_id}
                            data-open={open}
                            aria-expanded={open}
                            aria-controls="roadmap-detail"
                            onClick={() => select({ kind: "concept", conceptId: concept.concept_id })}
                          >
                            <h3>{concept.concept_name}</h3>
                            <MasteryBar mastery={concept.mastery} reduceMotion={reduceMotion} label={concept.concept_name} />
                            <span className="concept-hint">
                              {shownSkills(concept).length} topic{shownSkills(concept).length === 1 ? "" : "s"}
                            </span>
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>

          <AnimatePresence mode="wait" initial={false}>
            {selection && (
              <motion.section
                ref={detailRef}
                className="concept-detail"
                id="roadmap-detail"
                key={selection.kind === "skill" ? selection.skillId : selection.conceptId}
                aria-live="polite"
                initial={reduceMotion ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduceMotion ? undefined : { opacity: 0, y: -6 }}
                transition={{ duration: reduceMotion ? 0 : 0.22, ease: [0.2, 0.8, 0.2, 1] }}
              >
                {openSkill && openConcept ? (
                  <>
                    <button
                      type="button"
                      className="detail-back"
                      onClick={() => select({ kind: "concept", conceptId: openConcept.concept_id })}
                    >
                      ← {openConcept.concept_name}
                    </button>
                    <SkillDetail
                      skill={openSkill}
                      siblings={openConcept.skills.filter((other) => other.skill_id !== openSkill.skill_id && !isHidden(other))}
                      onPick={(skillId) => select({ kind: "skill", conceptId: openConcept.concept_id, skillId })}
                      reduceMotion={reduceMotion}
                    />
                  </>
                ) : openConcept ? (
                  <ConceptSummary
                    concept={openConcept}
                    stage={stages.find((stage) => stage.index === openConcept.stage) ?? null}
                    skills={shownSkills(openConcept)}
                    tailoring={tailoring}
                    isHidden={isHidden}
                    onToggle={toggleHidden}
                    onPick={(skillId) => select({ kind: "skill", conceptId: openConcept.concept_id, skillId })}
                    reduceMotion={reduceMotion}
                  />
                ) : null}
              </motion.section>
            )}
          </AnimatePresence>
        </div>
      ) : !loadError ? (
        <div className="empty-bucket">
          <strong>No roadmap yet</strong>
          <span>Analyse a few repositories and this diagram will fill in.</span>
        </div>
      ) : null}
    </motion.main>
  );
}
