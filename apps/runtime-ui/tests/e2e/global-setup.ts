/** Starts a Runtime from its real build for each example spec, on its own throwaway database, and a real preview. */
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

import pg from "pg";

import { APPS, PREVIEW_ENV } from "./helpers.js";

const ROOT = fileURLToPath(new URL("../../../../", import.meta.url));
const ADMIN = process.env.DAFTAR_TEST_DATABASE_URL ?? "postgres://postgres:test@127.0.0.1:5434/postgres";
/** An example spec, or one kept here because it covers what no example has. */
const specPath = (name: string): string => (name.startsWith("fixtures/") ? fileURLToPath(new URL(`${name}.spec.json`, import.meta.url)) : `${ROOT}packages/spec/examples/${name}.spec.json`);

async function admin<Result>(work: (client: pg.Client) => Promise<Result>): Promise<Result> {
  const client = new pg.Client({ connectionString: ADMIN });
  await client.connect();
  try {
    return await work(client);
  } finally {
    await client.end();
  }
}

async function ready(base: string): Promise<void> {
  for (let tries = 0; tries < 300; tries += 1) {
    try {
      if ((await fetch(`${base}/api/auth/status`)).ok) return;
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`${base} didn't start`);
}

function stopped(child: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (child.exitCode !== null) resolve();
    else {
      child.once("exit", () => resolve());
      child.kill("SIGTERM");
    }
  });
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  const children: ChildProcess[] = [];
  const databases: string[] = [];
  for (const { spec, port } of Object.values(APPS)) {
    const database = `e2e_${randomBytes(6).toString("hex")}`;
    await admin((client) => client.query(`CREATE DATABASE ${database}`));
    databases.push(database);
    const url = new URL(ADMIN);
    url.pathname = `/${database}`;
    const child = spawn("node", ["apps/runtime/dist/main.js"], {
      cwd: ROOT,
      stdio: ["ignore", "ignore", "inherit"],
      env: { PATH: process.env.PATH ?? "", PORT: String(port), DAFTAR_DATABASE_URL: url.toString(), DAFTAR_SPEC_PATH: specPath(spec), DAFTAR_SECRET: randomBytes(32).toString("hex") },
    });
    children.push(child);
    await ready(`http://127.0.0.1:${port}`);
  }
  const previewDatabase = `daftar_preview_${randomBytes(6).toString("hex")}`;
  const preview = spawn("node", ["apps/runtime/dist/preview.js"], {
    cwd: ROOT,
    stdio: ["pipe", "pipe", "inherit"],
    env: { PATH: process.env.PATH ?? "", DAFTAR_PREVIEW_ADMIN_URL: ADMIN, DAFTAR_PREVIEW_DATABASE: previewDatabase, DAFTAR_SPEC_PATH: specPath("repair-tracker") },
  });
  const line = await new Promise<string>((resolve, reject) => {
    preview.stdout?.once("data", (chunk: Buffer) => resolve(chunk.toString()));
    preview.once("exit", () => reject(new Error("the preview ended before it was ready")));
  });
  process.env[PREVIEW_ENV] = line.trim();
  return async () => {
    await Promise.all([...children, preview].map(stopped));
    await admin(async (client) => {
      for (const database of databases) await client.query(`DROP DATABASE IF EXISTS ${database} WITH (FORCE)`);
    });
  };
}
