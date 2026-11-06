import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { example, start, type Running } from "./helpers.js";

const PAGE = '<!doctype html><div id="root"></div>';

function builtUi(): string {
  const dir = mkdtempSync(join(tmpdir(), "daftar-ui-"));
  mkdirSync(join(dir, "assets"));
  writeFileSync(join(dir, "index.html"), PAGE);
  writeFileSync(join(dir, "assets", "app-abc123.js"), "export {};");
  return dir;
}

describe("the UI, served from the API's own origin", () => {
  let running: Running;
  let dir: string;
  beforeAll(async () => {
    dir = builtUi();
    running = await start(example("repair-tracker"), undefined, { uiDir: dir });
  });
  afterAll(async () => {
    await running.close();
    rmSync(dir, { recursive: true });
  });

  it("gives the app's page at the root, and at a deep link the browser's router will read", async () => {
    for (const path of ["/", "/v/repairs_all", "/e/repairs/new"]) {
      const response = await fetch(`${running.base}${path}`);
      expect(response.status, path).toBe(200);
      expect(response.headers.get("content-type"), path).toContain("text/html");
      expect(await response.text(), path).toBe(PAGE);
    }
  });

  it("still answers the API as JSON, and doesn't turn an unknown API path into a page", async () => {
    const status = await fetch(`${running.base}/api/auth/status`);
    expect(status.status).toBe(200);
    expect(status.headers.get("content-type")).toContain("application/json");
    const missing = await fetch(`${running.base}/api/nothing-here`);
    expect(missing.status).toBe(404);
    expect(missing.headers.get("content-type")).toContain("application/json");
  });

  it("keeps hashed files for good, and the page never past a release", async () => {
    const asset = await fetch(`${running.base}/assets/app-abc123.js`);
    expect(asset.status).toBe(200);
    expect(asset.headers.get("cache-control")).toContain("immutable");
    expect(asset.headers.get("x-content-type-options")).toBe("nosniff");
    expect((await fetch(`${running.base}/`)).headers.get("cache-control")).toBe("no-cache");
  });

  it("answers 404 for a missing file, because a script tag handed a page fails confusingly", async () => {
    for (const path of ["/assets/gone-123.js", "/gone.js", "/favicon.ico"]) {
      const response = await fetch(`${running.base}${path}`);
      expect(response.status, path).toBe(404);
      expect(await response.text(), path).not.toContain('id="root"');
    }
  });

  it("doesn't let a path climb out of the build folder", async () => {
    const response = await fetch(`${running.base}/assets/..%2f..%2f..%2f..%2f..%2fetc%2fpasswd`);
    expect(response.ok).toBe(false);
    expect(await response.text()).not.toContain("root:");
  });

  it("gives a page only to a read", async () => {
    const response = await fetch(`${running.base}/v/repairs_all`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    expect(response.status).toBe(404);
  });

  it("can't be framed, and runs only its own scripts", async () => {
    const { headers } = await fetch(`${running.base}/`);
    expect(headers.get("x-frame-options")).toBe("DENY");
    const policy = headers.get("content-security-policy");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("script-src 'self'");
    expect(policy).not.toMatch(/script-src[^;]*unsafe/);
  });
});

describe("the Studio's preview", () => {
  let running: Running;
  let dir: string;
  beforeAll(async () => {
    dir = builtUi();
    running = await start(example("repair-tracker"), undefined, { uiDir: dir, previewCookie: "daftar_preview_test" });
  });
  afterAll(async () => {
    await running.close();
    rmSync(dir, { recursive: true });
  });

  it("can be framed, because the Studio embeds it", async () => {
    const { headers } = await fetch(`${running.base}/`);
    expect(headers.get("x-frame-options")).toBeNull();
    expect(headers.get("content-security-policy")).not.toContain("frame-ancestors");
  });
});

describe("a runtime with no UI built", () => {
  let running: Running;
  beforeAll(async () => {
    running = await start(example("repair-tracker"));
  });
  afterAll(() => running.close());

  it("still serves its API", async () => {
    expect((await fetch(`${running.base}/api/auth/status`)).status).toBe(200);
    expect((await fetch(`${running.base}/`)).status).toBe(404);
  });
});
