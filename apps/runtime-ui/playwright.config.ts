import { defineConfig } from "@playwright/test";

/**
 * Real browser, real Runtime, real Postgres: nothing is mocked, because the point is the path between them.
 * Use `pnpm test:e2e` after `pnpm -r build`. Each spec file owns one app and its database.
 */
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 120_000,
  reporter: [["list"]],
  globalSetup: "./tests/e2e/global-setup.ts",
});
