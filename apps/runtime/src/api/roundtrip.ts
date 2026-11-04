/** R-22 and R-23: the runtime prepares the data and asks the worker for the Excel side of it. */
import { HttpException, HttpStatus } from "@nestjs/common";
import { sql } from "kysely";

import type { DaftarSpec, Entity } from "@daftar/spec/types";

import { column, tableOf, type Db, type Tx } from "../db.js";
import { Forbidden, MESSAGES, NotFound } from "../errors.js";
import { can, canSeeField, ownOnly, type User } from "../records/access.js";
import { MASK, type ImportPlan, type RecordService, type SeedProblem } from "../records/service.js";

/** A diff holds rows of the firm's data, so one nobody applied doesn't stay around. */
const DIFF_KEPT_DAYS = 7;

class WorkerUnavailable extends HttpException {
  constructor() {
    super({ reason: MESSAGES.workerUnavailable }, HttpStatus.SERVICE_UNAVAILABLE);
  }
}

function exportable(spec: DaftarSpec, user: User): Entity[] {
  return spec.entities.filter((entity) => can(spec, user, entity.key, "export") && can(spec, user, entity.key, "read"));
}

/** Comparing shows the current values, so an import needs read too. */
function importable(spec: DaftarSpec, user: User): Entity[] {
  return spec.entities.filter((entity) => can(spec, user, entity.key, "import") && can(spec, user, entity.key, "read"));
}

/** What a link shows in a sheet: the target's first key column, which a re-import can match. */
function linkKey(spec: DaftarSpec, target: string): string | undefined {
  const mapping = spec.mapping.find((item) => item.entity === target);
  return mapping?.keyColumns[0] ?? spec.entities.find((entity) => entity.key === target)?.titleField;
}

/** Labels of a link's targets, or null when this user may not read them (R-17). */
async function linkLabels(db: Db, spec: DaftarSpec, user: User, target: string): Promise<Map<unknown, unknown> | null> {
  const key = linkKey(spec, target);
  const field = spec.entities.find((entity) => entity.key === target)?.fields.find((item) => item.key === key);
  if (!key || !field || !can(spec, user, target, "read") || !canSeeField(spec, user, field)) return null;
  let query = db.selectFrom(tableOf(target)).select(["_id", column(key).as("label")]);
  if (ownOnly(spec, user, target)) query = query.where("_created_by", "=", user.id);
  const rows = await query.execute();
  return new Map(rows.map((row) => [row._id, row.label]));
}

async function rowsFor(db: Db, spec: DaftarSpec, user: User, entity: Entity): Promise<Record<string, unknown>[]> {
  let query = db.selectFrom(tableOf(entity.key)).selectAll();
  if (ownOnly(spec, user, entity.key)) query = query.where("_created_by", "=", user.id);
  const rows = await query.orderBy("_seq").execute();
  const labels = new Map<string, Map<unknown, unknown> | null>();
  for (const field of entity.fields) {
    if (field.type === "link") labels.set(field.key, await linkLabels(db, spec, user, field.target));
  }
  return rows.map((row) => {
    const out: Record<string, unknown> = { _id: row._id, _version: row._version };
    for (const field of entity.fields) {
      if (field.type === "child") continue;
      const shown = labels.get(field.key);
      // R-17: hidden fields are masked in exports too.
      if (!canSeeField(spec, user, field) || shown === null) out[field.key] = MASK;
      else if (field.type === "link") out[field.key] = shown?.get(row[field.key]) ?? null;
      else out[field.key] = row[field.key] ?? null;
    }
    return out;
  });
}

async function collect(db: Db, spec: DaftarSpec, user: User, entities: Entity[]): Promise<Record<string, Record<string, unknown>[]>> {
  const rows: Record<string, Record<string, unknown>[]> = {};
  for (const entity of entities) rows[entity.key] = await rowsFor(db, spec, user, entity);
  return rows;
}

function scopedSpec(spec: DaftarSpec, entities: Entity[]): DaftarSpec {
  const keys = new Set(entities.map((entity) => entity.key));
  return { ...spec, mapping: spec.mapping.filter((item) => keys.has(item.entity)) };
}

/** Formulas can rebuild what's left out from what's left in, so they ship only with the whole data. */
function seesEverything(spec: DaftarSpec, user: User, entities: Entity[]): boolean {
  if (entities.length < spec.entities.length) return false;
  return entities.every((entity) => !ownOnly(spec, user, entity.key) && entity.fields.every((field) => canSeeField(spec, user, field)));
}

async function callWorker(url: string | undefined, path: string, init: RequestInit): Promise<Response> {
  if (!url) throw new WorkerUnavailable();
  try {
    return await fetch(`${url}${path}`, init);
  } catch {
    throw new WorkerUnavailable();
  }
}

export interface RoundTripConfig {
  workerUrl?: string | undefined;
  timezone: string;
}

export async function exportWorkbook(db: Db, spec: DaftarSpec, user: User, config: RoundTripConfig, locale?: string): Promise<Buffer> {
  const entities = exportable(spec, user);
  if (!entities.length) throw new Forbidden();
  const response = await callWorker(config.workerUrl, "/v1/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      spec: scopedSpec(spec, entities),
      rows: await collect(db, spec, user, entities),
      locale,
      formulas: seesEverything(spec, user, entities),
      timezone: config.timezone,
    }),
  });
  if (!response.ok) throw new WorkerUnavailable();
  return Buffer.from(await response.arrayBuffer());
}

interface EntityDiff {
  added: { key: string; values: Record<string, unknown> }[];
  changed: { key: string; id: string; version: number; fields: Record<string, [unknown, unknown]> }[];
  missing: { key: string; id: string }[];
}

interface StoredDiff {
  entities: Record<string, EntityDiff>;
  problems: unknown[];
}

/** Compare an uploaded workbook with the data. It writes nothing but the diff, for the apply. */
export async function startImport(
  db: Db,
  spec: DaftarSpec,
  user: User,
  config: RoundTripConfig,
  file: Buffer,
  fileName: string,
): Promise<Record<string, unknown>> {
  const entities = importable(spec, user);
  if (!entities.length) throw new Forbidden();
  const form = new FormData();
  form.set("spec", JSON.stringify(scopedSpec(spec, entities)));
  form.set("keys", JSON.stringify(await collect(db, spec, user, entities)));
  form.set("timezone", config.timezone);
  form.set("file", new Blob([new Uint8Array(file)]), fileName);
  const response = await callWorker(config.workerUrl, "/v1/reimport/diff", { method: "POST", body: form });
  const body: unknown = await response.json().catch(() => {
    throw new WorkerUnavailable();
  });
  if (!response.ok) {
    // A file the worker can't read is the user's to fix, and its message is written for them.
    const { code, message } = body as { code?: string; message?: unknown };
    if (!code || !message) throw new WorkerUnavailable();
    throw new HttpException({ error: code, reason: message }, response.status === 413 ? 413 : HttpStatus.BAD_REQUEST);
  }
  await sql`DELETE FROM _import_diffs WHERE created_at < now() - make_interval(days => ${DIFF_KEPT_DAYS})`.execute(db);
  const row = await db
    .insertInto("_import_diffs")
    .values({ created_by: user.id, diff: JSON.stringify(body) })
    .returning("id")
    .executeTakeFirstOrThrow();
  return { diffId: row.id, ...(body as StoredDiff) };
}

interface Selection {
  added?: unknown;
  changed?: unknown;
}

function chosen(list: unknown, key: string): boolean {
  return Array.isArray(list) && list.includes(key);
}

/** Apply what was chosen, as one batch that can be undone. Rows missing from the file stay (R-23). */
export async function applyImport(
  db: Db,
  spec: DaftarSpec,
  records: RecordService,
  user: User,
  diffId: string,
  selected: Record<string, Selection> | undefined,
): Promise<{ batchId: string; added: number; changed: number; stale: string[]; problems: SeedProblem[] }> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(diffId)) throw new NotFound();
  return db.transaction().execute(async (tx) => {
    // Taken inside the transaction: applied once, and back in place if the apply fails.
    const row = await tx.deleteFrom("_import_diffs").where("id", "=", diffId).where("created_by", "=", user.id).returning("diff").executeTakeFirst();
    if (!row) throw new NotFound();
    const diff = row.diff as StoredDiff;
    const plan: ImportPlan[] = targetsFirst(spec).flatMap((entity) => {
      const part = diff.entities[entity.key];
      if (!part) return [];
      if (!can(spec, user, entity.key, "import")) throw new Forbidden();
      const choice = selected?.[entity.key];
      return [
        {
          entity,
          added: part.added.filter((item) => (selected ? chosen(choice?.added, item.key) : true)),
          changed: part.changed.filter((item) => (selected ? chosen(choice?.changed, item.key) : true)),
        },
      ];
    });
    return records.applyImportBatch(tx, user, plan, (inner, entity, values, where, problems) => resolveLinks(inner, spec, entity, values, where, problems));
  });
}

/** A new row can name another new row in the same file, so what's linked to goes in first. */
function targetsFirst(spec: DaftarSpec): Entity[] {
  const ordered: Entity[] = [];
  const visiting = new Set<string>();
  const visit = (entity: Entity): void => {
    if (visiting.has(entity.key)) return;
    visiting.add(entity.key);
    for (const field of entity.fields) {
      const target = field.type === "link" ? spec.entities.find((item) => item.key === field.target) : undefined;
      if (target) visit(target);
    }
    ordered.push(entity);
  };
  spec.entities.forEach(visit);
  return ordered;
}

/** A sheet names a link's target by its key. One that names nothing is reported, and the field stays as it was. */
async function resolveLinks(tx: Tx, spec: DaftarSpec, entity: Entity, values: Record<string, unknown>, where: string, problems: SeedProblem[]): Promise<Record<string, unknown>> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    const field = entity.fields.find((item) => item.key === key);
    if (field?.type !== "link" || value === null) {
      out[key] = value;
      continue;
    }
    const target = linkKey(spec, field.target);
    const found = target
      ? await tx.selectFrom(tableOf(field.target)).select("_id").where(sql`${column(target)}::text`, "=", String(value as string)).executeTakeFirst()
      : undefined;
    if (found) out[key] = found._id;
    else problems.push({ where, field: key, value });
  }
  return out;
}
