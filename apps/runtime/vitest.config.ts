import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Each test file gets its own database, but the engine and bcrypt-style hashing are slow to start.
    testTimeout: 60_000,
    hookTimeout: 120_000,
    fileParallelism: false,
  },
});
