import { defineConfig, devices } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

const testDir = defineBddConfig({
  features: "../../features/web/**/*.feature",
  featuresRoot: "../../features/web",
  steps: "e2e/**/*.ts",
  // S16、S19 的步驟定義在各自步驟才撰寫；閘門以 --grep 只執行目前與已完成的步驟
  missingSteps: "fail-on-run",
});

const PORT = 3100;

export default defineConfig({
  testDir,
  timeout: 60_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${PORT}`,
    viewport: { width: 1280, height: 900 },
  },
  webServer: {
    command: `npx next dev -p ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    // 後端位址指向不存在的埠：E2E 一律以 page.route mock /api/*（spec 0015）
    env: { API_BASE_URL: "http://127.0.0.1:9", NEXT_PUBLIC_DEMO_PROJECT_ID: "demo" },
  },
});
