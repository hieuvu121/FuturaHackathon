import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end config. Both halves of the app are started here, so a run needs
 * nothing set up by hand.
 *
 * The backend runs with MOCK_MODE=true: get_current_user then returns a fixed
 * demo user instead of demanding a GitHub OAuth round trip, and the roadmap
 * comes from backend/mock/roadmap.json. The concept grouping, the personalised
 * focus lines and the diagram are all exercised for real -- only the source of
 * the buckets is a fixture.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"]],
  use: {
    // Must be localhost, not 127.0.0.1: the backend CORS allowlist names this exact origin.
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // A throwaway database per run, so the recall attempt log starts empty and
      // a session cannot be exhausted by yesterday's run. Blank API keys force
      // the drill grader onto its deterministic key-point path: offline, free
      // and identical every time.
      command:
        "rm -f cache/e2e.db && ../backend/.venv/bin/python -m uvicorn app.main:app --port 8000",
      cwd: "../backend",
      env: {
        MOCK_MODE: "true",
        DATABASE_URL: "sqlite:///./cache/e2e.db",
        OPENAI_API_KEY: "",
        ANTHROPIC_API_KEY: "",
      },
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 3000",
      url: "http://localhost:3000/roadmap",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
