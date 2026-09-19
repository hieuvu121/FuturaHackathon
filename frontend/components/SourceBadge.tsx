import type { Provenance } from "@/lib/types";
import { InfoIcon } from "./Icons";

export interface SourceBadgeProps {
  provenance: Provenance;
}
export default function SourceBadge({ provenance }: SourceBadgeProps) {
  const sample = provenance.sample_size == null ? "sample unavailable" : `${provenance.sample_size} records`;
  const date = provenance.collected_at
    ? new Intl.DateTimeFormat("en-AU", { month: "short", year: "numeric" }).format(new Date(provenance.collected_at))
    : "date unavailable";

  return (
    <span className="source-badge" title={`Confidence ${Math.round(provenance.confidence * 100)}%`}>
      <InfoIcon width="15" height="15" />
      <span>{provenance.source_kind}</span>
      <span>{provenance.source_name}</span>
      <span>{sample}</span>
      <span>{date}</span>
    </span>
  );
}
