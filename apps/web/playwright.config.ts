import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    channel: "msedge"
  },
  webServer: [
    {
      command: "npm run dev -- --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      command: "python -m research_agent.runtime --host 127.0.0.1 --port 8787 --jobs-root runtime_data/web-jobs",
      cwd: "../..",
      url: "http://127.0.0.1:8787/api/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { ...process.env, PYTHONUTF8: "1" }
    }
  ]
});
