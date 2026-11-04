/**
 * Spec to schema: diff, plan, apply. Additive changes apply on their own. Destructive ones wait for a
 * backup and an explicit confirmation (Directus' snapshot, diff and apply).
 */
import { sql } from "kysely";

import type { DaftarSpec, Field } from "@daftar/spec/types";

import { column, tableOf, type Db, type Tx } from "../db.js";

export interface ColumnPlan {
  table: string;
  column: string;
  type: string;
  unique: boolean;
  references?: string;
}

export interface MigrationPlan {
  createTables: string[];
  addColumns: ColumnPlan[];
  dropColumns: { table: string; column: string }[];
  dropTables: string[];
  changeTypes: { table: string; column: string; from: string; to: string }[];
}

const SQL_TYPES: Record<string, string> = {
  text: "text",
  longtext: "text",
  integer: "bigint",
  decimal: "numeric",
  money: "numeric",
  percent: "numeric",
  date: "date",
  datetime: "timestamptz",
  boolean: "boolean",
  choice: "text",
  multichoice: "jsonb",
  phone: "text",
  email: "text",
  link: "uuid",
};

export function sqlTypeOf(field: Field): string | null {
  if (field.type === "child") return null;
  if (field.type === "computed") return field.computed.store ? (SQL_TYPES[field.resultType] ?? "text") : null;
  return SQL_TYPES[field.type] ?? null;
}

function desired(spec: DaftarSpec): ColumnPlan[] {
  const columns: ColumnPlan[] = [];
  for (const entity of spec.entities) {
    for (const field of entity.fields) {
      const type = sqlTypeOf(field);
      if (type === null) continue;
      const plan: ColumnPlan = {
        table: tableOf(entity.key),
        column: field.key,
        type,
        unique: "unique" in field && field.unique === true,
      };
      if (field.type === "link") plan.references = tableOf(field.target);
      columns.push(plan);
    }
  }
  return columns;
}

export async function ensureSystemTables(db: Db): Promise<void> {
  await sql`CREATE TABLE IF NOT EXISTS _schema_columns (
    table_name text NOT NULL, column_name text NOT NULL, column_type text NOT NULL, PRIMARY KEY (table_name, column_name)
  )`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _schema_tables (table_name text PRIMARY KEY)`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), username text NOT NULL UNIQUE, password_hash text NOT NULL,
    role text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
  )`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _sessions (
    token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES _users(id) ON DELETE CASCADE, expires_at timestamptz NOT NULL
  )`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _counters (name text PRIMARY KEY, value bigint NOT NULL)`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), seq bigserial, at timestamptz NOT NULL DEFAULT now(), actor text NOT NULL,
    source text NOT NULL, batch_id uuid, entity text NOT NULL, record_id uuid NOT NULL, op text NOT NULL,
    changes jsonb NOT NULL, snapshot jsonb, revert_of uuid, reverted_by uuid
  )`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _seed_state (
    id boolean PRIMARY KEY DEFAULT true, batch_id uuid, created integer NOT NULL, problems jsonb NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(), CHECK (id)
  )`.execute(db);
  await sql`CREATE TABLE IF NOT EXISTS _import_diffs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_by uuid NOT NULL, diff jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), applied_at timestamptz
  )`.execute(db);
  await sql`CREATE INDEX IF NOT EXISTS _audit_record ON _audit (entity, record_id, seq)`.execute(db);
  await sql`CREATE INDEX IF NOT EXISTS _audit_batch ON _audit (batch_id, seq)`.execute(db);
}

export async function planMigration(db: Db, spec: DaftarSpec): Promise<MigrationPlan> {
  await ensureSystemTables(db);
  const tables = new Set((await db.selectFrom("_schema_tables").select("table_name").execute()).map((row) => row.table_name as string));
  const current = await db.selectFrom("_schema_columns").selectAll().execute();
  const known = new Map(current.map((row) => [`${row.table_name}.${row.column_name}`, row.column_type as string]));
  const wanted = desired(spec);
  const wantedKeys = new Set(wanted.map((item) => `${item.table}.${item.column}`));
  const wantedTables = new Set(spec.entities.map((entity) => tableOf(entity.key)));
  const dropTables = [...tables].filter((table) => !wantedTables.has(table));
  return {
    createTables: [...wantedTables].filter((table) => !tables.has(table)),
    addColumns: wanted.filter((item) => !known.has(`${item.table}.${item.column}`)),
    dropTables,
    dropColumns: current
      .filter((row) => !wantedKeys.has(`${row.table_name}.${row.column_name}`) && !dropTables.includes(row.table_name as string))
      .map((row) => ({ table: row.table_name as string, column: row.column_name as string })),
    changeTypes: wanted
      .filter((item) => known.has(`${item.table}.${item.column}`) && known.get(`${item.table}.${item.column}`) !== item.type)
      .map((item) => ({ table: item.table, column: item.column, from: known.get(`${item.table}.${item.column}`) as string, to: item.type })),
  };
}

export function isDestructive(plan: MigrationPlan): boolean {
  return plan.dropColumns.length + plan.dropTables.length + plan.changeTypes.length > 0;
}

export class MigrationBlocked extends Error {
  constructor(readonly plan: MigrationPlan) {
    super(
      `This spec would destroy data, so it needs a backup and a confirmation:\n${JSON.stringify(
        { dropTables: plan.dropTables, dropColumns: plan.dropColumns, changeTypes: plan.changeTypes },
        null,
        1,
      )}`,
    );
  }
}

async function addColumn(tx: Tx, item: ColumnPlan): Promise<void> {
  // The type comes from the table above, never from a label or a formula.
  const type = sql.raw(item.type);
  await sql`ALTER TABLE ${sql.table(item.table)} ADD COLUMN ${column(item.column)} ${type}`.execute(tx);
  if (item.unique) {
    await sql`CREATE UNIQUE INDEX ${sql.ref(`${item.table}__${item.column}__unique`)} ON ${sql.table(item.table)} (${column(item.column)})`.execute(tx);
  }
  await tx.insertInto("_schema_columns").values({ table_name: item.table, column_name: item.column, column_type: item.type }).execute();
}

export interface ApplyOptions {
  /** Both must be given to apply a destructive plan. The backup is a reference to a real dump. */
  confirmDestructive?: boolean;
  backupReference?: string;
}

export async function applyMigration(db: Db, plan: MigrationPlan, options: ApplyOptions = {}): Promise<void> {
  if (isDestructive(plan) && !(options.confirmDestructive && options.backupReference)) throw new MigrationBlocked(plan);
  await db.transaction().execute(async (tx) => {
    for (const table of plan.createTables) {
      await sql`CREATE TABLE ${sql.table(table)} (
        _id uuid PRIMARY KEY DEFAULT gen_random_uuid(), _name text, _version integer NOT NULL DEFAULT 1,
        _created_at timestamptz NOT NULL DEFAULT now(), _created_by uuid, _updated_at timestamptz NOT NULL DEFAULT now(),
        _errors jsonb, _seq bigserial
      )`.execute(tx);
      await tx.insertInto("_schema_tables").values({ table_name: table }).execute();
    }
    for (const item of plan.addColumns) await addColumn(tx, item);
    // Links last: their target tables may only just have been created.
    for (const item of plan.addColumns) {
      if (item.references) {
        await sql`ALTER TABLE ${sql.table(item.table)} ADD FOREIGN KEY (${column(item.column)}) REFERENCES ${sql.table(item.references)} (_id)`.execute(tx);
      }
    }
    for (const change of plan.changeTypes) {
      await sql`ALTER TABLE ${sql.table(change.table)} ALTER COLUMN ${column(change.column)} TYPE ${sql.raw(change.to)} USING ${column(change.column)}::${sql.raw(change.to)}`.execute(tx);
      await tx.updateTable("_schema_columns").set({ column_type: change.to }).where("table_name", "=", change.table).where("column_name", "=", change.column).execute();
    }
    for (const drop of plan.dropColumns) {
      await sql`ALTER TABLE ${sql.table(drop.table)} DROP COLUMN ${column(drop.column)}`.execute(tx);
      await tx.deleteFrom("_schema_columns").where("table_name", "=", drop.table).where("column_name", "=", drop.column).execute();
    }
    for (const table of plan.dropTables) {
      await sql`DROP TABLE ${sql.table(table)} CASCADE`.execute(tx);
      await tx.deleteFrom("_schema_columns").where("table_name", "=", table).execute();
      await tx.deleteFrom("_schema_tables").where("table_name", "=", table).execute();
    }
  });
}

/** What boot does: apply additive changes, and stop on anything destructive. */
export async function migrateOnBoot(db: Db, spec: DaftarSpec): Promise<MigrationPlan> {
  const plan = await planMigration(db, spec);
  await applyMigration(db, plan);
  return plan;
}
