import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** The UI the runtime serves from its own origin. In development, this server hands API calls on to a running runtime. */
export default defineConfig({
  plugins: [react()],
  build: { target: "es2022" },
  server: { port: 5180, proxy: { "/api": process.env.DAFTAR_DEV_API ?? "http://127.0.0.1:3000" } },
});
