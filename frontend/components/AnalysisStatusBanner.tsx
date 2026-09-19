import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getPortfolio } from "@/lib/data";
import type { PortfolioRepo } from "@/lib/types";

export default function AnalysisStatusBanner() {
  const [repositories, setRepositories] = useState<PortfolioRepo[]>([]);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    async function poll() {
      let delay = 10_000;
      try {
        const portfolio = await getPortfolio();
        if (active) {
          setRepositories(portfolio.repositories);
          if (portfolio.repositories.some((repo) => !["done", "not_started", "failed"].includes(repo.stage))) {
            delay = 2500;
          }
        }
      } catch {
        if (active) setRepositories([]);
      }
      if (active) timer = window.setTimeout(poll, delay);
    }
    void poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  const state = useMemo(() => {
    const failed = repositories.filter((repo) => repo.stage === "failed");
    if (failed.length) return { failed: true, progress: 0, count: failed.length };
    const running = repositories.filter((repo) => !["done", "not_started"].includes(repo.stage));
    if (!running.length) return null;
    return {
      failed: false,
      progress: Math.round(running.reduce((sum, repo) => sum + repo.progress, 0) / running.length),
      count: running.length,
    };
  }, [repositories]);

  if (!state) return null;
  return (
    <Link className={`analysis-banner${state.failed ? " failed" : ""}`} href="/connect" role="status">
      <span>{state.failed ? `${state.count} analyses need attention` : `Analysing ${state.count} repositories`}</span>
      {!state.failed && <strong>{state.progress}%</strong>}
    </Link>
  );
}
