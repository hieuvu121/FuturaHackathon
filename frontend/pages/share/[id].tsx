/**
 * Public profile. Owner: Track C.
 *
 * EXPORTS THE VERIFIED TIER ONLY (OVERALL.md, [SHARE]).
 * Touched-tier skills must never appear here. Evidence links stay intact.
 */

import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { getScores } from "@/lib/data";
import type { Scores } from "@/lib/types";

export default function SharedProfile() {
  const { id } = useRouter().query;
  const [scores, setScores] = useState<Scores | null>(null);

  useEffect(() => {
    if (typeof id === "string") getScores(id).then(setScores).catch(console.error);
  }, [id]);

  if (!scores) return <main className="p-8">Loading…</main>;

  const verified = scores.skills.filter((s) => s.tier === "verified");

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <h1 className="text-2xl font-medium">Verified capabilities</h1>
      <p className="text-sm text-neutral-600">
        Each skill below was demonstrated against the author&apos;s own code, then re-verified
        by recall. Unverified work is not shown.
      </p>
      <ul className="space-y-2">
        {verified.map((s) => (
          <li key={s.skill_id} className="rounded-lg border border-neutral-200 p-3 font-mono text-sm">
            {s.skill_id}
          </li>
        ))}
      </ul>
    </main>
  );
}
