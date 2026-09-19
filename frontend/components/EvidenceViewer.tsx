import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import CodeViewer from "./CodeViewer";
import type { Evidence, Finding } from "@/lib/types";

/**
 * Evidence used to open the Profile page to show its source. That page is gone,
 * so the code comes to the evidence instead: any EvidenceLink opens this dialog
 * in place, on whichever page the link lives.
 */

interface EvidenceRequest {
  evidence: Evidence;
  finding?: Finding;
}

const EvidenceContext = createContext<((request: EvidenceRequest) => void) | null>(null);

export function useEvidenceViewer() {
  return useContext(EvidenceContext);
}

const CONTEXT_LINES = 3;

export function EvidenceProvider({ children }: { children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();
  const [request, setRequest] = useState<EvidenceRequest | null>(null);
  const open = useCallback((next: EvidenceRequest) => setRequest(next), []);
  const close = useCallback(() => setRequest(null), []);

  useEffect(() => {
    if (!request) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [request, close]);

  const slice = useMemo(() => {
    if (!request) return null;
    const [from, to] = request.evidence.lines;
    const start = Math.max(1, from - CONTEXT_LINES);
    return { start, count: to - start + 1 + CONTEXT_LINES };
  }, [request]);

  return (
    <EvidenceContext.Provider value={open}>
      {children}
      <AnimatePresence>
        {request && slice && (
          <motion.div
            className="evidence-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={`Source for ${request.evidence.file}`}
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.18 }}
            onClick={close}
          >
            <motion.div
              className="evidence-dialog"
              data-testid="evidence-dialog"
              initial={reduceMotion ? false : { opacity: 0, y: 18, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: 12, scale: 0.98 }}
              transition={{ duration: reduceMotion ? 0 : 0.24, ease: [0.2, 0.8, 0.2, 1] }}
              onClick={(event) => event.stopPropagation()}
            >
              <header className="evidence-dialog-header">
                <div>
                  <strong>{request.evidence.file}</strong>
                  <small>
                    lines {request.evidence.lines[0]}–{request.evidence.lines[1]}
                    {request.evidence.commit ? ` · ${request.evidence.commit.slice(0, 7)}` : ""}
                  </small>
                </div>
                <button type="button" className="chip" onClick={close} autoFocus>
                  Close
                </button>
              </header>
              <CodeViewer
                repoId={request.evidence.repo_id ?? ""}
                file={request.evidence.file}
                startLine={slice.start}
                lines={slice.count}
                highlight={request.evidence.lines}
                commit={request.evidence.commit}
                finding={request.finding}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </EvidenceContext.Provider>
  );
}
