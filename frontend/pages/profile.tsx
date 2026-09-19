/**
 * Capability map across six dimensions, touched vs verified tiers,
 * repository overview. Owner: Track C.
 */

import { useEffect, useState } from "react";

import DimensionCard from "@/components/DimensionCard";
import CodeViewer from "@/components/CodeViewer";
import { getScores } from "@/lib/data";
import type { Evidence, Scores } from "@/lib/types";

const REPO_ID = "1"; // TODO(Track C): from the route / selection state

export default function Profile() {
  const [scores, setScores] = useState<Scores | null>(null);
  const [open, setOpen] = useState<Evidence | null>(null);

  useEffect(() => {
    getScores(REPO_ID).then(setScores).catch(console.error);
  }, []);

  if (!scores) return <main className="p-8">Loading…</main>;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-8">
      <h1 className="text-2xl font-medium">{scores.repo}</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {scores.dimensions.map((d) => (
          <DimensionCard key={d.dimension} score={d} onOpenEvidence={setOpen} />
        ))}
      </div>
      {open && (
        <CodeViewer
          repoId={REPO_ID}
          file={open.file}
          start={Math.max(1, open.lines[0] - 5)}
          end={open.lines[1] + 5}
          highlight={open.lines}
        />
      )}
    </main>
  );
}
