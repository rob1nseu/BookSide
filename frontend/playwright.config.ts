import { defineConfig } from "@playwright/test";
import path from "node:path";
import os from "node:os";
const python = path.resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./e2e",
  outputDir: path.join(os.tmpdir(), "bookside-playwright-results"),
  timeout: 45000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5173",
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: `"${python}" ../scripts/e2e_server.py`,
      url: "http://127.0.0.1:8765/api/health",
      reuseExistingServer: process.env.BOOKSIDE_E2E_EXTERNAL === '1',
      timeout: 60000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: process.env.BOOKSIDE_E2E_EXTERNAL === '1',
      timeout: 60000,
    },
  ],
});
