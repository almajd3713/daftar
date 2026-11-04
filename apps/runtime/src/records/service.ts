/** The generic record store: the only path that writes records, so nothing skips the rules or audit. */
import { sql, type ExpressionBuilder } from "kysely";

import type { DaftarSpec, Entity, Field, Workflow } from "@daftar/spec/types";

import { column, tableOf, type Db, type Tx } from "../db.js";
import { BadQuery, Conflict, FieldErrors, Forbidden, MESSAGES, NotFound } from "../errors.js";
import { evaluate, ExcelError } from "../expr/evaluate.js";
import type { Message } from "../messages.js";
import { can, canSeeField, ownOnly, SYSTEM_USER, visibleFields, type Action, type User } from "./access.js";
import { computedFields, computeRow, recomputeDependents, recomputeEngineFields } from "./computed.js";
import { checkValue, recordScalars, UUID } from "./values.js";

export type Source = "ui" | "import" | "workflow" | "system";
export const MASK = "*";
const MAX_PAGE_SIZE = 500;
const FILTER_OPS: Record<string, string> = { eq: "=", ne: "!=", lt: "<", le: "<=", gt: ">", ge: ">=" };
const NUMERIC = new Set(["integer", "decimal", "money", "percent"]);

export interface WriteContext {
  user: User;
  source: Source;
  batchId?: string;
  /** A bulk load runs the table's engine formulas once at the end, not after every row. */
  deferEngine?: boolean;
}

export interface SeedProblem {
  where: string;
  field: string;
  value: unknown;
}

export interface ListQuery {
  q?: string;
  sort?: string;
  page?: number;
  pageSize?: number;
  totals?: string;
  filters?: { field: string; op: string; value: string }[];
}

function isNumeric(field: Field): boolean {
  return NUMERIC.has(field.type === "computed" ? field.resultType : field.type);
}

function same(left: unknown, right: unknown): boolean {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

export class RecordService {
  constructor(
    private readonly db: Db,
    private readonly spec: DaftarSpec,
    private readonly clock: () => Date = () => new Date(),
  ) {}

  entity(key: string): Entity {
    const entity = this.spec.entities.find((item) => item.key === key);
    if (!entity) throw new NotFound();
    return entity;
  }

  private require(user: User, entity: Entity, action: Action): void {
    if (!can(this.spec, user, entity.key, action)) {
      // Not even a hint that an entity exists, for someone who can't read it.
      if (!can(this.spec, user, entity.key, "read")) throw new NotFound();
      throw new Forbidden();
    }
  }

  /** A record as the API returns it: hidden fields are gone, as if they didn't exist. */
  present(user: User, entity: Entity, row: Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = {
      _id: row._id,
      _name: row._name,
      _version: row._version,
      _createdAt: row._created_at,
      _updatedAt: row._updated_at,
    };
    const errors = (row._errors ?? {}) as Record<string, string>;
    const shown: Record<string, string> = {};
    for (const field of visibleFields(this.spec, user, entity)) {
      if (field.type === "child") continue;
      out[field.key] = row[field.key] ?? null;
      if (errors[field.key]) shown[field.key] = errors[field.key] as string;
    }
    if (Object.keys(shown).length) out._errors = shown;
    return out;
  }

  private scoped(user: User, entity: Entity) {
    let query = this.db.selectFrom(tableOf(entity.key));
    if (ownOnly(this.spec, user, entity.key)) query = query.where("_created_by", "=", user.id);
    return query;
  }

  private filterableField(user: User, entity: Entity, key: string, what: string): Field {
    const field = entity.fields.find((item) => item.key === key);
    // A hidden field can't be sorted or filtered on either: that would reveal its values one by one.
    if (!field || field.type === "child" || !canSeeField(this.spec, user, field)) throw new BadQuery(`${what} ${key}`);
    return field;
  }

  private filterValue(field: Field, text: string): unknown {
    if (isNumeric(field)) {
      const number = Number(text);
      if (Number.isNaN(number)) throw new BadQuery(`filter ${field.key}`);
      return number;
    }
    if (field.type === "boolean") return text === "true";
    return text;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private applyFilters(query: any, user: User, entity: Entity, list: ListQuery): any {
    let result = query;
    for (const filter of list.filters ?? []) {
      const field = this.filterableField(user, entity, filter.field, "filter");
      const ref = column(field.key);
      if (filter.op in FILTER_OPS) {
        result = result.where(ref, FILTER_OPS[filter.op], this.filterValue(field, filter.value));
      } else if (filter.op === "in") {
        result = result.where(ref, "in", filter.value.split(",").map((value) => this.filterValue(field, value)));
      } else if (filter.op === "contains") {
        const pattern = `%${filter.value.replace(/[\\%_]/g, "\\$&")}%`;
        result = result.where(sql`${ref}::text`, "ilike", pattern);
      } else if (filter.op === "isEmpty") {
        result = result.where(ref, "is", null);
      } else if (filter.op === "isNotEmpty") {
        result = result.where(ref, "is not", null);
      } else {
        throw new BadQuery(`filter operator ${filter.op}`);
      }
    }
    if (list.q) {
      const pattern = `%${list.q.replace(/[\\%_]/g, "\\$&")}%`;
      const visible = new Set(visibleFields(this.spec, user, entity).map((field) => field.key));
      const keys = (entity.searchFields ?? [entity.titleField]).filter((key) => visible.has(key));
      if (keys.length) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        result = result.where((eb: ExpressionBuilder<any, any>) => eb.or(keys.map((key) => eb(sql`${column(key)}::text`, "ilike", pattern))));
      }
    }
    return result;
  }

  async list(user: User, entityKey: string, query: ListQuery): Promise<Record<string, unknown>> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "read");
    const page = Math.max(1, Math.trunc(query.page ?? 1));
    const pageSize = Math.min(MAX_PAGE_SIZE, Math.max(1, Math.trunc(query.pageSize ?? 50)));
    const base = this.applyFilters(this.scoped(user, entity), user, entity, query);

    let rowsQuery = base.selectAll();
    for (const part of (query.sort ?? "").split(",").filter(Boolean)) {
      const descending = part.startsWith("-");
      const field = this.filterableField(user, entity, descending ? part.slice(1) : part, "sort");
      rowsQuery = rowsQuery.orderBy(column(field.key), descending ? "desc" : "asc");
    }
    const rows = await rowsQuery.orderBy("_seq").limit(pageSize).offset((page - 1) * pageSize).execute();
    const counted = await base.select(sql<number>`count(*)`.as("count")).executeTakeFirst();

    const totals: Record<string, number | null> = {};
    for (const key of (query.totals ?? "").split(",").filter(Boolean)) {
      const field = this.filterableField(user, entity, key, "totals");
      if (!isNumeric(field)) throw new BadQuery(`totals ${key}`);
      const sum = await base.select(sql<number>`sum(${column(key)})`.as("total")).executeTakeFirst();
      totals[key] = sum?.total ?? null;
    }
    return {
      rows: rows.map((row: Record<string, unknown>) => this.present(user, entity, row)),
      total: Number(counted?.count ?? 0),
      page,
      pageSize,
      totals,
    };
  }

  private async fetchRow(tx: Tx, user: User, entity: Entity, id: string, lock = false): Promise<Record<string, unknown>> {
    if (!UUID.test(id)) throw new NotFound();
    let query = tx.selectFrom(tableOf(entity.key)).selectAll().where("_id", "=", id);
    if (ownOnly(this.spec, user, entity.key)) query = query.where("_created_by", "=", user.id);
    if (lock) query = query.forUpdate();
    const row = await query.executeTakeFirst();
    if (!row) throw new NotFound();
    return row;
  }

  async get(user: User, entityKey: string, id: string): Promise<Record<string, unknown>> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "read");
    return this.present(user, entity, await this.fetchRow(this.db, user, entity, id));
  }

  private workflowOf(entity: Entity): Workflow | undefined {
    return this.spec.workflows.find((workflow) => workflow.entity === entity.key);
  }

  /** Check a form's values. Fields a role can't see are refused as if they weren't there. */
  private async check(tx: Tx, user: User, entity: Entity, input: Record<string, unknown>, creating: boolean, source: Source): Promise<Record<string, unknown>> {
    const errors: Record<string, Message> = {};
    const values: Record<string, unknown> = {};
    const stateField = this.workflowOf(entity)?.stateField;
    for (const [key, raw] of Object.entries(input)) {
      if (key.startsWith("_")) continue;
      const field = entity.fields.find((item) => item.key === key);
      if (!field || !canSeeField(this.spec, user, field)) {
        errors[key] = MESSAGES.unknownField;
      } else if (field.type === "computed" || field.type === "child") {
        errors[key] = MESSAGES.readOnly;
      } else if (key === stateField && source === "ui") {
        errors[key] = MESSAGES.useTransition;
      } else {
        const checked = checkValue(field, raw);
        if ("error" in checked) errors[key] = checked.error;
        else values[key] = checked.value;
      }
    }
    if (creating) {
      for (const field of entity.fields) {
        if (!("default" in field) || field.default === undefined || values[field.key] !== undefined) continue;
        if (field.key === stateField) continue;
        values[field.key] = field.default;
      }
    }
    for (const field of entity.fields) {
      const required = "required" in field && field.required === true;
      if (!required || errors[field.key] || field.key === stateField) continue;
      const missing = creating ? values[field.key] === undefined || values[field.key] === null : field.key in values && values[field.key] === null;
      if (missing && canSeeField(this.spec, user, field)) errors[field.key] = MESSAGES.required;
    }
    for (const field of entity.fields) {
      if (field.type !== "link" || !values[field.key] || errors[field.key]) continue;
      const target = await tx.selectFrom(tableOf((field).target)).select("_id").where("_id", "=", values[field.key] as string).executeTakeFirst();
      if (!target) errors[field.key] = MESSAGES.invalidLink;
    }
    if (Object.keys(errors).length) throw new FieldErrors(errors);
    return values;
  }

  private async nextName(tx: Tx, entity: Entity, values: Record<string, unknown>, id: string): Promise<string> {
    const naming = entity.naming;
    if (naming.type === "uuid") return id;
    if (naming.type === "field") return JSON.stringify(values[naming.field] ?? id).replace(/^"|"$/g, "");
    const counter = await tx
      .insertInto("_counters")
      .values({ name: entity.key, value: 1 })
      .onConflict((conflict) => conflict.column("name").doUpdateSet({ value: sql`_counters.value + 1` }))
      .returning("value")
      .executeTakeFirstOrThrow();
    return `${naming.prefix}${String(counter.value).padStart(4, "0")}`;
  }

  private writable(entity: Entity, row: Record<string, unknown>): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const field of entity.fields) {
      if (field.type === "child" || !(field.key in row)) continue;
      if (field.type === "computed" && !field.computed.store) continue;
      const value = row[field.key];
      out[field.key] = field.type === "multichoice" && value !== null ? JSON.stringify(value) : value;
    }
    return out;
  }

  /** Per-field changes for the audit record. Computed fields aren't recorded (R-18). */
  private changesOf(entity: Entity, before: Record<string, unknown>, after: Record<string, unknown>): Record<string, [unknown, unknown]> {
    const changes: Record<string, [unknown, unknown]> = {};
    for (const field of entity.fields) {
      if (field.type === "computed" || field.type === "child") continue;
      const previous = before[field.key] ?? null;
      const next = after[field.key] ?? null;
      if (!same(previous, next)) changes[field.key] = [previous, next];
    }
    return changes;
  }

  private async audit(
    tx: Tx,
    context: WriteContext,
    entity: Entity,
    id: string,
    op: string,
    changes: Record<string, [unknown, unknown]>,
    extra: { snapshot?: unknown; revertOf?: string } = {},
  ): Promise<string> {
    const row = await tx
      .insertInto("_audit")
      .values({
        actor: context.user.username,
        source: context.source,
        batch_id: context.batchId ?? null,
        entity: entity.key,
        record_id: id,
        op,
        changes: JSON.stringify(changes),
        snapshot: extra.snapshot ? JSON.stringify(extra.snapshot) : null,
        revert_of: extra.revertOf ?? null,
      })
      .returning("id")
      .executeTakeFirstOrThrow();
    return row.id as string;
  }

  private async afterWrite(tx: Tx, entity: Entity, id: string, row: Record<string, unknown>): Promise<void> {
    await recomputeEngineFields(tx, this.spec, entity);
    await recomputeDependents(tx, this.spec, entity, id, this.clock(), row);
  }

  private uniqueError(error: unknown, entity: Entity): unknown {
    const pg = error as { code?: string; constraint?: string };
    if (pg.code === "23505") {
      const match = /__([a-z0-9_]+)__unique$/.exec(pg.constraint ?? "");
      const key = match?.[1] ?? entity.titleField;
      return new FieldErrors({ [key]: MESSAGES.notUnique });
    }
    return error;
  }

  /** Create inside an open transaction. Seed loads and imports come through here too. */
  async createIn(tx: Tx, context: WriteContext, entity: Entity, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    const values = await this.check(tx, context.user, entity, input, true, context.source);
    const workflow = this.workflowOf(entity);
    if (workflow && (context.source === "ui" || values[workflow.stateField] == null)) values[workflow.stateField] = workflow.initialState;
    const { id } = (await sql<{ id: string }>`SELECT gen_random_uuid() AS id`.execute(tx)).rows[0] as { id: string };
    const row: Record<string, unknown> = { _id: id, ...values };
    await computeRow(tx, this.spec, entity, row, this.clock());
    const name = await this.nextName(tx, entity, row, id);
    try {
      const inserted = await tx
        .insertInto(tableOf(entity.key))
        .values({
          _id: id,
          _name: name,
          _created_by: context.user === SYSTEM_USER ? null : context.user.id,
          _errors: row._errors ? JSON.stringify(row._errors) : null,
          ...this.writable(entity, row),
        })
        .returningAll()
        .executeTakeFirstOrThrow();
      await this.audit(tx, context, entity, id, "create", this.changesOf(entity, {}, inserted), { snapshot: { _name: name, _created_by: inserted._created_by } });
      if (context.deferEngine) return inserted;
      await this.afterWrite(tx, entity, id, inserted);
      return await tx.selectFrom(tableOf(entity.key)).selectAll().where("_id", "=", id).executeTakeFirstOrThrow();
    } catch (error) {
      throw this.uniqueError(error, entity);
    }
  }

  async create(user: User, entityKey: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "create");
    const row = await this.db.transaction().execute((tx) => this.createIn(tx, { user, source: "ui" }, entity, input));
    return this.present(user, entity, row);
  }

  private async updateIn(
    tx: Tx,
    context: WriteContext,
    entity: Entity,
    before: Record<string, unknown>,
    values: Record<string, unknown>,
    op: string,
    extra: { revertOf?: string } = {},
  ): Promise<{ row: Record<string, unknown>; auditId: string | null }> {
    const row: Record<string, unknown> = { ...before, ...values };
    await computeRow(tx, this.spec, entity, row, this.clock());
    const changes = this.changesOf(entity, before, row);
    const computedChanged = computedFields(entity).some((field) => !same(before[field.key], row[field.key]));
    if (!Object.keys(changes).length && !computedChanged) return { row: before, auditId: null };
    try {
      const updated = await tx
        .updateTable(tableOf(entity.key))
        .set({
          ...this.writable(entity, row),
          _errors: row._errors ? JSON.stringify(row._errors) : null,
          _version: sql`_version + 1`,
          _updated_at: sql`now()`,
        })
        .where("_id", "=", before._id)
        .returningAll()
        .executeTakeFirstOrThrow();
      const auditId = Object.keys(changes).length ? await this.audit(tx, context, entity, before._id as string, op, changes, extra) : null;
      await this.afterWrite(tx, entity, before._id as string, updated);
      return { row: await tx.selectFrom(tableOf(entity.key)).selectAll().where("_id", "=", before._id).executeTakeFirstOrThrow(), auditId };
    } catch (error) {
      throw this.uniqueError(error, entity);
    }
  }

  async update(user: User, entityKey: string, id: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "update");
    const row = await this.db.transaction().execute(async (tx) => {
      const before = await this.fetchRow(tx, user, entity, id, true);
      if (input._version !== undefined && input._version !== before._version) throw new Conflict(MESSAGES.stale);
      const values = await this.check(tx, user, entity, input, false, "ui");
      return (await this.updateIn(tx, { user, source: "ui" }, entity, before, values, "update")).row;
    });
    return this.present(user, entity, row);
  }

  private async deleteIn(tx: Tx, context: WriteContext, entity: Entity, before: Record<string, unknown>, extra: { revertOf?: string } = {}): Promise<void> {
    const id = before._id as string;
    // Links are handled here, not by the database, so every effect lands in the history.
    for (const other of this.spec.entities) {
      for (const link of other.fields) {
        if (link.type !== "link" || link.target !== entity.key) continue;
        const rows = await tx.selectFrom(tableOf(other.key)).selectAll().where(link.key, "=", id).forUpdate().execute();
        if (!rows.length) continue;
        if (link.onDelete === "restrict") throw new Conflict(MESSAGES.linked);
        for (const row of rows) {
          if (link.onDelete === "cascade") await this.deleteIn(tx, context, other, row);
          else await this.updateIn(tx, context, other, row, { [link.key]: null }, "update");
        }
      }
    }
    await tx.deleteFrom(tableOf(entity.key)).where("_id", "=", id).execute();
    const changes = this.changesOf(entity, before, {});
    await this.audit(tx, context, entity, id, "delete", changes, {
      snapshot: { _name: before._name, _created_by: before._created_by, _created_at: before._created_at, _errors: before._errors },
      ...extra,
    });
    await this.afterWrite(tx, entity, id, before);
  }

  async remove(user: User, entityKey: string, id: string): Promise<void> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "delete");
    await this.db.transaction().execute(async (tx) => {
      const before = await this.fetchRow(tx, user, entity, id, true);
      await this.deleteIn(tx, { user, source: "ui" }, entity, before);
    });
  }

  /** R-20: only the transitions the spec defines, and a refusal says why. */
  async transition(user: User, entityKey: string, id: string, action: string): Promise<Record<string, unknown>> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "update");
    const workflow = this.workflowOf(entity);
    const transition = workflow?.transitions.find((item) => item.key === action);
    if (!workflow || !transition) throw new NotFound();
    const row = await this.db.transaction().execute(async (tx) => {
      const before = await this.fetchRow(tx, user, entity, id, true);
      if (!transition.roles.includes(user.role as "owner")) throw new Conflict(MESSAGES.transitionRole);
      if (!transition.from.includes(before[workflow.stateField] as string)) throw new Conflict(MESSAGES.transitionFrom);
      if (transition.condition) {
        const result = evaluate(transition.condition, { record: recordScalars(entity, before), now: this.clock() });
        if (result instanceof ExcelError || result !== true) throw new Conflict(MESSAGES.transitionCondition);
      }
      const context: WriteContext = { user, source: "workflow" };
      return (await this.updateIn(tx, context, entity, before, { [workflow.stateField]: transition.to }, "transition")).row;
    });
    return this.present(user, entity, row);
  }

  private masked(user: User, entityKey: string, changes: Record<string, [unknown, unknown]>): Record<string, [unknown, unknown]> {
    const entity = this.spec.entities.find((item) => item.key === entityKey);
    const out: Record<string, [unknown, unknown]> = {};
    for (const [key, pair] of Object.entries(changes)) {
      const field = entity?.fields.find((item) => item.key === key);
      // The change happened and that's visible; what it was isn't (R-17).
      out[key] = field && canSeeField(this.spec, user, field) ? pair : [MASK, MASK];
    }
    return out;
  }

  /** C-9, masked for this user. */
  presentAudit(user: User, row: Record<string, unknown>): Record<string, unknown> {
    const entry: Record<string, unknown> = {
      id: row.id,
      at: row.at,
      actor: row.actor,
      source: row.source,
      entity: row.entity,
      recordId: row.record_id,
      op: row.op,
      changes: this.masked(user, row.entity as string, row.changes as Record<string, [unknown, unknown]>),
    };
    if (row.batch_id) entry.batchId = row.batch_id;
    if (row.revert_of) entry.revertOf = row.revert_of;
    if (row.reverted_by) entry.revertedBy = row.reverted_by;
    return entry;
  }

  async history(user: User, entityKey: string, id: string): Promise<Record<string, unknown>[]> {
    const entity = this.entity(entityKey);
    this.require(user, entity, "read");
    if (!UUID.test(id)) throw new NotFound();
    if (ownOnly(this.spec, user, entity.key)) {
      const first = await this.db.selectFrom("_audit").select("snapshot").where("entity", "=", entity.key).where("record_id", "=", id).orderBy("seq").executeTakeFirst();
      const owner = (first?.snapshot as { _created_by?: string } | null)?._created_by;
      if (owner !== user.id) throw new NotFound();
    }
    const rows = await this.db.selectFrom("_audit").selectAll().where("entity", "=", entity.key).where("record_id", "=", id).orderBy("seq", "desc").execute();
    if (!rows.length) throw new NotFound();
    return rows.map((row) => this.presentAudit(user, row));
  }

  /** Put one change back. It must still be what's there: a later edit is a conflict, not lost. */
  private async revertIn(tx: Tx, context: WriteContext, change: Record<string, unknown>): Promise<void> {
    if (change.reverted_by) throw new Conflict(MESSAGES.alreadyReverted);
    const entity = this.entity(change.entity as string);
    const id = change.record_id as string;
    const changes = change.changes as Record<string, [unknown, unknown]>;
    const existing = await tx.selectFrom(tableOf(entity.key)).selectAll().where("_id", "=", id).forUpdate().executeTakeFirst();
    let auditId: string | null;
    const op = change.op as string;
    if (op === "create") {
      if (!existing) throw new Conflict(MESSAGES.revertConflict);
      for (const [key, pair] of Object.entries(changes)) {
        if (!same(existing[key], pair[1])) throw new Conflict(MESSAGES.revertConflict);
      }
      await this.deleteIn(tx, context, entity, existing, { revertOf: change.id as string });
      auditId = "done";
    } else if (op === "delete") {
      if (existing) throw new Conflict(MESSAGES.revertConflict);
      const snapshot = (change.snapshot ?? {}) as Record<string, unknown>;
      const row: Record<string, unknown> = { _id: id };
      for (const [key, pair] of Object.entries(changes)) row[key] = pair[0];
      await computeRow(tx, this.spec, entity, row, this.clock());
      const inserted = await tx
        .insertInto(tableOf(entity.key))
        .values({ _id: id, _name: snapshot._name as string, _created_by: (snapshot._created_by) ?? null, _errors: row._errors ? JSON.stringify(row._errors) : null, ...this.writable(entity, row) })
        .returningAll()
        .executeTakeFirstOrThrow();
      auditId = await this.audit(tx, context, entity, id, "revert", this.changesOf(entity, {}, inserted), { revertOf: change.id as string, snapshot });
      await this.afterWrite(tx, entity, id, inserted);
    } else if (op === "update" || op === "transition") {
      if (!existing) throw new Conflict(MESSAGES.revertConflict);
      const values: Record<string, unknown> = {};
      for (const [key, pair] of Object.entries(changes)) {
        if (!same(existing[key], pair[1])) throw new Conflict(MESSAGES.revertConflict);
        values[key] = pair[0];
      }
      auditId = (await this.updateIn(tx, context, entity, existing, values, "revert", { revertOf: change.id as string })).auditId;
    } else {
      throw new Conflict(MESSAGES.revertConflict);
    }
    if (auditId) await tx.updateTable("_audit").set({ reverted_by: auditId === "done" ? change.id : auditId }).where("id", "=", change.id).execute();
  }

  async revert(user: User, changeId: string): Promise<void> {
    if (!UUID.test(changeId)) throw new NotFound();
    await this.db.transaction().execute(async (tx) => {
      const change = await tx.selectFrom("_audit").selectAll().where("id", "=", changeId).forUpdate().executeTakeFirst();
      if (!change) throw new NotFound();
      if (!can(this.spec, user, change.entity as string, "revert")) throw new Forbidden();
      await this.revertIn(tx, { user, source: "ui" }, change);
    });
  }

  /** Undo a whole batch, newest first, or nothing at all. */
  async undoBatch(user: User, batchId: string): Promise<{ undone: number }> {
    if (!UUID.test(batchId)) throw new NotFound();
    return this.db.transaction().execute(async (tx) => {
      const changes = await tx.selectFrom("_audit").selectAll().where("batch_id", "=", batchId).where("revert_of", "is", null).orderBy("seq", "desc").forUpdate().execute();
      if (!changes.length) throw new NotFound();
      for (const entity of new Set(changes.map((change) => change.entity as string))) {
        if (!can(this.spec, user, entity, "revert")) throw new Forbidden();
      }
      for (const change of changes) await this.revertIn(tx, { user, source: "system", batchId }, change);
      return { undone: changes.length };
    });
  }

  /** Records arriving together, such as a seed or an import: one batch that can be undone. */
  async createBatch(entityKey: string, rows: Record<string, unknown>[], source: Source = "import"): Promise<{ batchId: string; created: number }> {
    const entity = this.entity(entityKey);
    return this.db.transaction().execute(async (tx) => {
      const { id: batchId } = (await sql<{ id: string }>`SELECT gen_random_uuid() AS id`.execute(tx)).rows[0] as { id: string };
      const context: WriteContext = { user: SYSTEM_USER, source, batchId, deferEngine: true };
      for (const row of rows) await this.createIn(tx, context, entity, row);
      await recomputeEngineFields(tx, this.spec, entity);
      return { batchId, created: rows.length };
    });
  }

  /** Several entities in one transaction and one batch, so a seed loads whole or not at all. */
  async loadBatch(
    entities: { key: string; rows: Record<string, unknown>[] }[],
    resolve: (tx: Tx, row: Record<string, unknown>, problems: SeedProblem[], where: string) => Promise<Record<string, unknown>>,
  ): Promise<{ batchId: string; created: number; problems: SeedProblem[] }> {
    return this.db.transaction().execute(async (tx) => {
      const { id: batchId } = (await sql<{ id: string }>`SELECT gen_random_uuid() AS id`.execute(tx)).rows[0] as { id: string };
      const context: WriteContext = { user: SYSTEM_USER, source: "import", batchId, deferEngine: true };
      const problems: SeedProblem[] = [];
      let created = 0;
      for (const { key, rows } of entities) {
        const entity = this.entity(key);
        for (const [index, row] of rows.entries()) {
          await this.createIn(tx, context, entity, await resolve(tx, row, problems, `${key}[${index}]`));
          created += 1;
        }
      }
      // Now everything is in: the formulas that read across tables see the whole picture.
      for (const { key } of entities) await recomputeEngineFields(tx, this.spec, this.entity(key));
      for (const { key } of entities) {
        const entity = this.entity(key);
        if (!computedFields(entity).some((field) => field.computed.eval === "translated")) continue;
        const rows = await tx.selectFrom(tableOf(key)).selectAll().execute();
        for (const row of rows) await this.refreshComputed(tx, entity, row);
      }
      return { batchId, created, problems };
    });
  }

  private async refreshComputed(tx: Tx, entity: Entity, row: Record<string, unknown>): Promise<void> {
    await computeRow(tx, this.spec, entity, row, this.clock());
    const set: Record<string, unknown> = { _errors: row._errors ? JSON.stringify(row._errors) : null };
    for (const field of computedFields(entity)) if (field.computed.store && field.computed.eval === "translated") set[field.key] = row[field.key];
    await tx.updateTable(tableOf(entity.key)).set(set).where("_id", "=", row._id).execute();
  }
}
