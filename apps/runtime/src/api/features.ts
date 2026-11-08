/** Reads built on the spec: what a role may see of it, calculators, reminders and the register. */
import type { Calculator, CalculatorInput, CalculatorOutput, DaftarSpec, Entity, Field, Filter } from "@daftar/spec/types";

import { tableOf, column, type Db } from "../db.js";
import { BadQuery, FieldErrors, Forbidden, NotFound } from "../errors.js";
import type { Message } from "../messages.js";
import { evaluateCells, fromSerial, loadEngine } from "../expr/engine.js";
import { ExcelError, type Scalar } from "../expr/evaluate.js";
import { can, canSeeField, ownOnly, roleOf, visibleFields, type User } from "../records/access.js";
import { checkValue, toScalar } from "../records/values.js";

const CELL = /^([A-Z]+)([0-9]+)$/;

function place(sheet: string, ref: string): { sheet: string; row: number; column: number } {
  const match = CELL.exec(ref);
  if (!match) throw new BadQuery(`cell ${ref}`);
  const letters = match[1] as string;
  return { sheet, row: Number(match[2]), column: [...letters].reduce((total, letter) => total * 26 + letter.charCodeAt(0) - 64, 0) };
}

function stripProvenance<T>(value: T): T {
  if (Array.isArray(value)) return value.map(stripProvenance) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).filter(([key]) => key !== "provenance").map(([key, item]) => [key, stripProvenance(item)])) as T;
  }
  return value;
}

/** The spec, filtered: only what this role may read, with hidden fields gone from every part. */
export function metaFor(spec: DaftarSpec, user: User): Record<string, unknown> {
  const readable = spec.entities.filter((entity) => can(spec, user, entity.key, "read"));
  const keys = new Set(readable.map((entity) => entity.key));
  const shown = new Map(readable.map((entity) => [entity.key, new Set(visibleFields(spec, user, entity).map((field) => field.key))]));
  const seen = (entity: string, field: string): boolean => shown.get(entity)?.has(field) ?? false;
  const filters = (entity: string, list: Filter[] | undefined): Filter[] => (list ?? []).filter((item) => seen(entity, item.field));
  const role = roleOf(spec, user);
  return stripProvenance({
    specVersion: spec.specVersion,
    app: spec.app,
    user: { username: user.username, role: user.role },
    permissions: role?.permissions ?? [],
    // Only the owner manages accounts, so only the owner needs the list of roles.
    ...(user.role === "owner" ? { roles: spec.roles.map((item) => ({ key: item.key, label: item.label })) } : {}),
    entities: readable.map((entity) => ({
      ...entity,
      fields: visibleFields(spec, user, entity).map((field) => {
        // How a value is calculated stays on the server: a formula can give away a sensitive one.
        return field.type === "computed" ? { ...field, computed: undefined } : field;
      }),
    })),
    views: spec.views
      .filter((view) => keys.has(view.entity))
      .map((view) =>
        view.type === "list"
          ? {
              ...view,
              columns: view.columns.filter((key) => seen(view.entity, key)),
              sort: (view.sort ?? []).filter((item) => seen(view.entity, item.field)),
              totals: (view.totals ?? []).filter((key) => seen(view.entity, key)),
              filters: filters(view.entity, view.filters),
            }
          : { ...view, cardFields: view.cardFields.filter((key) => seen(view.entity, key)), filters: filters(view.entity, view.filters) },
      ),
    forms: spec.forms
      .filter((form) => keys.has(form.entity) && can(spec, user, form.entity, "create"))
      .map((form) => ({ ...form, sections: form.sections.map((section) => ({ ...section, fields: section.fields.filter((key) => seen(form.entity, key)) })).filter((section) => section.fields.length) })),
    dashboards: spec.dashboards
      .map((dashboard) => ({
        ...dashboard,
        widgets: dashboard.widgets.filter(
          (widget) => keys.has(widget.entity) && (!widget.field || seen(widget.entity, widget.field)) && (widget.type === "kpi" || seen(widget.entity, widget.groupBy)),
        ),
      }))
      .filter((dashboard) => dashboard.widgets.length),
    workflows: spec.workflows.filter((workflow) => keys.has(workflow.entity)),
    calculators: spec.calculators.map((calculator) => {
      return { ...calculator, cells: undefined, testCases: undefined, outputs: calculator.outputs.filter((output) => canSeeField(spec, user, output)) };
    }),
  });
}

/** An output as the API gives any value. A date is `YYYY-MM-DD` here too, though the engine only knows serial numbers. */
function outcome(output: CalculatorOutput, value: Scalar): unknown {
  if (value instanceof ExcelError) return { error: value.code };
  return output.type === "date" && typeof value === "number" ? fromSerial(value).toISOString().slice(0, 10) : value;
}

/** An input is checked like a field of its type. A choice with no list has nothing to be checked against. */
function fieldOf(port: CalculatorInput): Field {
  const { key, label } = port;
  if (port.type !== "choice") return { key, label, type: port.type };
  return port.choices ? { key, label, type: "choice", choices: port.choices } : { key, label, type: "text" };
}

export async function runCalculator(spec: DaftarSpec, user: User, key: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
  const calculator: Calculator | undefined = spec.calculators.find((item) => item.key === key);
  if (!calculator) throw new NotFound();
  await loadEngine();
  const values = new Map<string, Scalar>();
  const problems: Record<string, Message> = {};
  for (const port of calculator.inputs) {
    const raw = input[port.key] === undefined ? port.default : input[port.key];
    const field = fieldOf(port);
    const checked = checkValue(field, raw ?? null);
    if ("error" in checked) {
      problems[port.key] = checked.error;
      continue;
    }
    values.set(`${port.sheet}!${port.cell}`, toScalar(field, checked.value));
  }
  if (Object.keys(problems).length) throw new FieldErrors(problems);
  const cells = calculator.cells.map((cell) => {
    const where = place(cell.sheet, cell.ref);
    const name = `${cell.sheet}!${cell.ref}`;
    if (values.has(name)) return { ...where, value: values.get(name) ?? null };
    return cell.f ? { ...where, formula: cell.f } : { ...where, value: cell.v ?? null };
  });
  const outputs = calculator.outputs.filter((output) => canSeeField(spec, user, output));
  const results = evaluateCells(cells, outputs.map((output) => place(output.sheet, output.cell)));
  return { outputs: Object.fromEntries(outputs.map((output, index) => [output.key, outcome(output, results[index] ?? null)])) };
}

function todayIn(timezone: string, now: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
}

const OPERATORS: Record<string, string> = { eq: "=", ne: "!=", lt: "<", le: "<=", gt: ">", ge: ">=" };

/** R-20: date rules, checked against today. A reminder is due when date + offset is today. */
export async function notificationsFor(db: Db, spec: DaftarSpec, user: User, timezone: string, now: Date): Promise<Record<string, unknown>[]> {
  const today = todayIn(timezone, now);
  const found: Record<string, unknown>[] = [];
  for (const reminder of spec.reminders) {
    if (!reminder.roles.includes(user.role as "owner") || !can(spec, user, reminder.entity, "read")) continue;
    let query = db
      .selectFrom(tableOf(reminder.entity))
      .select(["_id", "_name", column(reminder.dateField).as("date")])
      .where(column(reminder.dateField), "=", addDays(today, -reminder.offsetDays));
    if (ownOnly(spec, user, reminder.entity)) query = query.where("_created_by", "=", user.id);
    for (const filter of reminder.filters ?? []) {
      const ref = column(filter.field);
      if (filter.op in OPERATORS) query = query.where(ref, OPERATORS[filter.op] as "=", filter.value as string);
      else if (filter.op === "in") query = query.where(ref, "in", filter.value as string[]);
      else if (filter.op === "isEmpty") query = query.where(ref, "is", null);
      else if (filter.op === "isNotEmpty") query = query.where(ref, "is not", null);
    }
    for (const row of await query.execute()) {
      found.push({ reminder: reminder.key, label: reminder.label, message: reminder.message, entity: reminder.entity, recordId: row._id, name: row._name, date: row.date });
    }
  }
  return found;
}

/** R-24: the processing register, built from the spec. Change history is the automated log. */
export function processingRegister(spec: DaftarSpec, user: User, processor: string | undefined): Record<string, unknown> {
  if (user.role !== "owner" && user.role !== "accountant") throw new Forbidden();
  const personal = spec.entities.filter((entity: Entity) => entity.personalData);
  return {
    app: spec.app.name,
    processor: processor ?? null,
    personalData: personal.map((entity) => ({
      entity: entity.key,
      label: entity.label,
      retention: entity.retention ?? null,
      fields: entity.fields.filter((field) => "personalData" in field && field.personalData).map((field) => ({ key: field.key, label: field.label })),
      accessBy: spec.roles
        .filter((role) => role.permissions.some((item) => item.entity === entity.key && item.actions.includes("read")))
        .map((role) => ({ role: role.key, label: role.label })),
    })),
    roles: spec.roles.map((role) => ({ key: role.key, label: role.label })),
    log: { kind: "change history", retentionMonths: spec.history.retentionMonths ?? null },
  };
}

/** Compliance export (C-9). A leading = + - @ is neutralised so a spreadsheet won't run it. */
export function auditCsv(rows: Record<string, unknown>[]): string {
  const cell = (value: unknown): string => {
    let text = typeof value === "string" ? value : value === undefined || value === null ? "" : JSON.stringify(value);
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  };
  const columns = ["id", "at", "actor", "source", "batchId", "entity", "recordId", "op", "changes"];
  return [columns.join(","), ...rows.map((row) => columns.map((key) => cell(row[key])).join(","))].join("\r\n") + "\r\n";
}
