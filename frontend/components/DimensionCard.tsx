/** One dimension: its 1-4 level, rationale, and evidence links. Owner: Track C. */

import type { DimensionScore, Evidence } from "@/lib/types";
import EvidenceLink from "./EvidenceLink";

export interface DimensionCardProps {
  score: DimensionScore;
  onOpenEvidence: (evidence: Evidence) => void;
}

export default function DimensionCard({ score, onOpenEvidence }: DimensionCardProps) {
  // TODO(Track C): level meter, metric_basis table, dimension display names from the API.
  return (
    <article className="rounded-xl border border-neutral-200 p-4">
      <header className="flex items-baseline justify-between">
        <h3 className="font-medium">{score.dimension}</h3>
        <span className="text-sm text-neutral-500">Level {score.level} / 4</span>
      </header>
      <p className="mt-2 text-sm text-neutral-700">{score.rationale}</p>
      {score.evidence.length > 0 && (
        <ul className="mt-3 space-y-1">
          {score.evidence.map((e, i) => (
            <li key={i}>
              <EvidenceLink evidence={e} onOpen={onOpenEvidence} />
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
