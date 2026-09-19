import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";

import CodeViewer from "@/components/CodeViewer";
import DimensionCard from "@/components/DimensionCard";
import { CheckIcon } from "@/components/Icons";
import PageSkeleton from "@/components/PageSkeleton";
import { ApiError, getPortfolioProfile } from "@/lib/data";
import type { Evidence, Finding, PortfolioProfile } from "@/lib/types";

function sameEvidence(left: Evidence, right: Evidence) {
  return left.repo_id === right.repo_id && left.file === right.file && left.lines[0] <= right.lines[1] && right.lines[0] <= left.lines[1];
}

export default function ProfilePage() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [profile, setProfile] = useState<PortfolioProfile | null>(null);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function load() {
      try {
        const data = await getPortfolioProfile();
        if (!active) return;
        setProfile(data);
        setSelected(data.findings[0] ?? null);
      } catch (error: unknown) {
        if (!active) return;
        if (error instanceof ApiError && [404, 409].includes(error.status)) {
          timer = window.setTimeout(load, 1800);
        } else {
          setLoadError(error instanceof Error ? error.message : "The capability map could not be loaded.");
        }
      }
    }
    void load();
    return () => { active = false; if (timer) window.clearTimeout(timer); };
  }, []);

  const queryEvidence = useMemo<Evidence | null>(() => {
    if (!router.isReady || typeof router.query.file !== "string") return null;
    const from = Number(router.query.from);
    const to = Number(router.query.to);
    if (!Number.isFinite(from) || !Number.isFinite(to)) return null;
    return { repo_id: typeof router.query.repo === "string" ? router.query.repo : null, file: router.query.file, lines: [from, to], commit: typeof router.query.commit === "string" ? router.query.commit : null };
  }, [router.isReady, router.query.commit, router.query.file, router.query.from, router.query.repo, router.query.to]);
  const queryFinding = useMemo(() => {
    if (typeof router.query.ev === "string") return profile?.findings.find((finding) => finding.id === router.query.ev) ?? null;
    if (queryEvidence) return profile?.findings.find((finding) => sameEvidence(finding.evidence, queryEvidence)) ?? null;
    return null;
  }, [profile?.findings, queryEvidence, router.query.ev]);
  const activeFinding = queryFinding ?? selected;
  const activeEvidence = queryEvidence ?? activeFinding?.evidence ?? profile?.scores.dimensions[0]?.evidence[0] ?? null;
  const sourceWindow = activeEvidence ? { start: activeEvidence.lines[0], count: activeEvidence.lines[1] - activeEvidence.lines[0] + 1 } : null;

  function openEvidence(evidence: Evidence) {
    const finding = profile?.findings.find((candidate) => sameEvidence(candidate.evidence, evidence)) ?? null;
    setSelected(finding);
    void router.replace("/profile", undefined, { shallow: true });
  }

  if (loadError) return <main className="page"><div className="error-state" role="alert">{loadError}</div></main>;
  if (!profile) return <PageSkeleton label="Building your capability map" />;
  if (!activeEvidence || !sourceWindow) return (
    <main className="page">
      <section className="empty-state surface">
        <p className="eyebrow">Profile</p>
        <h1>No capability evidence yet</h1>
        <p>Analyse at least one repository to build a capability map from real source evidence.</p>
        <Link className="primary-button" href="/connect">Choose repositories</Link>
      </section>
    </main>
  );

  const { scores } = profile;
  const verified = scores.skills.filter((skill) => skill.tier === "verified");
  const touched = scores.skills.filter((skill) => skill.tier === "touched");
  const container = { hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } };
  const item = { hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : .5, ease: [.2,.8,.2,1] as const } } };

  return (
    <motion.main className="page profile-page" variants={container} initial="hidden" animate="show">
      <motion.header className="profile-header" variants={item}>
        <div><p className="eyebrow">Profile</p><h1 className="page-title">Capability map</h1></div>
        <div className="profile-stats">
          <span className="chip mono">{profile.repositories.length} repositories</span>
          <span className="chip">{profile.total_functions} functions mapped</span>
          <span className="chip">{profile.excluded_files} files excluded</span>
        </div>
      </motion.header>

      <div className="profile-layout">
        <motion.div className="profile-left" variants={item}>
          <section className="dimension-grid" aria-label="Capability dimensions">
            {scores.dimensions.map((score) => (
              <DimensionCard
                key={score.dimension}
                score={score}
                selected={activeFinding?.dimension === score.dimension}
                onOpenEvidence={openEvidence}
              />
            ))}
          </section>

          <section className="skill-tiers surface">
            <div className="skill-row">
              <strong>Verified</strong>
              <div>{verified.length > 0 ? verified.map((skill) => <span className="skill-chip verified chip" key={skill.skill_id}><CheckIcon width="14" height="14" />{skill.skill_id}</span>) : <span className="empty-skill">No verified skills yet</span>}</div>
            </div>
            <div className="skill-row">
              <strong>Touched</strong>
              <div>{touched.length > 0 ? touched.map((skill) => <span className="skill-chip touched chip" key={skill.skill_id}>{skill.skill_id}</span>) : <span className="empty-skill">No touched skills yet</span>}</div>
            </div>
          </section>
        </motion.div>

        <motion.aside className="profile-code" variants={item}>
          <CodeViewer
            repoId={activeEvidence.repo_id ?? profile.repositories[0].id}
            file={activeEvidence.file}
            startLine={sourceWindow.start}
            lines={sourceWindow.count}
            highlight={activeEvidence.lines}
            commit={activeEvidence.commit}
            finding={activeFinding ?? undefined}
          />
        </motion.aside>
      </div>
    </motion.main>
  );
}
