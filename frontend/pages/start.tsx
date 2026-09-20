import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { ArrowRightIcon, CheckIcon, ConnectIcon, RecallIcon } from "@/components/Icons";
import { getLearnerProfile, getRolePaths, loginUrl, submitSurvey } from "@/lib/data";
import type { LearnerProfile, RolePath } from "@/lib/types";

type Step = "choose" | "role" | "skills";

/**
 * The first page: two ways in, one way out.
 *
 *   code on GitHub  ->  connect repositories  ->  recall  ->  roadmap
 *   no code yet     ->  a short survey        ->  recall  ->  roadmap
 *
 * The survey asks only what it uses: the role to aim at, and which of that
 * role's skills the person has already touched. It needs no account.
 */
export default function StartPage() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [step, setStep] = useState<Step>("choose");
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [roles, setRoles] = useState<RolePath[]>([]);
  const [roleId, setRoleId] = useState<string | null>(null);
  const [known, setKnown] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    // Neither call needs a login, so a first-time visitor sees the page at once.
    getLearnerProfile().then((found) => active && setProfile(found)).catch(() => undefined);
    getRolePaths()
      .then((found) => active && setRoles(found))
      .catch((cause: unknown) => active && setError(cause instanceof Error ? cause.message : "The roles could not be loaded."));
    return () => {
      active = false;
    };
  }, []);

  const role = roles.find((item) => item.id === roleId) ?? null;
  // Having a session is not enough: the GitHub token can expire or be revoked,
  // and then the way forward is to sign in again, not to open an empty repo list.
  const signedInWithGitHub = Boolean(profile?.github_connected);

  function connectRepos() {
    // Someone already signed in with GitHub goes straight to their repositories;
    // anyone else signs in first, and GitHub sends them back to the same place.
    if (signedInWithGitHub) void router.push("/connect");
    else window.location.href = loginUrl;
  }

  function pickRole(id: string) {
    setRoleId(id);
    setKnown(new Set());
    setStep("skills");
  }

  function toggle(skillId: string) {
    setKnown((current) => {
      const next = new Set(current);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      return next;
    });
  }

  async function finish() {
    if (!roleId || busy) return;
    setBusy(true);
    setError("");
    try {
      await submitSurvey(roleId, [...known]);
      await router.push("/recall");
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Your answers could not be saved.");
      setBusy(false);
    }
  }

  const slide = {
    initial: reduceMotion ? false : { opacity: 0, x: 40 },
    animate: { opacity: 1, x: 0 },
    exit: reduceMotion ? undefined : { opacity: 0, x: -40 },
    transition: { duration: reduceMotion ? 0 : 0.32, ease: [0.2, 0.8, 0.2, 1] as const },
  };

  return (
    <main className="page start-page">
      <header className="page-header">
        <p className="eyebrow">Start</p>
        <h1 className="page-title">
          {step === "choose" ? <>Where are you <span className="gradient-text">starting from?</span></> : step === "role" ? "Which role are you aiming for?" : "Which of these have you already used?"}
        </h1>
        <p className="page-copy">
          {step === "choose"
            ? "Both ways end in the same place: five short questions, then a roadmap built for you. The only difference is what it is built from."
            : step === "role"
              ? "Your roadmap starts from the path to this role. You can come back and change it."
              : "Tick anything you have worked with, even a little. Those get asked about first, so the roadmap reflects what you really know rather than what you remember ticking."}
        </p>
      </header>

      {error && <div className="error-state" role="alert">{error}</div>}

      <AnimatePresence mode="wait" initial={false}>
        {step === "choose" && (
          <motion.section key="choose" className="start-choices" {...slide}>
            <button type="button" className="start-choice surface interactive-card" data-testid="start-repos" onClick={connectRepos}>
              <span className="start-icon"><ConnectIcon width="26" height="26" /></span>
              <strong>I have code on GitHub</strong>
              <span>Pick 3 to 5 repositories. Your roadmap is built from what your code actually shows, with the file and line behind every claim.</span>
              <ol className="start-steps"><li>Connect repositories</li><li>Recall</li><li>Roadmap</li></ol>
              <em>{signedInWithGitHub ? "Choose repositories" : "Connect GitHub"} <ArrowRightIcon width="17" height="17" /></em>
            </button>

            <button type="button" className="start-choice surface interactive-card" data-testid="start-survey" onClick={() => setStep("role")}>
              <span className="start-icon alt"><RecallIcon width="26" height="26" /></span>
              <strong>I am just starting out</strong>
              <span>No repositories, no account needed. Tell us the role you want, answer a few questions, and get a roadmap of what to learn and in what order.</span>
              <ol className="start-steps"><li>Two-step survey</li><li>Recall</li><li>Roadmap</li></ol>
              <em>Answer the survey <ArrowRightIcon width="17" height="17" /></em>
            </button>

            {profile?.path === "survey" && profile.role_name && (
              <p className="start-note">
                You already have a roadmap for <strong>{profile.role_name}</strong>.{" "}
                <button type="button" className="detail-back" onClick={() => void router.push("/roadmap")}>Open it</button>, or answer the survey again to change it.
              </p>
            )}
          </motion.section>
        )}

        {step === "role" && (
          <motion.section key="role" {...slide}>
            <div className="role-grid" role="radiogroup" aria-label="The role you are aiming for">
              {roles.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={item.id === roleId}
                  className="role-card surface interactive-card"
                  data-testid="survey-role"
                  onClick={() => pickRole(item.id)}
                >
                  <strong>{item.name}</strong>
                  <span>{item.summary}</span>
                  <small>{item.skills.length} skills on this path</small>
                </button>
              ))}
            </div>
            <div className="question-actions start-actions">
              <button type="button" className="ghost-button" onClick={() => setStep("choose")}>Back</button>
            </div>
          </motion.section>
        )}

        {step === "skills" && role && (
          <motion.section key="skills" className="survey-skills surface" {...slide}>
            <p className="detail-stage">Path to {role.name}</p>
            <div className="skill-picks" role="group" aria-label={`Skills on the path to ${role.name}`}>
              {role.skills.map((skill) => {
                const picked = known.has(skill.skill_id);
                return (
                  <button
                    key={skill.skill_id}
                    type="button"
                    className={`skill-pick${picked ? " picked" : ""}`}
                    data-testid="survey-skill"
                    aria-pressed={picked}
                    onClick={() => toggle(skill.skill_id)}
                  >
                    {picked && <CheckIcon width="12" height="12" />}
                    {skill.name}
                  </button>
                );
              })}
            </div>
            <p className="survey-count" role="status">
              {known.size === 0
                ? "Nothing ticked is a fine answer: everything starts as new."
                : `${known.size} ticked. They start as “basics” and recall checks them first.`}
            </p>
            <div className="question-actions start-actions">
              <button type="button" className="ghost-button" disabled={busy} onClick={() => setStep("role")}>Back</button>
              <button type="button" className="primary-button" data-testid="survey-finish" disabled={busy} onClick={() => void finish()}>
                {busy ? "Saving…" : "Continue to the questions"} <ArrowRightIcon width="18" height="18" />
              </button>
            </div>
          </motion.section>
        )}
      </AnimatePresence>
    </main>
  );
}
