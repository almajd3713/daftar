/**
 * Serves the built UI from the API's own origin, so the session cookie just works and nothing needs CORS.
 * Paths other than /api and /assets belong to the browser's router, so they all get the app's one page.
 */
import { existsSync } from "node:fs";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import type { NestExpressApplication } from "@nestjs/platform-express";
import { static as serveStatic, type NextFunction, type Request, type Response } from "express";

const HERE = fileURLToPath(new URL(".", import.meta.url));

/** In an image the UI sits beside `dist/`. In a checkout it's the UI package's own build, which is how a preview finds it. */
export function findUiDir(): string | undefined {
  return [join(HERE, "../ui"), join(HERE, "../../runtime-ui/dist")].find((dir) => existsSync(join(dir, "index.html")));
}

// Mantine writes its theme into a <style> and sizes through style attributes, so styles have to allow inline.
const POLICY = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
].join("; ");

function isPage(request: Request): boolean {
  if (request.method !== "GET" && request.method !== "HEAD") return false;
  if (request.path === "/api" || request.path.startsWith("/api/")) return false;
  // A missing file stays a 404: a script tag handed a web page fails in a far more confusing way.
  return extname(request.path) === "";
}

/** `framable` is only for the Studio's preview, which it embeds (D-9). A delivered app can't be framed. */
export function serveUi(app: NestExpressApplication, dir: string, framable: boolean): void {
  // Their names carry a hash, so a browser can keep them for good.
  app.use(
    "/assets",
    serveStatic(join(dir, "assets"), {
      immutable: true,
      maxAge: "1y",
      index: false,
      fallthrough: false,
      setHeaders: (response) => response.setHeader("X-Content-Type-Options", "nosniff"),
    }),
  );
  app.use((request: Request, response: Response, next: NextFunction) => {
    if (!isPage(request)) {
      next();
      return;
    }
    // The page names the hashed files, so it must never be kept past a new release.
    response.setHeader("Cache-Control", "no-cache");
    response.setHeader("X-Content-Type-Options", "nosniff");
    response.setHeader("Referrer-Policy", "same-origin");
    response.setHeader("Content-Security-Policy", framable ? POLICY : `${POLICY}; frame-ancestors 'none'`);
    if (!framable) response.setHeader("X-Frame-Options", "DENY");
    response.sendFile("index.html", { root: dir }, (error) => {
      if (error) next(error);
    });
  });
}
