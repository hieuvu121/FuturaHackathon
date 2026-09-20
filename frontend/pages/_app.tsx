import "@/styles/globals.css";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { AppProps } from "next/app";
import { Bricolage_Grotesque, Figtree, JetBrains_Mono } from "next/font/google";
import Head from "next/head";
import { useRouter } from "next/router";
import { useEffect, useRef, useState } from "react";

import AppShell from "@/components/AppShell";
import { EvidenceProvider } from "@/components/EvidenceViewer";

const heading = Bricolage_Grotesque({ subsets: ["latin"], weight: ["500", "700"], variable: "--font-heading" });
const body = Figtree({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-body" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-mono" });

const ORDER = ["/start", "/connect", "/recall", "/roadmap", "/share"];
const META: Record<string, { title: string; description: string }> = {
  "/start": { title: "Start | Retrace", description: "Connect your repositories, or answer a short survey, and get a roadmap built for you." },
  "/connect": { title: "Connect repositories | Retrace", description: "Choose the repositories that best represent your engineering work." },
  "/recall": { title: "Recall session | Retrace", description: "Revisit past code through supportive, evidence-based revision." },
  "/roadmap": { title: "Learning roadmap | Retrace", description: "Prioritise what to revise, deepen, and learn next." },
  "/share": { title: "Verified profile | Retrace", description: "Share engineering skills backed by exact source-code evidence." },
  "/404": { title: "Page not found | Retrace", description: "Return to your Retrace roadmap." },
};

function routeIndex(pathname: string) {
  const base = pathname.startsWith("/share") ? "/share" : pathname;
  const index = ORDER.indexOf(base);
  return index < 0 ? 0 : index;
}

export default function App({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const reduceMotion = useReducedMotion();
  const previousIndex = useRef(routeIndex(router.pathname));
  const [direction, setDirection] = useState(1);
  const metaKey = router.pathname.startsWith("/share") ? "/share" : router.pathname;
  const meta = META[metaKey] ?? { title: "Retrace", description: "Engineering capability, backed by evidence." };

  useEffect(() => {
    function handleRouteStart(url: string) {
      const nextIndex = routeIndex(url.split("?")[0]);
      setDirection(nextIndex >= previousIndex.current ? 1 : -1);
      previousIndex.current = nextIndex;
    }
    router.events.on("routeChangeStart", handleRouteStart);
    return () => router.events.off("routeChangeStart", handleRouteStart);
  }, [router.events]);

  const variants = {
    enter: (dir: number) => reduceMotion ? { opacity: 1 } : { opacity: 0, y: dir > 0 ? 44 : -44 },
    center: { opacity: 1, y: 0 },
    exit: (dir: number) => reduceMotion ? { opacity: 1 } : { opacity: 0, y: dir > 0 ? -44 : 44 },
  };

  return (
    <div className={`${heading.variable} ${body.variable} ${mono.variable}`}>
      <Head>
        <title>{meta.title}</title>
        <meta name="description" content={meta.description} />
        <meta property="og:title" content={meta.title} />
        <meta property="og:description" content={meta.description} />
        <meta property="og:type" content="website" />
        <meta property="og:image" content="/og-retrace.svg" />
        <meta name="twitter:card" content="summary_large_image" />
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </Head>
      <EvidenceProvider>
      <AppShell>
        <AnimatePresence mode="popLayout" initial={false} custom={direction}>
          <motion.div key={router.pathname} custom={direction} variants={variants} initial="enter" animate="center" exit="exit" transition={{ duration: reduceMotion ? 0 : 0.5, ease: [0.77, 0, 0.18, 1] }}>
            <Component {...pageProps} />
          </motion.div>
        </AnimatePresence>
      </AppShell>
      </EvidenceProvider>
    </div>
  );
}
