/**
 * The most load-bearing component in the product (OVERALL.md).
 * Every score, finding and recommendation links into this.
 *
 * Owner: Track C. Fill in the body; keep the props signature -- three other
 * components import it.
 */

import { useEffect, useState } from "react";

import { getCodeSlice } from "@/lib/data";
import type { CodeSlice } from "@/lib/types";

export interface CodeViewerProps {
  repoId: string;
  file: string;
  /** Inclusive 1-based range to fetch. */
  start: number;
  end: number;
  /** Subrange to highlight within [start, end]. Defaults to the whole slice. */
  highlight?: [number, number];
}

export default function CodeViewer({ repoId, file, start, end, highlight }: CodeViewerProps) {
  const [slice, setSlice] = useState<CodeSlice | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCodeSlice(repoId, file, start, end).then(setSlice).catch((e) => setError(String(e)));
  }, [repoId, file, start, end]);

  if (error) return <pre className="text-sm text-red-600">{error}</pre>;
  if (!slice) return <div className="text-sm text-neutral-500">Loading {file}…</div>;

  const [hs, he] = highlight ?? [start, end];

  // TODO(Track C): syntax highlighting, sticky file header, copy-permalink.
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-neutral-50 font-mono text-sm">
      <div className="border-b border-neutral-200 px-3 py-2 text-xs text-neutral-600">
        {file}:{start}-{end}
      </div>
      <pre className="p-0">
        {slice.lines.map((line, i) => {
          const n = start + i;
          const on = n >= hs && n <= he;
          return (
            <div key={n} className={on ? "bg-amber-100 px-3" : "px-3"}>
              <span className="mr-4 inline-block w-10 select-none text-right text-neutral-400">{n}</span>
              {line}
            </div>
          );
        })}
      </pre>
    </div>
  );
}
