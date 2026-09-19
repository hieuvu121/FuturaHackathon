import { motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import EvidenceLink from "@/components/EvidenceLink";
import { CheckIcon, CopyIcon } from "@/components/Icons";
import PageSkeleton from "@/components/PageSkeleton";
import { getCurrentUser, getPortfolioProfile } from "@/lib/data";
import type { PortfolioProfile } from "@/lib/types";
export default function SharePage() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [profile, setProfile] = useState<PortfolioProfile | null>(null);
  const [login, setLogin] = useState("");
  const [copied, setCopied] = useState(false);
  const [loadError, setLoadError] = useState("");
  const shareId = typeof router.query.id === "string" ? router.query.id : "yourhandle";
  const shareUrl = router.isReady && typeof window !== "undefined" ? window.location.href : `/share/${shareId}`;

  useEffect(() => {
    Promise.all([getPortfolioProfile(), getCurrentUser()])
      .then(([profileData, user]) => { setProfile(profileData); setLogin(user.user); })
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "The profile preview could not be loaded."));
  }, []);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
      setLoadError("Copy was blocked by the browser. Select the link and copy it manually.");
    }
  }

  if (loadError && !profile) return <main className="page"><div className="error-state" role="alert">{loadError}</div></main>;
  if (!profile) return <PageSkeleton label="Preparing your profile preview" />;

  const { scores } = profile;
  const verified = scores.skills.filter((skill) => skill.tier === "verified");
  const initials = login.slice(0, 2).toUpperCase() || "GH";
  const container = { hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } };
  const item = { hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : .5, ease: [.2,.8,.2,1] as const } } };

  return (
    <motion.main className="page share-page" variants={container} initial="hidden" animate="show">
      <motion.header className="page-header" variants={item}>
        <p className="eyebrow">Share</p>
        <h1 className="page-title">A profile preview made of <span className="gradient-text">proof</span></h1>
        <p className="page-copy">This is an owner-only preview. Public publishing is not enabled yet.</p>
      </motion.header>

      {loadError && <div className="error-state" role="alert">{loadError}</div>}
      <div className="share-layout">
        <motion.aside className="owner-controls surface" variants={item}>
          <div className="public-control"><span><strong>Owner preview</strong><small>Publishing controls are not connected yet</small></span></div>
          <label htmlFor="share-link">Link</label>
          <div className="copy-row">
            <input id="share-link" className="mono" value={shareUrl} readOnly onFocus={(event) => event.currentTarget.select()} />
            <button type="button" className="primary-button" onClick={() => void copyLink()}>
              <CopyIcon width="18" height="18" />{copied ? "Copied" : "Copy"}
            </button>
            <span className="sr-only" role="status" aria-live="polite">{copied ? "Share link copied" : ""}</span>
          </div>
          <p>Verified skills retain their repository-specific evidence links in this preview.</p>
        </motion.aside>

        <motion.section className="public-profile surface private-preview" variants={item}>
          <span className="private-badge">Owner preview</span>
          <header className="public-identity">
            <span className="share-avatar">{initials}</span>
            <div><h2>@{login}</h2><p>{verified.length} verified skills across {profile.repositories.length} repositories</p></div>
          </header>
          {verified.length > 0 ? <ul className="verified-list">
            {verified.map((skill) => {
              const evidence = skill.evidence[0];
              return (
                <li key={skill.skill_id}>
                  <span className="verified-check"><CheckIcon width="16" height="16" /></span>
                  <strong>{skill.skill_id}</strong>
                  {evidence && <EvidenceLink evidence={evidence} />}
                </li>
              );
            })}
          </ul> : <div className="verified-empty"><strong>No verified skills yet</strong><p>Complete a Recall session to add evidence-backed skills to this profile.</p></div>}
          <div className="compact-dimensions">
            {scores.dimensions.map((score) => (
              <div key={score.dimension}>
                <span><strong>{score.dimension}</strong><small>Level {score.level} of 4</small></span>
                <i><motion.b initial={reduceMotion ? false : { scaleX: 0 }} animate={{ scaleX: score.level / 4 }} transition={{ duration: reduceMotion ? 0 : .65, delay: reduceMotion ? 0 : .25, ease: [.2,.8,.2,1] }} /></i>
              </div>
            ))}
          </div>
        </motion.section>
      </div>
    </motion.main>
  );
}
