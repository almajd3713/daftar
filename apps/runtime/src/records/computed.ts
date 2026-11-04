/** R-19: computed fields, recalculated on every write and stored in real columns. */
import type { ComputedEngine, DaftarSpec, Entity, EntityMapping, Expr, FieldComputed } from "@daftar/spec/types";

import { tableOf, type Tx } from "../db.js";
import { evaluateCells, fromSerial, shiftRows, type EngineCell } from "../expr/engine.js";
import { evaluate, ExcelError, toNumber, type Scalar } from "../expr/evaluate.js";
import { recordScalars } from "./values.js";

export function computedFields(entity: Entity): FieldComputed[] {
  return entity.fields.filter((field): field is FieldComputed => field.type === "computed");
}

/** A computed value in its column's type. An Excel error goes beside it, in `_errors`. */
export function storedForm(field: FieldComputed, value: Scalar): { value: unknown; error?: string } {
  if (value instanceof ExcelError) return { value: null, error: value.code };
  if (value === null || value === "") return { value: null };
  switch (field.resultType) {
    case "text":
      return { value: String(value) };
    case "boolean":
      return { value: Boolean(value) };
    case "date":
    case "datetime": {
      if (typeof value !== "number") return { value: null, error: "#VALUE!" };
      const iso = fromSerial(value).toISOString();
      return { value: field.resultType === "date" ? iso.slice(0, 10) : iso };
    }
    default:
      try {
        const number = toNumber(value);
        return { value: field.resultType === "integer" ? Math.round(number) : number };
      } catch {
        return { value: null, error: "#VALUE!" };
      }
  }
}

function walk(expr: Expr, visit: (node: Expr) => void): void {
  visit(expr);
  if (expr.kind === "op" || expr.kind === "call") expr.args.forEach((arg) => walk(arg, visit));
}

/** Computed fields in the order they can run: a field after those it reads. */
function ordered(fields: FieldComputed[]): FieldComputed[] {
  const keys = new Set(fields.map((field) => field.key));
  const done = new Set<string>();
  const result: FieldComputed[] = [];
  let pending = [...fields];
  while (pending.length) {
    const ready = pending.filter((field) => field.computed.deps.every((dep) => !keys.has(dep) || done.has(dep)));
    const next = ready.length ? ready : pending; // A cycle: run what's left, the engine reports it.
    next.forEach((field) => {
      result.push(field);
      done.add(field.key);
    });
    pending = pending.filter((field) => !next.includes(field));
  }
  return result;
}

async function loadRelated(tx: Tx, spec: DaftarSpec, entity: Entity, row: Record<string, unknown>, exprs: Expr[]): Promise<{
  related: (via: string, field: string) => Scalar;
  rollup: (via: string, fn: string, field: string | undefined) => Scalar;
}> {
  const targets = new Map<string, Record<string, unknown> | undefined>();
  const children = new Map<string, Record<string, unknown>[]>();
  for (const expr of exprs) {
    const nodes: Expr[] = [];
    walk(expr, (node) => nodes.push(node));
    for (const node of nodes) {
      if (node.kind === "related" && !targets.has(node.via)) {
        const link = entity.fields.find((field) => field.key === node.via);
        const id = row[node.via];
        if (link?.type === "link" && id) {
          targets.set(node.via, await tx.selectFrom(tableOf(link.target)).selectAll().where("_id", "=", id).executeTakeFirst());
        } else targets.set(node.via, undefined);
      }
      if (node.kind === "rollup" && !children.has(node.via)) {
        const child = entity.fields.find((field) => field.key === node.via);
        children.set(
          node.via,
          child?.type === "child" ? await tx.selectFrom(tableOf(child.target)).selectAll().where(child.via, "=", row._id).execute() : [],
        );
      }
    }
  }
  const entityOf = (key: string): Entity | undefined => spec.entities.find((item) => item.key === key);
  return {
    related: (via, field) => {
      const link = entity.fields.find((item) => item.key === via);
      const target = targets.get(via);
      const other = link?.type === "link" ? entityOf(link.target) : undefined;
      if (!target || !other) return new ExcelError("#N/A");
      return recordScalars(other, target)[field] ?? null;
    },
    rollup: (via, fn, field) => {
      const rows = children.get(via) ?? [];
      if (fn === "count") return rows.length;
      const numbers = rows.map((item) => Number(item[field as string])).filter((value) => !Number.isNaN(value));
      if (fn === "sum") return numbers.reduce((sum, value) => sum + value, 0);
      if (!numbers.length) return fn === "avg" ? new ExcelError("#DIV/0!") : 0;
      if (fn === "avg") return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
      return fn === "min" ? Math.min(...numbers) : Math.max(...numbers);
    },
  };
}

/** Fill in the translated computed fields of one row. Engine fields run on the whole table, after. */
export async function computeRow(tx: Tx, spec: DaftarSpec, entity: Entity, row: Record<string, unknown>, now: Date): Promise<void> {
  const fields = ordered(computedFields(entity));
  const errors: Record<string, string> = { ...((row._errors ?? {}) as Record<string, string>) };
  const translated = fields.filter((field) => field.computed.eval === "translated");
  const exprs = translated.map((field) => (field.computed as { expr: Expr }).expr);
  const lookups = await loadRelated(tx, spec, entity, row, exprs);
  for (const field of translated) {
    const record = recordScalars(entity, { ...row, _errors: errors });
    const result = evaluate((field.computed as { expr: Expr }).expr, { record, now, ...lookups });
    const stored = storedForm(field, result);
    row[field.key] = stored.value;
    if (stored.error) errors[field.key] = stored.error;
    else delete errors[field.key];
  }
  row._errors = Object.keys(errors).length ? errors : null;
}

function letterIndex(letters: string): number {
  return [...letters].reduce((total, letter) => total * 26 + letter.charCodeAt(0) - 64, 0);
}

interface Layout {
  sheet: string;
  firstRow: number;
  firstColumn: number;
  columns: string[];
}

function layoutOf(mapping: EntityMapping): Layout {
  const source = mapping.sources[0];
  const start = source?.range ? /^([A-Z]+)/.exec(source.range)?.[1] : undefined;
  return {
    sheet: source?.sheet ?? mapping.entity,
    firstRow: mapping.headerRow + 1,
    firstColumn: start ? letterIndex(start) : 1,
    columns: mapping.columns.map((item) => item.field),
  };
}

function isEngine(field: FieldComputed): boolean {
  return field.computed.eval === "engine";
}

/**
 * Run a table's engine formulas, as the original sheet would: rows laid out by the mapping, each
 * formula copied down. Other mapped entities are loaded too, since a formula may read their sheets.
 */
export async function recomputeEngineFields(tx: Tx, spec: DaftarSpec, entity: Entity): Promise<void> {
  const fields = computedFields(entity).filter(isEngine);
  if (!fields.length) return;
  const mapping = spec.mapping.find((item) => item.entity === entity.key);
  const rows = await tx.selectFrom(tableOf(entity.key)).selectAll().orderBy("_seq").execute();
  if (!mapping) {
    for (const row of rows) await saveEngineErrors(tx, entity, row, fields);
    return;
  }
  const cells: EngineCell[] = [];
  const addValues = (other: Entity, otherRows: Record<string, unknown>[], layout: Layout): void => {
    otherRows.forEach((row, index) => {
      const record = recordScalars(other, row);
      layout.columns.forEach((key, position) => {
        const field = other.fields.find((item) => item.key === key);
        if (field?.type === "computed" && isEngine(field) && other === entity) return;
        const value = record[key];
        cells.push({ sheet: layout.sheet, row: layout.firstRow + index, column: layout.firstColumn + position, value: value ?? null });
      });
    });
  };
  for (const other of spec.entities) {
    const otherMapping = spec.mapping.find((item) => item.entity === other.key);
    if (!otherMapping) continue;
    const otherRows = other === entity ? rows : await tx.selectFrom(tableOf(other.key)).selectAll().orderBy("_seq").execute();
    addValues(other, otherRows, layoutOf(otherMapping));
  }
  const layout = layoutOf(mapping);
  const targets: { sheet: string; row: number; column: number; key: string; index: number }[] = [];
  for (const field of fields) {
    const position = layout.columns.indexOf(field.key);
    if (position < 0) continue;
    rows.forEach((_, index) => {
      const place = { sheet: layout.sheet, row: layout.firstRow + index, column: layout.firstColumn + position };
      cells.push({ ...place, formula: shiftRows((field.computed as ComputedEngine).excel, index) });
      targets.push({ ...place, key: field.key, index });
    });
  }
  const results = evaluateCells(cells, targets);
  targets.forEach((target, position) => {
    const field = fields.find((item) => item.key === target.key) as FieldComputed;
    const row = rows[target.index] as Record<string, unknown>;
    const stored = storedForm(field, results[position] ?? null);
    const errors = { ...((row._errors ?? {}) as Record<string, string>) };
    if (stored.error) errors[field.key] = stored.error;
    else delete errors[field.key];
    row._errors = Object.keys(errors).length ? errors : null;
    row[`__next_${field.key}`] = stored.value;
  });
  for (const row of rows) {
    const set: Record<string, unknown> = { _errors: row._errors ? JSON.stringify(row._errors) : null };
    for (const field of fields) if (`__next_${field.key}` in row) set[field.key] = row[`__next_${field.key}`];
    await tx.updateTable(tableOf(entity.key)).set(set).where("_id", "=", row._id).execute();
  }
}

async function saveEngineErrors(tx: Tx, entity: Entity, row: Record<string, unknown>, fields: FieldComputed[]): Promise<void> {
  // Never a silently wrong value: with no layout to run it on, the formula reports that it can't.
  const errors = { ...((row._errors ?? {}) as Record<string, string>) };
  for (const field of fields) errors[field.key] = "#ENGINE!";
  await tx.updateTable(tableOf(entity.key)).set({ _errors: JSON.stringify(errors) }).where("_id", "=", row._id).execute();
}

/** Other tables whose stored results read this one: their related and rollup fields, and sheets. */
export async function recomputeDependents(tx: Tx, spec: DaftarSpec, entity: Entity, id: string, now: Date, parentIds: Record<string, unknown>): Promise<void> {
  for (const other of spec.entities) {
    const translated = computedFields(other).filter((field) => field.computed.eval === "translated");
    if (translated.length) {
      const nodes: Expr[] = [];
      translated.forEach((field) => walk((field.computed as { expr: Expr }).expr, (node) => nodes.push(node)));
      for (const link of other.fields) {
        if (link.type === "link" && link.target === entity.key && nodes.some((node) => node.kind === "related" && node.via === link.key)) {
          const rows = await tx.selectFrom(tableOf(other.key)).selectAll().where(link.key, "=", id).execute();
          for (const row of rows) await saveComputed(tx, spec, other, row, now);
        }
        if (link.type === "child" && link.target === entity.key && nodes.some((node) => node.kind === "rollup" && node.via === link.key)) {
          const parent = parentIds[link.via];
          if (parent) {
            const rows = await tx.selectFrom(tableOf(other.key)).selectAll().where("_id", "=", parent).execute();
            for (const row of rows) await saveComputed(tx, spec, other, row, now);
          }
        }
      }
    }
    if (other !== entity && computedFields(other).some(isEngine)) {
      const sheet = spec.mapping.find((item) => item.entity === entity.key)?.sources[0]?.sheet;
      const reads = sheet !== undefined && computedFields(other).some((field) => field.computed.excel.includes(`${sheet}!`) || field.computed.excel.includes(`'${sheet}'!`));
      if (reads) await recomputeEngineFields(tx, spec, other);
    }
  }
}

async function saveComputed(tx: Tx, spec: DaftarSpec, entity: Entity, row: Record<string, unknown>, now: Date): Promise<void> {
  await computeRow(tx, spec, entity, row, now);
  const set: Record<string, unknown> = { _errors: row._errors ? JSON.stringify(row._errors) : null };
  for (const field of computedFields(entity)) if (field.computed.store && field.computed.eval === "translated") set[field.key] = row[field.key];
  await tx.updateTable(tableOf(entity.key)).set(set).where("_id", "=", row._id).execute();
}
