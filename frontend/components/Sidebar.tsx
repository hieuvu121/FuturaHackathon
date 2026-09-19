import { motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/router";
import { useEffect, useState } from "react";

import { getCurrentUser } from "@/lib/data";
import { ConnectIcon, RecallIcon, RoadmapIcon, ShareIcon } from "./Icons";

export const NAV_ITEMS = [
  { href: "/connect", label: "Connect", icon: ConnectIcon },
  { href: "/recall", label: "Recall", icon: RecallIcon },
  { href: "/roadmap", label: "Roadmap", icon: RoadmapIcon },
  { href: "/share/demo", label: "Share", icon: ShareIcon },
] as const;

function Logo() {
  return (
    <Link href="/connect" className="brand-link" aria-label="Retrace home">
      <span className="brand-mark"><RecallIcon width="22" height="22" /></span>
      <span>Retrace</span>
    </Link>
  );
}

function UserChip({ login }: { login: string }) {
  const initials = login.slice(0, 2).toUpperCase() || "GH";
  return (
    <div className="user-chip">
      <span className="avatar" aria-hidden="true">{initials}</span>
      <span><strong>@{login || "not-connected"}</strong><small><i aria-hidden="true" />{login ? "GitHub connected" : "Connect GitHub"}</small></span>
    </div>
  );
}

function normalizePath(path: string) {
  const pathname = path.split("?")[0];
  return pathname.startsWith("/share") ? "/share/demo" : pathname;
}

function Navigation({ activePath, reduceMotion, variant }: { activePath: string; reduceMotion: boolean | null; variant: "sidebar" | "topbar" }) {
  return (
    <nav aria-label="Primary navigation" className="nav-list">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = activePath === href;
        return (
          <Link key={href} href={href} prefetch className={`nav-link${active ? " active" : ""}`} aria-current={active ? "page" : undefined}>
            {active && <motion.span layoutId={`active-nav-pill-${variant}`} className="nav-active-pill" transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 430, damping: 38 }} />}
            <Icon className="nav-icon" width="20" height="20" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export default function Sidebar() {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const [pendingPath, setPendingPath] = useState<string | null>(null);
  const [login, setLogin] = useState("");
  const activePath = pendingPath ?? normalizePath(router.pathname);

  useEffect(() => {
    getCurrentUser().then((user) => setLogin(user.user)).catch(() => setLogin(""));
  }, []);

  useEffect(() => {
    const handleStart = (url: string) => setPendingPath(normalizePath(url));
    const handleDone = () => setPendingPath(null);
    router.events.on("routeChangeStart", handleStart);
    router.events.on("routeChangeComplete", handleDone);
    router.events.on("routeChangeError", handleDone);
    return () => {
      router.events.off("routeChangeStart", handleStart);
      router.events.off("routeChangeComplete", handleDone);
      router.events.off("routeChangeError", handleDone);
    };
  }, [router.events]);

  return (
    <>
      <aside className="sidebar"><Logo /><Navigation activePath={activePath} reduceMotion={reduceMotion} variant="sidebar" /><UserChip login={login} /></aside>
      <header className="topbar"><Logo /><Navigation activePath={activePath} reduceMotion={reduceMotion} variant="topbar" /><UserChip login={login} /></header>
    </>
  );
}
