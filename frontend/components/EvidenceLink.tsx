/** Turns an Evidence object into a clickable jump into CodeViewer. Owner: Track C. */

import type { Evidence } from "@/lib/types";

export interface EvidenceLinkProps {
  evidence: Evidence;
  onOpen: (evidence: Evidence) => void;
  label?: string;
}

export default function EvidenceLink({ evidence, onOpen, label }: EvidenceLinkProps) {
  const text = label ?? `${evidence.file}:${evidence.lines[0]}-${evidence.lines[1]}`;
  return (
    <button
      type="button"
      onClick={() => onOpen(evidence)}
      className="font-mono text-xs text-blue-700 underline underline-offset-2 hover:text-blue-900"
    >
      {text}
    </button>
  );
}
