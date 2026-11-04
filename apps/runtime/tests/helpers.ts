import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";

import type { INestApplication } from "@nestjs/common";
import { sql } from "kysely";

import type { DaftarSpec } from "@daftar/spec/types";

import { createApp } from "../src/app.js";
import { createDb, type Db } from "../src/db.js";
import { parseSpec } from "../src/spec/loader.js";

const ADMIN = process.env.DAFTAR_TEST_DATABASE_URL ?? "postgres://postgres:test@127.0.0.1:5434/postgres";

export function example(name: string): DaftarSpec {
  const text = readFileSync(new URL(`../../../packages/spec/examples/${name}.spec.json`, import.meta.url), "utf8");
  return parseSpec(JSON.parse(text));
}

export interface Running {
  app: INestApplication;
  db: Db;
  base: string;
  close: () => Promise<void>;
  name: string;
}

export async function newDatabase(): Promise<{ db: Db; name: string; drop: () => Promise<void> }> {
  const name = `t_${randomBytes(6).toString("hex")}`;
  const admin = createDb(ADMIN);
  await sql`CREATE DATABASE ${sql.ref(name)}`.execute(admin);
  const url = new URL(ADMIN);
  url.pathname = `/${name}`;
  const db = createDb(url.toString());
  return {
    db,
    name,
    drop: async () => {
      await db.destroy();
      // destroy() asks each connection to close without waiting for the server to finish. FORCE would
      // kill one still on its way out, and that client, out of the pool, has nobody to take the error.
      for (let tries = 0; tries < 100; tries += 1) {
        const { rows } = await sql<{ open: number }>`SELECT count(*)::int AS open FROM pg_stat_activity WHERE datname = ${name}`.execute(admin);
        if (!rows[0]?.open) break;
        await new Promise((resolve) => setTimeout(resolve, 20));
      }
      await sql`DROP DATABASE ${sql.ref(name)} WITH (FORCE)`.execute(admin);
      await admin.destroy();
    },
  };
}

export async function start(spec: DaftarSpec, clock?: () => Date): Promise<Running> {
  const { db, name, drop } = await newDatabase();
  const app = await createApp({ spec, db, clock, config: { secret: "test-secret-value", timezone: "Africa/Algiers", processor: "Atelier de test" } });
  await app.listen(0, "127.0.0.1");
  const base = await app.getUrl();
  return {
    app,
    db,
    name,
    base: base.replace("[::1]", "127.0.0.1"),
    close: async () => {
      await app.close();
      await drop();
    },
  };
}

export interface Response {
  status: number;
  body: any;
  text: string;
}

/** A signed-in browser: it keeps its session cookie. */
export class Client {
  private cookie = "";

  constructor(private readonly base: string) {}

  async request(method: string, path: string, body?: unknown): Promise<Response> {
    const response = await fetch(`${this.base}${path}`, {
      method,
      headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), Cookie: this.cookie },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const setCookie = response.headers.get("set-cookie");
    if (setCookie) this.cookie = setCookie.split(";")[0] as string;
    const text = await response.text();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    return { status: response.status, body: parsed, text };
  }

  /** A file, as a browser's fetch sends it. */
  async upload(path: string, data: Uint8Array<ArrayBuffer>, type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): Promise<Response> {
    const response = await fetch(`${this.base}${path}`, { method: "POST", headers: { "Content-Type": type, Cookie: this.cookie }, body: data });
    const text = await response.text();
    return { status: response.status, body: text ? JSON.parse(text) : null, text };
  }

  async download(path: string): Promise<{ status: number; type: string | null; data: Uint8Array<ArrayBuffer> }> {
    const response = await fetch(`${this.base}${path}`, { headers: { Cookie: this.cookie } });
    return { status: response.status, type: response.headers.get("content-type"), data: new Uint8Array(await response.arrayBuffer()) };
  }

  get = (path: string) => this.request("GET", path);
  post = (path: string, body: unknown = {}) => this.request("POST", path, body);
  patch = (path: string, body: unknown) => this.request("PATCH", path, body);
  del = (path: string) => this.request("DELETE", path);
}

export const PASSWORD = "un-mot-de-passe-long";

export async function ownerOf(running: Running): Promise<Client> {
  const owner = new Client(running.base);
  const response = await owner.post("/api/auth/setup", { username: "owner", password: PASSWORD });
  if (response.status !== 201) throw new Error(`setup failed: ${response.text}`);
  return owner;
}

export async function userOf(running: Running, owner: Client, role: string, username = role): Promise<Client> {
  const created = await owner.post("/api/auth/users", { username, password: PASSWORD, role });
  if (created.status !== 201) throw new Error(`user failed: ${created.text}`);
  const client = new Client(running.base);
  await client.post("/api/auth/login", { username, password: PASSWORD });
  return client;
}
