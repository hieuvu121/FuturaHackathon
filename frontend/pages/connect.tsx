/** GitHub connect and repository selection (3-5 repos). Owner: Track C. */

import { useEffect, useState } from "react";

import { getRepos, startAnalysis } from "@/lib/data";
import type { Repo } from "@/lib/types";

export default function Connect() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    getRepos().then(setRepos).catch(console.error);
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.size < 5 && next.add(id);
      return next;
    });
  }

  const ready = selected.size >= 3 && selected.size <= 5;

  // TODO(Track C): OAuth button, per-repo analysis progress polling via getStatus.
  return (
    <main className="mx-auto max-w-2xl space-y-6 p-8">
      <h1 className="text-2xl font-medium">Select 3–5 repositories</h1>
      <ul className="space-y-2">
        {repos.map((r) => (
          <li key={r.id}>
            <label className="flex items-center gap-3 rounded-lg border border-neutral-200 p-3">
              <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} />
              <span className="font-mono text-sm">{r.full_name}</span>
              <span className="ml-auto text-xs text-neutral-500">{r.language}</span>
            </label>
          </li>
        ))}
      </ul>
      <button
        type="button"
        disabled={!ready}
        onClick={() => selected.forEach((id) => startAnalysis(id))}
        className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-40"
      >
        Analyse {selected.size} repositories
      </button>
    </main>
  );
}
