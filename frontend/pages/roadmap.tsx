/**
 * Three buckets, each item citing specific code and market evidence,
 * filterable by target role. Owner: Track C.
 */

import { useEffect, useState } from "react";

import SourceBadge from "@/components/SourceBadge";
import { getRoadmap } from "@/lib/data";
import type { Buckets, RoadmapItem } from "@/lib/types";

const REPO_ID = "1";
const TITLES: Record<string, string> = {
  revise: "Revise", deepen: "Deepen", learn_new: "Learn new",
};

function Column({ name, items }: { name: string; items: RoadmapItem[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">{TITLES[name]}</h2>
      {items.map((item) => (
        <article key={item.skill_id} className="space-y-2 rounded-xl border border-neutral-200 p-4">
          <h3 className="font-medium">{item.skill_name}</h3>
          <p className="text-sm text-neutral-700">{item.reason}</p>
          <SourceBadge provenance={item.provenance} frequency={item.market_frequency} />
        </article>
      ))}
    </section>
  );
}

export default function Roadmap() {
  const [buckets, setBuckets] = useState<Buckets | null>(null);
  const [role, setRole] = useState("backend");

  useEffect(() => {
    getRoadmap(REPO_ID, role).then(setBuckets).catch(console.error);
  }, [role]);

  if (!buckets) return <main className="p-8">Loading…</main>;

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-8">
      <h1 className="text-2xl font-medium">Roadmap</h1>
      <div className="grid gap-6 md:grid-cols-3">
        <Column name="revise" items={buckets.revise} />
        <Column name="deepen" items={buckets.deepen} />
        <Column name="learn_new" items={buckets.learn_new} />
      </div>
    </main>
  );
}
