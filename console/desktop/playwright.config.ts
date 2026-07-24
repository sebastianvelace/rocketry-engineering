import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:1421",
    browserName: "chromium",
    channel: "chrome",
    viewport: { width: 1440, height: 900 },
    colorScheme: "dark",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "pnpm exec vite --port 1421",
    url: "http://127.0.0.1:1421",
    reuseExistingServer: false,
    env: {
      VITE_GATEWAY_URL: "http://gateway.test",
      VITE_GATEWAY_TOKEN: "e2e-token",
      VITE_WORKSPACE: "/workspace/rocketry-portfolio",
    },
  },
});
