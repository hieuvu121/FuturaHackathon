import type { Evidence, Finding } from "@/lib/types";
import { useEvidenceViewer } from "./EvidenceViewer";
import { ExternalIcon } from "./Icons";

export interface EvidenceLinkProps {
  evidence: Evidence;
  onOpen?: (evidence: Evidence) => void;
  finding?: Finding;
  /** Show only the file name. The full path stays in the tooltip. */
  compact?: boolean;
}

export default function EvidenceLink({ evidence, onOpen, finding, compact }: EvidenceLinkProps) {
  const openViewer = useEvidenceViewer();
  const range = `${evidence.lines[0]}-${evidence.lines[1]}`;
  const full = `${evidence.file}:${range}`;
  const label = compact ? `${evidence.file.split("/").pop()}:${range}` : full;

  return (
    <button
      type="button"
      className="evidence-link"
      title={full}
      onClick={() => (onOpen ? onOpen(evidence) : openViewer?.({ evidence, finding }))}
    >
      <span>{label}</span>
      <ExternalIcon width="15" height="15" />
    </button>
  );
}
