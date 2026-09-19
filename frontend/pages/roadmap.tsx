import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import EvidenceLink from "@/components/EvidenceLink";
import { InfoIcon } from "@/components/Icons";
import SourceBadge from "@/components/SourceBadge";
import { ApiError, getPortfolioRoadmap } from "@/lib/data";
import type { BucketName, Buckets, RoadmapItem } from "@/lib/types";
const ROLES = [
  { id: "backend", label: "Backend engineer" },
  { id: "data", label: "Data engineer" },
  { id: "ml", label: "ML engineer" },
] as const;

const BUCKETS: Array<{ id: BucketName; title: string; description: string }> = [
  { id: "revise", title: "Revise", description: "Touched in your code, not yet verified" },
  { id: "deepen", title: "Deepen", description: "Touched and verified, worth taking further" },
  { id: "learn_new", title: "Learn new", description: "Never touched, in demand, close to what you know" },
];

function RoadmapCard({ item, rank, reduceMotion }: { item: RoadmapItem; rank: number; reduceMotion: boolean | null }) {
  const evidence = item.evidence[0];
  const hasMarketData = item.market_frequency != null;
  return (
    <motion.article className="roadmap-card" variants={{ hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0 } }}>
      <header><h3>{item.skill_name}</h3><strong>Priority {rank}</strong></header>
      <p>{item.reason}</p>
      {evidence && <EvidenceLink evidence={evidence} />}
      <div className="frequency-row">
        <span className="frequency-bar">
          {hasMarketData && <motion.i initial={reduceMotion ? false : { scaleX: 0 }} animate={{ scaleX: item.market_frequency ?? 0 }} transition={{ duration: reduceMotion ? 0 : .7, delay: reduceMotion ? 0 : .25, ease: [.2,.8,.2,1] }} />}
        </span>
        <small>{hasMarketData ? `in ${Math.round((item.market_frequency ?? 0) * 100)}% of sampled roles` : "No market data"}</small>
      </div>
    </motion.article>
  );
}

export default function RoadmapPage() {
  const reduceMotion = useReducedMotion();
  const [role, setRole] = useState<(typeof ROLES)[number]["id"]>("backend");
  const [roadmap, setRoadmap] = useState<Buckets | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function load() {
      try {
        const data = await getPortfolioRoadmap(role);
        if (active) { setRoadmap(data); setLoading(false); }
      } catch (error: unknown) {
        if (!active) return;
        if (error instanceof ApiError && [404, 409].includes(error.status)) {
          timer = window.setTimeout(load, 1800);
        } else {
          setLoadError(error instanceof Error ? error.message : "The roadmap could not be loaded.");
          setLoading(false);
        }
      }
    }
    void load();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, [role]);

  const noMarketData = roadmap ? [...roadmap.revise, ...roadmap.deepen, ...roadmap.learn_new].every((item) => item.market_frequency == null) : false;
  const provenance = roadmap?.revise[0]?.provenance ?? roadmap?.deepen[0]?.provenance ?? roadmap?.learn_new[0]?.provenance;

  function changeRole(nextRole: (typeof ROLES)[number]["id"]) {
    if (nextRole === role) return;
    setLoadError("");
    setLoading(true);
    setRoadmap(null);
    setRole(nextRole);
  }

  return (
    <motion.main className="page roadmap-page" initial={reduceMotion ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduceMotion ? 0 : .5, ease: [.2,.8,.2,1] }}>
      <header className="roadmap-header">
        <div><p className="eyebrow">Roadmap</p><h1 className="page-title">What to work on next</h1></div>
        <div className="role-controls">
          <div role="group" aria-label="Target role">
            {ROLES.map((option) => <button key={option.id} type="button" className={`role-pill chip${role === option.id ? " active" : ""}`} aria-pressed={role === option.id} onClick={() => changeRole(option.id)}>{option.label}</button>)}
          </div>
          <div className="market-note">
            {noMarketData ? <><InfoIcon width="16" height="16" /><span>No market data for this role yet. Ranked by proximity to your code.</span></> : provenance ? <SourceBadge provenance={provenance} /> : null}
          </div>
        </div>
      </header>

      {loadError && <div className="error-state" role="alert">{loadError}</div>}
      <AnimatePresence mode="popLayout" initial={false}>
        {loading ? (
          <motion.div key={`loading-${role}`} className="roadmap-columns roadmap-skeleton" aria-busy="true" aria-label={`Loading ${role} roadmap`} initial={reduceMotion ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            {BUCKETS.map((bucket) => <div key={bucket.id} className="roadmap-skeleton-column"><span /><i /><i /></div>)}
          </motion.div>
        ) : roadmap && (
          <motion.div
            key={role}
            className="roadmap-columns"
            initial={reduceMotion ? false : { opacity: 0, x: 28 }}
            animate={{ opacity: 1, x: 0 }}
            exit={reduceMotion ? undefined : { opacity: 0, x: -28 }}
            transition={{ duration: reduceMotion ? 0 : .3, ease: [.2,.8,.2,1] }}
          >
            {BUCKETS.map((bucket) => {
              const items = [...roadmap[bucket.id]].sort((left, right) => right.priority - left.priority);
              return (
                <section className={`roadmap-column bucket-${bucket.id}`} key={bucket.id}>
                  <header><h2>{bucket.title}</h2><p>{bucket.description}</p></header>
                  <motion.div variants={{ hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } }} initial="hidden" animate="show">
                    {items.length > 0 ? items.map((item) => <RoadmapCard key={item.skill_id} item={item} rank={item.priority ? Math.max(1, [...roadmap.revise, ...roadmap.deepen, ...roadmap.learn_new].sort((a,b) => b.priority-a.priority).findIndex((entry) => entry.skill_id === item.skill_id) + 1) : 1} reduceMotion={reduceMotion} />) : <div className="empty-bucket"><strong>No recommendations yet</strong><span>More analysed code will make this bucket more useful.</span></div>}
                  </motion.div>
                </section>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.main>
  );
}
