import { defineConfig } from "@playwright/test";

/**
 * Drives the built reference app. Use `pnpm test:browser`, which builds first. The server only serves dist/,
 * so a preview left running still shows the new build: building here instead would skip it, and test old code.
 */
export default defineConfig({
  testDir: "tests/browser",
  timeout: 120_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:5175" },
  webServer: {
    command: "pnpm exec vite preview --host 127.0.0.1",
    url: "http://127.0.0.1:5175",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
