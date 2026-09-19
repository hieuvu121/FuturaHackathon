import { motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import EvidenceLink from "@/components/EvidenceLink";
import { CheckIcon, CopyIcon } from "@/components/Icons";
import PageSkeleton from "@/components/PageSkeleton";
import { getScores, updateShareVisibility } from "@/lib/data";
import type { Scores } from "@/lib/types";
export default function SharePage() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [scores, setScores] = useState<Scores | null>(null);
  const [isPublic, setIsPublic] = useState(true);
  const [copied, setCopied] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [visibilityState, setVisibilityState] = useState<"idle" | "saving" | "saved">("idle");
  const shareId = typeof router.query.id === "string" ? router.query.id : "yourhandle";
  const shareUrl = `retrace.app/share/${shareId}`;

  useEffect(() => {
    getScores("orders-api").then(setScores).catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "The public profile could not be loaded."));
  }, []);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(`https://${shareUrl}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
      setLoadError("Copy was blocked by the browser. Select the link and copy it manually.");
    }
  }

  async function toggleVisibility() {
    if (visibilityState === "saving") return;
    const nextPublic = !isPublic;
    setIsPublic(nextPublic);
    setVisibilityState("saving");
    setLoadError("");
    try {
      await updateShareVisibility(shareId, nextPublic);
      setVisibilityState("saved");
      window.setTimeout(() => setVisibilityState("idle"), 1600);
    } catch {
      setIsPublic(!nextPublic);
      setVisibilityState("idle");
      setLoadError("Visibility could not be saved. Your previous setting is still active.");
    }
  }

  if (loadError && !scores) return <main className="page"><div className="error-state" role="alert">{loadError}</div></main>;
  if (!scores) return <PageSkeleton label="Preparing your public profile" />;

  const verified = scores.skills.filter((skill) => skill.tier === "verified");
  const container = { hidden: {}, show: { transition: { staggerChildren: reduceMotion ? 0 : .08 } } };
  const item = { hidden: reduceMotion ? {} : { opacity: 0, y: 24 }, show: { opacity: 1, y: 0, transition: { duration: reduceMotion ? 0 : .5, ease: [.2,.8,.2,1] as const } } };

  return (
    <motion.main className="page share-page" variants={container} initial="hidden" animate="show">
      <motion.header className="page-header" variants={item}>
        <p className="eyebrow">Share</p>
        <h1 className="page-title">A public profile made of <span className="gradient-text">proof</span></h1>
        <p className="page-copy">Only the verified tier is exported. Touched skills stay private until you verify them in Recall.</p>
      </motion.header>

      {loadError && <div className="error-state" role="alert">{loadError}</div>}
      <div className="share-layout">
        <motion.aside className="owner-controls surface" variants={item}>
          <div className="public-control">
            <span><strong>Public profile</strong><small>{isPublic ? "Anyone with the link can view" : "Only you can view"}</small></span>
            <button type="button" role="switch" aria-checked={isPublic} aria-label="Public profile" aria-busy={visibilityState === "saving"} disabled={visibilityState === "saving"} className={`toggle-switch${isPublic ? " on" : ""}`} onClick={() => void toggleVisibility()}>
              <motion.span layout transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 480, damping: 30 }} />
            </button>
          </div>
          <div className="save-status" role="status" aria-live="polite">{visibilityState === "saving" ? "Saving visibility..." : visibilityState === "saved" ? "Visibility saved" : ""}</div>
          <label htmlFor="share-link">Link</label>
          <div className="copy-row">
            <input id="share-link" className="mono" value={shareUrl} readOnly onFocus={(event) => event.currentTarget.select()} />
            <button type="button" className="primary-button" onClick={() => void copyLink()}>
              <CopyIcon width="18" height="18" />{copied ? "Copied" : "Copy"}
            </button>
            <span className="sr-only" role="status" aria-live="polite">{copied ? "Share link copied" : ""}</span>
          </div>
          <p>Every skill on the public page keeps its evidence link, so a reader can open the exact lines that support the claim.</p>
        </motion.aside>

        <motion.section className={`public-profile surface${isPublic ? "" : " private-preview"}`} variants={item}>
          {!isPublic && <span className="private-badge">Private preview</span>}
          <header className="public-identity">
            <span className="share-avatar">YH</span>
            <div><h2>@yourhandle</h2><p>{verified.length} verified skills across 3 repositories</p></div>
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
