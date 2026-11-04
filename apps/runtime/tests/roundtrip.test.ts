/** R-22 and R-23 with the real worker: export, edit the file, re-import, apply, undo. */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import type { DaftarSpec } from "@daftar/spec/types";

import { createApp } from "../src/app.js";
import { parseSpec } from "../src/spec/loader.js";
import { Client, newDatabase, PASSWORD, userOf } from "./helpers.js";

const workerUrl = process.env.DAFTAR_TEST_WORKER_URL;
const root = new URL("../../../packages/spec/fixtures/generated/", import.meta.url);
const original = JSON.parse(readFileSync(new URL("daftar.spec.json", root), "utf8")) as DaftarSpec;
const seedDir = fileURLToPath(new URL("seed/", root));
const tool = fileURLToPath(new URL("workbook_tool.py", import.meta.url));
const repository = fileURLToPath(new URL("../../../", import.meta.url));
const directory = mkdtempSync(join(tmpdir(), "daftar-roundtrip-"));
const JANVIER = "Janvier 2026";

type Sheets = Record<string, Record<string, { value: unknown; formula: string | null }>>;

function python(...args: string[]): string {
  return execFileSync("uv", ["run", "python", tool, ...args], { cwd: repository, encoding: "utf8" });
}

function read(data: Uint8Array): Sheets {
  const path = join(directory, "read.xlsx");
  writeFileSync(path, data);
  return JSON.parse(python("read", path)) as Sheets;
}

function edited(data: Uint8Array, edits: unknown): Uint8Array<ArrayBuffer> {
  const path = join(directory, "edit.xlsx");
  writeFileSync(path, data);
  python("edit", path, JSON.stringify(edits));
  return new Uint8Array(readFileSync(path));
}

/** The app's state without what any write moves on: what an undo must bring back. */
async function snapshot(owner: Client): Promise<unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["eleves", "paiements", "parent"]) {
    const rows = (await owner.get(`/api/e/${key}?pageSize=200`)).body.rows as Record<string, unknown>[];
    out[key] = rows
      .map((row) => Object.fromEntries(Object.entries(row).filter(([name]) => !["_version", "_updatedAt", "_createdAt"].includes(name))))
      .sort((left, right) => String(left._id).localeCompare(String(right._id)));
  }
  return out;
}

async function bootApp(spec: DaftarSpec, url: string | undefined): Promise<{ base: string; close: () => Promise<void> }> {
  const { db, drop } = await newDatabase();
  const config = { secret: "s", timezone: "Africa/Algiers", processor: undefined, workerUrl: url };
  const app = await createApp({ spec: parseSpec(spec), db, config, seedDir });
  await app.listen(0, "127.0.0.1");
  const base = (await app.getUrl()).replace("[::1]", "127.0.0.1");
  return {
    base,
    close: async () => {
      await app.close();
      await drop();
    },
  };
}

async function sumOf(owner: Client, field: string, period: string): Promise<number> {
  const rows = (await owner.get("/api/e/paiements?pageSize=200")).body.rows as Record<string, number | string>[];
  return rows.filter((row) => String(row.period).startsWith(period)).reduce((total, row) => total + Number(row[field]), 0);
}

afterAll(() => rmSync(directory, { recursive: true, force: true }));

describe("without the worker", () => {
  it("says the Excel service isn't answering, in the user's words", async () => {
    const running = await bootApp(original, "http://127.0.0.1:9");
    const owner = new Client(running.base);
    await owner.post("/api/auth/setup", { username: "owner", password: PASSWORD });
    const response = await owner.upload("/api/import?name=a.xlsx", new Uint8Array([1, 2, 3]));
    expect(response.status).toBe(503);
    expect(response.body.reason.fr).toContain("Excel");
    expect((await owner.download("/api/export.xlsx")).status).toBe(503);
    await running.close();
  });
});

describe.runIf(workerUrl)("the round trip", () => {
  let owner: Client;
  let close: () => Promise<void>;
  let base: string;
  let exported: Uint8Array<ArrayBuffer>;

  beforeAll(async () => {
    const running = await bootApp(original, workerUrl);
    base = running.base;
    close = running.close;
    owner = new Client(base);
    await owner.post("/api/auth/setup", { username: "owner", password: PASSWORD });
    exported = (await owner.download("/api/export.xlsx")).data;
  }, 60_000);
  afterAll(() => close());

  it("exports the owner's layout, with the app's totals and live formulas", async () => {
    const response = await owner.download("/api/export.xlsx");
    expect(response.status).toBe(200);
    expect(response.type).toContain("spreadsheetml");
    const sheets = read(response.data);
    expect(Object.keys(sheets)).toEqual(["Élèves", JANVIER, "Février 2026", "Mars 2026", "Parent"]);
    const january = sheets[JANVIER] as Sheets[string];
    expect(["A3", "B3", "C3", "D3", "E3"].map((cell) => january[cell]?.value)).toEqual(["Matricule", "Dû", "Payé", "Reste", "Statut"]);
    expect(january.D4?.formula).toMatch(/^=/);
    expect(january.D5?.formula).toContain("5");
    expect(january.A4?.value).toBe("E000");
    // The row after the 12 January payments.
    const totals = january.B16;
    expect(totals?.formula).toMatch(/^=SUM\(B4:B15\)$/);
    expect(totals?.value).toBe(await sumOf(owner, "du", "2026-01"));
    expect(january.C16?.value).toBe(await sumOf(owner, "paye", "2026-01"));
    expect(january.D16?.value).toBe(await sumOf(owner, "reste", "2026-01"));
  });

  it("writes right-to-left sheets for Arabic", async () => {
    const sheets = read((await owner.download("/api/export.xlsx?locale=ar-DZ")).data);
    expect(sheets[JANVIER]?._rtl?.value).toBe(true);
  });

  it("finds nothing to do in a file nobody touched", async () => {
    const response = await owner.upload("/api/import?name=daftar.xlsx", exported);
    expect(response.status).toBe(201);
    expect(response.body.problems).toEqual([]);
    for (const part of Object.values<any>(response.body.entities)) expect(part).toEqual({ added: [], changed: [], missing: [] });
  });

  it("shows exactly the edits, applies them as one batch, and an undo brings everything back", async () => {
    const before = await snapshot(owner);
    const file = edited(exported, {
      set: { [JANVIER]: { C4: 1500, E5: "Payé" }, "Élèves": { A18: "E999", B18: "Nouvel Élève", C18: "BENALI", D18: "0555123456" } },
      deleteRow: { "Mars 2026": 6 },
    });
    const diff = await owner.upload("/api/import?name=edited.xlsx", file);
    expect(diff.status).toBe(201);
    expect(diff.body.problems).toEqual([]);
    const { eleves, paiements, parent } = diff.body.entities;
    expect(parent).toEqual({ added: [], changed: [], missing: [] });
    expect(eleves.changed).toEqual([]);
    expect(eleves.missing).toEqual([]);
    expect(eleves.added.map((item: any) => item.key)).toEqual(["E999"]);
    expect(paiements.added).toEqual([]);
    expect(paiements.changed.map((item: any) => [item.key, Object.keys(item.fields)])).toEqual([
      ["2026-01␟E000", ["paye"]],
      ["2026-01␟E001", ["statut"]],
    ]);
    expect(paiements.changed[0].fields.paye).toEqual([1000, 1500]);
    expect(paiements.changed[1].fields.statut).toEqual(["impaye", "paye"]);
    expect(paiements.missing.map((item: any) => item.key)).toEqual(["2026-03␟E002"]);

    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.status).toBe(200);
    expect(applied.body).toMatchObject({ added: 1, changed: 2, stale: [], problems: [] });

    const rows = (await owner.get("/api/e/paiements?pageSize=200")).body.rows as any[];
    const parents = (await owner.get("/api/e/parent?pageSize=50")).body.rows as any[];
    const students = (await owner.get("/api/e/eleves?pageSize=50")).body.rows as any[];
    const newcomer = students.find((row) => row.matricule === "E999");
    expect(newcomer.eleve).toBe("Nouvel Élève");
    expect(parents.map((row) => row._id)).toContain(newcomer.parent);
    const first = students.find((row) => row.matricule === "E000");
    const payment = rows.find((row) => row.matricule === first._id && row.period === "2026-01-01");
    // The computed column followed the edit.
    expect(payment.paye).toBe(1500);
    expect(payment.reste).toBe(payment.du - 1500);
    // R-23: a row deleted from the file is still here.
    expect(rows).toHaveLength(36);

    expect((await owner.post(`/api/batches/${applied.body.batchId}/undo`)).status).toBe(200);
    expect(await snapshot(owner)).toEqual(before);
  });

  it("applies only what was chosen, and a diff only once", async () => {
    const before = await snapshot(owner);
    const diff = await owner.upload("/api/import", edited(exported, { set: { [JANVIER]: { C4: 1234, C5: 2345 } } }));
    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, { selected: { paiements: { changed: ["2026-01␟E001"] } } });
    expect(applied.body).toMatchObject({ added: 0, changed: 1 });
    const rows = (await owner.get("/api/e/paiements?pageSize=200")).body.rows as any[];
    expect(rows.some((row) => row.paye === 2345)).toBe(true);
    expect(rows.some((row) => row.paye === 1234)).toBe(false);
    expect((await owner.post(`/api/import/${diff.body.diffId}/apply`, {})).status).toBe(404);
    await owner.post(`/api/batches/${applied.body.batchId}/undo`);
    expect(await snapshot(owner)).toEqual(before);
  });

  it("leaves a row someone edited after the comparison alone, and says so", async () => {
    const diff = await owner.upload("/api/import", edited(exported, { set: { [JANVIER]: { C4: 1111 } } }));
    const { id, version } = diff.body.entities.paiements.changed[0];
    const patched = await owner.patch(`/api/e/paiements/${id}`, { paye: 7777, _version: version });
    expect(patched.status).toBe(200);
    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.body).toMatchObject({ changed: 0, stale: ["2026-01␟E000"] });
    expect((await owner.get(`/api/e/paiements/${id}`)).body.paye).toBe(7777);
    expect((await owner.patch(`/api/e/paiements/${id}`, { paye: 1000, _version: version + 1 })).status).toBe(200);
  });

  it("refuses a bad value naming its row, writes nothing, and keeps the diff for another try", async () => {
    const before = await snapshot(owner);
    const diff = await owner.upload("/api/import", edited(exported, { set: { [JANVIER]: { C4: 1500 }, "Élèves": { D2: "pas un numéro" } } }));
    const row = diff.body.entities.eleves.changed[0];
    expect(row.fields.telephone_parent[1]).toBe("pasunnuméro");
    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.status).toBe(400);
    expect(applied.body).toMatchObject({ entity: "eleves", key: row.key });
    expect(applied.body.fields.telephone_parent.fr).toBeTruthy();
    expect(await snapshot(owner)).toEqual(before);
    const nothing = await owner.post(`/api/import/${diff.body.diffId}/apply`, { selected: {} });
    expect(nothing.body).toMatchObject({ added: 0, changed: 0 });
    expect(await snapshot(owner)).toEqual(before);
  });

  it("reports a link that names nothing and keeps the row's old link", async () => {
    const before = await snapshot(owner);
    const diff = await owner.upload("/api/import", edited(exported, { set: { "Élèves": { B2: "Renommé", C2: "PERSONNE" } } }));
    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.status).toBe(200);
    expect(applied.body.problems).toEqual([{ where: "E000", field: "parent", value: "PERSONNE" }]);
    const students = (await owner.get("/api/e/eleves?pageSize=50")).body.rows as any[];
    const first = students.find((row) => row.matricule === "E000");
    expect(first.eleve).toBe("Renommé");
    expect(first.parent).toBeTruthy();
    await owner.post(`/api/batches/${applied.body.batchId}/undo`);
    expect(await snapshot(owner)).toEqual(before);
  });

  it("tells a file it can't read in the user's words", async () => {
    const response = await owner.upload("/api/import?name=a.xlsx", new TextEncoder().encode("not a workbook"));
    expect(response.status).toBe(400);
    expect(response.body.reason.fr).toBeTruthy();
    expect(response.body.reason.ar).toBeTruthy();
  });

  it("needs a session and the permission, and a diff belongs to whoever made it", async () => {
    const anonymous = new Client(base);
    expect((await anonymous.download("/api/export.xlsx")).status).toBe(401);
    expect((await anonymous.upload("/api/import", exported)).status).toBe(401);
    // A form post isn't a way in: the raw route takes only a workbook's type.
    expect((await owner.upload("/api/import", exported, "text/plain")).status).toBeGreaterThanOrEqual(400);
    const diff = await owner.upload("/api/import", exported);
    const other = await userOf({ base } as never, owner, "owner", "second-owner");
    expect((await other.post(`/api/import/${diff.body.diffId}/apply`, {})).status).toBe(404);
    expect((await owner.post("/api/import/not-a-uuid/apply", {})).status).toBe(404);
  });
});

describe.runIf(workerUrl)("what new rows set off", () => {
  const spec = structuredClone(original) as any;
  const entityOf = (key: string): any => spec.entities.find((entity: any) => entity.key === key);
  const mappingOf = (key: string): any => spec.mapping.find((item: any) => item.entity === key);
  const label = { fr: "x", ar: "س" };
  entityOf("parent").fields.push(
    { key: "enfants", label, type: "child", target: "eleves", via: "parent" },
    { key: "nombre", label, type: "computed", resultType: "integer", computed: { eval: "translated", excel: "=0", deps: [], store: true, expr: { kind: "rollup", valueType: "number", via: "enfants", fn: "count" } } },
  );
  entityOf("eleves").fields.push({ key: "taille", label, type: "computed", resultType: "integer", computed: { eval: "engine", excel: "=LEN(A2)", deps: ["matricule"], store: true } });
  mappingOf("eleves").columns.push({ header: "Taille", field: "taille", column: "E" });
  let owner: Client;
  let close: () => Promise<void>;

  beforeAll(async () => {
    const running = await bootApp(spec as DaftarSpec, workerUrl);
    close = running.close;
    owner = new Client(running.base);
    await owner.post("/api/auth/setup", { username: "owner", password: PASSWORD });
  }, 60_000);
  afterAll(() => close());

  it("runs formulas, updates what counts them, and links a new row to another new row", async () => {
    const file = (await owner.download("/api/export.xlsx")).data;
    const diff = await owner.upload(
      "/api/import",
      edited(file, { set: { "Élèves": { A18: "E99999", B18: "Nouveau", C18: "NOUVEAU PARENT", A19: "E99998", B19: "Autre", C19: "NOUVEAU PARENT" }, Parent: { A6: "NOUVEAU PARENT" } } }),
    );
    expect(diff.body.problems).toEqual([]);
    const applied = await owner.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.body).toMatchObject({ added: 3, problems: [] });
    const students = (await owner.get("/api/e/eleves?pageSize=50")).body.rows as any[];
    const newcomer = students.find((row) => row.matricule === "E99999");
    expect(newcomer.taille).toBe(6);
    const parents = (await owner.get("/api/e/parent?pageSize=50")).body.rows as any[];
    const parent = parents.find((row) => row.nom === "NOUVEAU PARENT");
    expect(newcomer.parent).toBe(parent._id);
    expect(parent.nombre).toBe(2);
  });

  it("updates an existing row that counts a new one", async () => {
    const parents = (await owner.get("/api/e/parent?pageSize=50")).body.rows as any[];
    const existing = parents.find((row) => row.nom !== "NOUVEAU PARENT");
    const file = (await owner.download("/api/export.xlsx")).data;
    const diff = await owner.upload("/api/import", edited(file, { set: { "Élèves": { A20: "E99997", B20: "Encore", C20: existing.nom } } }));
    expect(diff.body.entities.eleves.added).toHaveLength(1);
    expect(diff.body.entities.parent.added).toEqual([]);
    expect((await owner.post(`/api/import/${diff.body.diffId}/apply`, {})).body).toMatchObject({ added: 1, problems: [] });
    expect((await owner.get(`/api/e/parent/${existing._id}`)).body.nombre).toBe(existing.nombre + 1);
  });
});

describe.runIf(workerUrl)("a role that may see only part of the data", () => {
  const spec = structuredClone(original);
  const payments = spec.entities.find((entity) => entity.key === "paiements");
  const owed = payments?.fields.find((field) => field.key === "du");
  if (owed) owed.level = 1;
  const staff = spec.roles.find((role) => role.key === "staff");
  if (staff) {
    staff.fieldLevel = 0;
    staff.permissions = [
      { entity: "paiements", actions: ["read", "update", "export", "import"], rowScope: "all" },
      { entity: "eleves", actions: ["read", "export"], rowScope: "own" },
    ];
  }
  const accountant = spec.roles.find((role) => role.key === "accountant");
  if (accountant) {
    accountant.fieldLevel = 0;
    accountant.permissions = [
      { entity: "paiements", actions: ["read", "update", "export", "import"], rowScope: "all" },
      { entity: "eleves", actions: ["read", "export"], rowScope: "all" },
    ];
  }
  let owner: Client;
  let worker: Client;
  let clerk: Client;
  let close: () => Promise<void>;
  let file: Uint8Array<ArrayBuffer>;

  beforeAll(async () => {
    const running = await bootApp(spec, workerUrl);
    close = running.close;
    owner = new Client(running.base);
    await owner.post("/api/auth/setup", { username: "owner", password: PASSWORD });
    worker = await userOf({ base: running.base } as never, owner, "staff");
    clerk = await userOf({ base: running.base } as never, owner, "accountant");
    file = (await worker.download("/api/export.xlsx")).data;
  }, 60_000);
  afterAll(() => close());

  it("masks hidden fields, writes values instead of formulas, and leaves out other people's rows", () => {
    const sheets = read(file);
    const january = sheets[JANVIER] as Sheets[string];
    expect(january.B4?.value).toBe("*");
    expect(Object.values(january).every((cell) => cell.formula === null || !/[A-Z]+\d/.test(cell.formula.replace(/SUM\([^)]*\)/, "")))).toBe(true);
    expect(january.D4?.formula).toBeNull();
    // No total over a column of masks.
    expect(january.B16).toBeUndefined();
    // Row scope: this user created no students. They aren't in the file, and neither are their keys.
    expect(Object.keys(sheets["Élèves"] ?? {}).filter((cell) => /^A\d+$/.test(cell) && cell !== "A1")).toEqual([]);
    expect(sheets.Parent).toBeUndefined();
    expect(JSON.stringify(sheets)).not.toContain("BENALI");
  });

  it("can't change what it can't see", async () => {
    const own = (await clerk.download("/api/export.xlsx")).data;
    const diff = await clerk.upload("/api/import", edited(own, { set: { [JANVIER]: { B4: 999999, C4: 1500 } } }));
    expect(diff.status).toBe(201);
    const change = diff.body.entities.paiements.changed.find((item: any) => item.fields.paye);
    expect(change.fields).toEqual({ paye: [1000, 1500] });
    expect(diff.body.problems).toContainEqual(expect.objectContaining({ field: "du", reason: "hidden" }));
    const applied = await clerk.post(`/api/import/${diff.body.diffId}/apply`, {});
    expect(applied.body).toMatchObject({ changed: 1, stale: [] });
    const row = (await owner.get(`/api/e/paiements/${change.id}`)).body;
    expect(row.paye).toBe(1500);
    expect(row.du).toBe(3000);
    // Undoing needs the revert right, which this role doesn't have.
    expect((await clerk.post(`/api/batches/${applied.body.batchId}/undo`)).status).toBe(403);
    expect((await owner.post(`/api/batches/${applied.body.batchId}/undo`)).status).toBe(200);
  });

  it("matches nothing when the key is a row this user can't see", async () => {
    const diff = await worker.upload("/api/import", file);
    expect(diff.status).toBe(201);
    expect(diff.body.entities.paiements).toMatchObject({ added: [], changed: [] });
    expect(diff.body.problems.length).toBeGreaterThan(0);
    expect(diff.body.problems.every((item: any) => item.field === "missingKey" || item.field === "duplicateKey")).toBe(true);
  });

  it("refuses a role with no export or import at all", async () => {
    const restricted = structuredClone(spec);
    const role = restricted.roles.find((item) => item.key === "staff");
    if (role) role.permissions = [{ entity: "paiements", actions: ["read"], rowScope: "all" }];
    const running = await bootApp(restricted, workerUrl);
    const boss = new Client(running.base);
    await boss.post("/api/auth/setup", { username: "owner", password: PASSWORD });
    const user = await userOf({ base: running.base } as never, boss, "staff");
    expect((await user.download("/api/export.xlsx")).status).toBe(403);
    expect((await user.upload("/api/import", file)).status).toBe(403);
    await running.close();
  }, 60_000);
});
