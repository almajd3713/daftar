/** R-25: on first start, load the accepted import data. Once, in one batch the owner can undo. */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { sql } from "kysely";

import type { DaftarSpec } from "@daftar/spec/types";

import { column, tableOf, type Db, type Tx } from "./db.js";
import type { RecordService, SeedProblem } from "./records/service.js";

interface Reference {
  $ref: { field: string; value: unknown };
}

function isReference(value: unknown): value is Reference {
  return typeof value === "object" && value !== null && "$ref" in value;
}

/** Entities in an order where each comes after those it links to. A loop keeps its given order. */
function loadOrder(spec: DaftarSpec, keys: string[]): string[] {
  const done: string[] = [];
  const visiting = new Set<string>();
  const visit = (key: string): void => {
    if (done.includes(key) || visiting.has(key) || !keys.includes(key)) return;
    visiting.add(key);
    for (const field of spec.entities.find((entity) => entity.key === key)?.fields ?? []) {
      if (field.type === "link") visit(field.target);
    }
    visiting.delete(key);
    done.push(key);
  };
  keys.forEach(visit);
  return done;
}

export async function loadSeedOnce(db: Db, spec: DaftarSpec, records: RecordService, seedDir: string): Promise<void> {
  const taken = await db.selectFrom("_seed_state").select("id").executeTakeFirst();
  if (taken) return;
  const keys = spec.entities.map((entity) => entity.key).filter((key) => existsSync(join(seedDir, `${key}.jsonl`)));
  const entities = loadOrder(spec, keys).map((key) => ({
    key,
    rows: readFileSync(join(seedDir, `${key}.jsonl`), "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>),
  }));
  const resolve = async (tx: Tx, row: Record<string, unknown>, problems: SeedProblem[], where: string): Promise<Record<string, unknown>> => {
    const entityKey = where.split("[")[0] as string;
    const entity = spec.entities.find((item) => item.key === entityKey);
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(row)) {
      if (!isReference(value)) {
        out[key] = value;
        continue;
      }
      const link = entity?.fields.find((item) => item.key === key);
      if (link?.type !== "link") continue;
      const found = await tx
        .selectFrom(tableOf(link.target))
        .select("_id")
        .where(sql`${column(value.$ref.field)}::text`, "=", String(value.$ref.value as string | number))
        .executeTakeFirst();
      if (found) out[key] = found._id;
      // A row whose target isn't there is kept, unlinked, and reported rather than lost.
      else problems.push({ where, field: key, value: value.$ref.value });
    }
    return out;
  };
  const { batchId, created, problems } = await records.loadBatch(entities, resolve);
  await db.insertInto("_seed_state").values({ batch_id: batchId, created, problems: JSON.stringify(problems) }).execute();
}
