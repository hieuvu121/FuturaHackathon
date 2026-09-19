/**
 * Renders Provenance so any market figure shows where it came from and on what
 * sample size. A number with no badge is a number with no defence. Owner: Track D + C.
 */

import type { Provenance } from "@/lib/types";

export interface SourceBadgeProps {
  provenance: Provenance | null;
  /** Null frequency is legitimate — render "no data", never 0%. */
  frequency?: number | null;
}

export default function SourceBadge({ provenance, frequency }: SourceBadgeProps) {
  if (!provenance) return <span className="text-xs text-neutral-400">no source</span>;

  const freq = frequency == null ? "no demand data" : `${Math.round(frequency * 100)}% of ads`;
  const sample = provenance.sample_size ? ` · n=${provenance.sample_size}` : "";

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600"
      title={`${provenance.source_kind}: ${provenance.source_name}${sample}`}
    >
      {freq} · {provenance.source_name}
      {sample}
    </span>
  );
}
