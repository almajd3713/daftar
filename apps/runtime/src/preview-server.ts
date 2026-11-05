/**
 * The operator's preview (R-14): a Runtime on a throwaway database with the generated data.
 * Only the Studio starts it, and client images leave it out (D-9).
 */
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";

import type { INestApplication } from "@nestjs/common";
import { sql } from "kysely";

import { createApp } from "./app.js";
import { createDb, type Db } from "./db.js";
import { loadSpec } from "./spec/loader.js";

const SAFE_NAME = /^[a-z][a-z0-9_]{0,62}$/;

export interface PreviewOptions {
  adminUrl: string;
  databaseName: string;
  specPath: string;
}

export interface Preview {
  port: number;
  /** The throwaway owner's session, as `name=value`. */
  cookie: string;
  stop: () => Promise<void>;
}

async function dropDatabase(admin: Db, name: string): Promise<void> {
  await sql`DROP DATABASE IF EXISTS ${sql.ref(name)} WITH (FORCE)`.execute(admin);
}

export async function startPreview(options: PreviewOptions): Promise<Preview> {
  if (!SAFE_NAME.test(options.databaseName)) throw new Error("unsafe preview database name");
  const spec = loadSpec(options.specPath);
  const admin = createDb(options.adminUrl);
  let db: Db | undefined;
  let app: INestApplication | undefined;
  const stop = async (): Promise<void> => {
    await app?.close();
    await db?.destroy();
    await dropDatabase(admin, options.databaseName);
    await admin.destroy();
  };
  try {
    // A preview that crashed may have left its database. Nothing in it is worth keeping.
    await dropDatabase(admin, options.databaseName);
    await sql`CREATE DATABASE ${sql.ref(options.databaseName)}`.execute(admin);
    const url = new URL(options.adminUrl);
    url.pathname = `/${options.databaseName}`;
    db = createDb(url.toString());
    const seedDir = join(dirname(options.specPath), "seed");
    app = await createApp({
      spec,
      db,
      seedDir: existsSync(seedDir) ? seedDir : undefined,
      config: {
        secret: randomBytes(32).toString("hex"),
        timezone: spec.app.timezone,
        processor: "Aperçu",
      },
    });
    await app.listen(0, "127.0.0.1");
    const port = Number(new URL((await app.getUrl()).replace("[::1]", "127.0.0.1")).port);
    // Nobody ever types this password, and it goes with the database.
    const response = await fetch(`http://127.0.0.1:${port}/api/auth/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "apercu", password: randomBytes(24).toString("hex") }),
    });
    const cookie = response.headers.get("set-cookie")?.split(";")[0];
    if (response.status !== 201 || !cookie) throw new Error(`preview setup failed: ${response.status}`);
    return { port, cookie, stop };
  } catch (error) {
    await stop();
    throw error;
  }
}
