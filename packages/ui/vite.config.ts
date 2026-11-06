import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** Builds and serves the reference app in preview/, which draws every screen from the real components. */
export default defineConfig({
  root: fileURLToPath(new URL("./preview", import.meta.url)),
  base: "./",
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL("./dist", import.meta.url)),
    emptyOutDir: true,
    target: "es2022",
  },
  server: { port: 5174, strictPort: false },
  preview: { port: 5175, strictPort: true },
});
