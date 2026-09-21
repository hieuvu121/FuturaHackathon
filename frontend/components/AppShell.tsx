import type { ReactNode } from "react";

import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <div className="ambient" aria-hidden="true">
        <span className="blob blob-blue" />
        <span className="blob blob-mint" />
        <span className="blob blob-peach" />
      </div>
      <Sidebar />
      <div id="main-content" className="app-content" tabIndex={-1}>{children}</div>
    </div>
  );
}
