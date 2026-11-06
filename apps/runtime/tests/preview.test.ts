import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { sql } from "kysely";
import { afterAll, describe, expect, it } from "vitest";

import { createDb } from "../src/db.js";
import { startPreview } from "../src/preview-server.js";
import { example } from "./helpers.js";

const ADMIN = process.env.DAFTAR_TEST_DATABASE_URL ?? "postgres://postgres:test@127.0.0.1:5434/postgres";

describe("the operator's preview", () => {
  const folder = mkdtempSync(join(tmpdir(), "daftar-preview-"));
  afterAll(() => rmSync(folder, { recursive: true, force: true }));

  const exists = async (name: string): Promise<boolean> => {
    const admin = createDb(ADMIN);
    const { rows } = await sql<{ n: number }>`SELECT count(*)::int AS n FROM pg_database WHERE datname = ${name}`.execute(admin);
    await admin.destroy();
    return rows[0]?.n === 1;
  };

  it("runs on the generated data, signed in, and leaves nothing behind", async () => {
    const specPath = join(folder, "daftar.spec.json");
    writeFileSync(specPath, JSON.stringify(example("tutoring-register")));
    mkdirSync(join(folder, "seed"));
    writeFileSync(join(folder, "seed", "classes.jsonl"), `${JSON.stringify({ code: "MATH", name: "Maths", monthly_fee: 1000 })}\n`);
    const name = "daftar_preview_test";
    const preview = await startPreview({ adminUrl: ADMIN, databaseName: name, specPath });
    try {
      expect(await exists(name)).toBe(true);
      const base = `http://127.0.0.1:${preview.port}`;
      const signedIn = { headers: { Cookie: preview.cookie } };
      expect((await (await fetch(`${base}/api/auth/me`, signedIn)).json()).role).toBe("owner");
      const list = await (await fetch(`${base}/api/e/classes`, signedIn)).json();
      expect(list.rows.map((row: { code: string }) => row.code)).toEqual(["MATH"]);
      expect((await fetch(`${base}/api/auth/me`)).status).toBe(401);
      // Another Runtime on this host, whose cookie this browser also sends, must not be touched.
      expect(preview.cookie.startsWith(`${name}=`)).toBe(true);
      expect((await fetch(`${base}/api/auth/me`, { headers: { Cookie: preview.cookie.replace(name, "daftar_session") } })).status).toBe(401);
      expect((await (await fetch(`${base}/api/auth/status`)).json()).preview).toBe(true);
    } finally {
      await preview.stop();
    }
    expect(await exists(name)).toBe(false);
  });

  it("starts again after a crash left its database, with no old data", async () => {
    const specPath = join(folder, "daftar.spec.json");
    writeFileSync(specPath, JSON.stringify(example("tutoring-register")));
    rmSync(join(folder, "seed"), { recursive: true, force: true });
    const name = "daftar_preview_crash";
    const admin = createDb(ADMIN);
    await sql`DROP DATABASE IF EXISTS ${sql.ref(name)} WITH (FORCE)`.execute(admin);
    await sql`CREATE DATABASE ${sql.ref(name)}`.execute(admin);
    await admin.destroy();
    const preview = await startPreview({ adminUrl: ADMIN, databaseName: name, specPath });
    const list = await (await fetch(`http://127.0.0.1:${preview.port}/api/e/classes`, { headers: { Cookie: preview.cookie } })).json();
    expect(list.total).toBe(0);
    await preview.stop();
  });

  it("refuses a database name that isn't a plain name", async () => {
    await expect(startPreview({ adminUrl: ADMIN, databaseName: 'x"; DROP DATABASE y; --', specPath: "/nope" })).rejects.toThrow("unsafe");
  });
});
