import Link from "next/link";

import type { Evidence } from "@/lib/types";
import { ExternalIcon } from "./Icons";

export interface EvidenceLinkProps {
  evidence: Evidence;
  onOpen?: (evidence: Evidence) => void;
  findingId?: string;
}
export default function EvidenceLink({ evidence, onOpen, findingId }: EvidenceLinkProps) {
  const label = `${evidence.file}:${evidence.lines[0]}-${evidence.lines[1]}`;
  const content = <><span>{label}</span><ExternalIcon width="15" height="15" /></>;
  const className = "evidence-link";

  if (onOpen) {
    return <button type="button" className={className} onClick={() => onOpen(evidence)}>{content}</button>;
  }

  const href = findingId
    ? { pathname: "/profile", query: { ev: findingId } }
    : { pathname: "/profile", query: { file: evidence.file, from: evidence.lines[0], to: evidence.lines[1], commit: evidence.commit ?? undefined } };

  return <Link className={className} href={href}>{content}</Link>;
}
