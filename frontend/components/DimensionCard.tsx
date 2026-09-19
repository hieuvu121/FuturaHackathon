import { motion, useReducedMotion } from "framer-motion";

import type { DimensionScore, Evidence } from "@/lib/types";
import EvidenceLink from "./EvidenceLink";

export interface DimensionCardProps {
  score: DimensionScore;
  selected: boolean;
  onOpenEvidence: (evidence: Evidence) => void;
}
export default function DimensionCard({ score, selected, onOpenEvidence }: DimensionCardProps) {
  const reduceMotion = useReducedMotion();

  return (
    <article className={`dimension-card${selected ? " selected" : ""}`}>
      <header>
        <h3>{score.dimension}</h3>
        <strong>Level {score.level} of 4</strong>
      </header>
      <div className="level-segments" aria-label={`Level ${score.level} of 4`}>
        {[1, 2, 3, 4].map((segment) => (
          <span key={segment}>
            {segment <= score.level && (
              <motion.i
                initial={reduceMotion ? false : { scaleX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: reduceMotion ? 0 : .55, delay: reduceMotion ? 0 : .1 + segment * .08, ease: [.2, .8, .2, 1] }}
              />
            )}
          </span>
        ))}
      </div>
      <p>{score.rationale}</p>
      {score.evidence[0] && <EvidenceLink evidence={score.evidence[0]} onOpen={onOpenEvidence} />}
    </article>
  );
}
