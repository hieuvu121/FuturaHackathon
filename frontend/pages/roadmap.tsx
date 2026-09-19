import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import EvidenceLink from "@/components/EvidenceLink";
import { CheckIcon, InfoIcon } from "@/components/Icons";
import SourceBadge from "@/components/SourceBadge";
import { ApiError, getRoadmapGraph } from "@/lib/data";
import type { ConceptSkill, NodeStatus, RoadmapConcept, RoadmapGraph } from "@/lib/types";

const ROLE = { id: "software_engineer", label: "Software engineer" } as const;

const STATUS_LABEL: Record<NodeStatus, string> = {
  verified: "Verified",
  familiar: "Basics",
  new: "New",
};

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

function SkillNode({ skill, reduceMotion }: { skill: ConceptSkill; reduceMotion: boolean | null }) {
  // The gap the focus line names beats the skill's own evidence: it points at
  // the problem to fix, not merely at where the skill was used.
  const evidence = skill.gap_evidence ?? skill.evidence[0];
  return (
    <motion.li
      className={`skill-node node-${skill.status}`}
      data-testid="skill-node"
      variants={{ hidden: reduceMotion ? {} : { opacity: 0, x: -10 }, show: { opacity: 1, x: 0 } }}
    >
      <header>
        <StatusMark status={skill.status} />
        <h4>{skill.skill_name}</h4>
        <span className="skill-status">{STATUS_LABEL[skill.status]}</span>
      </header>
      <MasteryBar
        mastery={skill.mastery}
        status={skill.status}
        reduceMotion={reduceMotion}
        label={skill.skill_name}
      />
      <p className="skill-focus">{skill.focus}</p>
      <footer>
        {evidence ? <EvidenceLink evidence={evidence} compact /> : <span />}
        {skill.market_frequency != null && (
          <span className="demand-chip" title="Share of sampled job ads naming this skill">
            {Math.round(skill.market_frequency * 100)}% of roles
          </span>
        )}
      </footer>
    </motion.li>
  );
}

function ConceptRow({
  concept,
  side,
  open,
  onToggle,
  reduceMotion,
}: {
  concept: RoadmapConcept;
  side: "left" | "right";
  open: boolean;
  onToggle: () => void;
  reduceMotion: boolean | null;
}) {
  const panelId = `concept-panel-${concept.concept_id}`;
  const total = concept.verified_count + concept.familiar_count + concept.new_count;

  const detail = (
    <motion.div
      className="concept-detail"
      id={panelId}
      key={panelId}
      initial={reduceMotion ? false : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduceMotion ? undefined : { opacity: 0, y: -8 }}
      transition={{ duration: reduceMotion ? 0 : 0.28, ease: [0.2, 0.8, 0.2, 1] }}
    >
      <motion.ul
        className="skill-list"
        variants={{ hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : 0.05 } } }}
        initial="hidden"
        animate="show"
      >
        {concept.skills.map((skill) => (
          <SkillNode key={skill.skill_id} skill={skill} reduceMotion={reduceMotion} />
        ))}
      </motion.ul>
    </motion.div>
  );

  return (
    <div className={`concept-row side-${side}`} data-open={open}>
      <div className="rail rail-left">
        <AnimatePresence initial={false}>{open && side === "left" && detail}</AnimatePresence>
      </div>

      <button
        type="button"
        className="concept-node"
        data-testid="concept-node"
        data-concept={concept.concept_id}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <h3>{concept.concept_name}</h3>
        <MasteryBar mastery={concept.mastery} reduceMotion={reduceMotion} label={concept.concept_name} />
        <div className="concept-counts">
          {concept.verified_count > 0 && <span className="count count-verified">{concept.verified_count} verified</span>}
          {concept.familiar_count > 0 && <span className="count count-familiar">{concept.familiar_count} basics</span>}
          {concept.new_count > 0 && <span className="count count-new">{concept.new_count} new</span>}
        </div>
        <span className="concept-hint">{open ? "Hide detail" : `Show ${total} skill${total === 1 ? "" : "s"}`}</span>
      </button>

      <div className="rail rail-right">
        <AnimatePresence initial={false}>{open && side === "right" && detail}</AnimatePresence>
      </div>
    </div>
  );
}

export default function RoadmapPage() {
  const reduceMotion = useReducedMotion();
  const [graph, setGraph] = useState<RoadmapGraph | null>(null);
  const [openConcept, setOpenConcept] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function load() {
      try {
        const data = await getRoadmapGraph(ROLE.id);
        if (!active) return;
        setGraph(data);
        setOpenConcept(data.concepts[0]?.concept_id ?? null);
        setLoading(false);
      } catch (error: unknown) {
        if (!active) return;
        // 404/409 mean the analysis has not finished yet, so keep waiting.
        if (error instanceof ApiError && [404, 409].includes(error.status)) {
          timer = window.setTimeout(load, 1800);
        } else {
          setLoadError(error instanceof Error ? error.message : "The roadmap could not be loaded.");
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const everySkill = graph?.concepts.flatMap((concept) => concept.skills) ?? [];
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
            Each box is a concept. Open one to see what to do about it, based on what your code already proves.
          </p>
        </div>
        <div className="role-controls">
          <span className="role-pill chip active" aria-current="true">{ROLE.label}</span>
          {everySkill.length > 0 && (
            <div className="overall-mastery">
              <span>Overall</span>
              <MasteryBar mastery={overall} reduceMotion={reduceMotion} label="Overall roadmap" />
            </div>
          )}
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

      {loading ? (
        <div className="roadmap-diagram roadmap-skeleton" aria-busy="true" aria-label="Loading roadmap">
          {[0, 1, 2, 3].map((row) => (
            <div className="concept-row" key={row}>
              <div className="rail rail-left" />
              <span className="concept-skeleton" />
              <div className="rail rail-right" />
            </div>
          ))}
        </div>
      ) : graph && graph.concepts.length > 0 ? (
        <div className="roadmap-diagram" data-testid="roadmap-diagram">
          {graph.concepts.map((concept, index) => (
            <ConceptRow
              key={concept.concept_id}
              concept={concept}
              side={index % 2 === 0 ? "right" : "left"}
              open={openConcept === concept.concept_id}
              onToggle={() => setOpenConcept(openConcept === concept.concept_id ? null : concept.concept_id)}
              reduceMotion={reduceMotion}
            />
          ))}
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
