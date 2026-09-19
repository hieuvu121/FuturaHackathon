import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

import { getCode } from "@/lib/data";
import type { CodeSlice, Finding } from "@/lib/types";

export interface CodeViewerProps {
  repoId?: string;
  file: string;
  startLine: number;
  lines: number | string[];
  highlight: [number, number];
  commit?: string | null;
  finding?: Finding;
}

export default function CodeViewer({
  repoId = "orders-api",
  file,
  startLine,
  lines,
  highlight,
  commit,
  finding,
}: CodeViewerProps) {
  const reduceMotion = useReducedMotion();
  const [slice, setSlice] = useState<CodeSlice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lineCount = Array.isArray(lines) ? lines.length : lines;
  const overrideKey = Array.isArray(lines) ? lines.join("\n") : "";

  useEffect(() => {
    let active = true;
    getCode(repoId, file, startLine, startLine + lineCount - 1)
      .then((loaded) => {
        if (!active) return;
        setError(null);
        setSlice(Array.isArray(lines) ? { ...loaded, start: startLine, end: startLine + lines.length - 1, lines } : loaded);
      })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : "Unable to load this source slice."); });
    return () => { active = false; };
  }, [file, lineCount, overrideKey, repoId, startLine, lines]);

  const contentKey = useMemo(() => `${file}:${startLine}:${overrideKey || "source"}`, [file, overrideKey, startLine]);

  if (error) return <div className="code-viewer error-state" role="alert">{error}</div>;
  if (!slice) return <div className="code-viewer code-loading" aria-label={`Loading ${file}`}><span /><span /><span /><span /><span /></div>;

  return (
    <section className="code-viewer surface" aria-label={`Source code from ${file}`}>
      <header className="code-header">
        <strong>{file}</strong>
        <span>{commit ?? slice.commit}</span>
      </header>
      <div className="code-lines-wrap">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.div
            key={contentKey}
            className="code-lines"
            tabIndex={0}
            aria-label="Source code. Scroll horizontally to view long lines."
            initial={reduceMotion ? false : { opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, x: -12 }}
            transition={{ duration: reduceMotion ? 0 : .24, ease: [.2, .8, .2, 1] }}
          >
            {slice.lines.map((line, index) => {
              const lineNumber = slice.start + index;
              const highlighted = lineNumber >= highlight[0] && lineNumber <= highlight[1];
              return (
                <div key={lineNumber} className={`code-line${highlighted ? " highlighted" : ""}`}>
                  <span>{lineNumber}</span>
                  <code>{line || " "}</code>
                </div>
              );
            })}
          </motion.div>
        </AnimatePresence>
      </div>
      {finding && (
        <footer className="finding-panel">
          <div>
            <span className={`severity severity-${finding.severity}`}>{finding.severity} severity</span>
            <strong>{finding.dimension}</strong>
            <small>confidence {finding.confidence.toFixed(2)}</small>
          </div>
          <p>{finding.observation}</p>
        </footer>
      )}
    </section>
  );
}
