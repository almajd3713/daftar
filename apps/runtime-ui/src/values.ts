/**
 * Between what a form holds and what the server stores. A form holds what a person typed: text in their own
 * language's habits, where `9.800,00` is a number. The server takes numbers and `YYYY-MM-DD`, and it stays the
 * only judge of what's valid: text that can't be read is sent as it is, so the error is in the server's words.
 */
import type { CalculatorInput, CalculatorOutput, Entity, Field } from "@daftar/spec/types";
import { formatNumber, parseAmount, type Locale } from "@daftar/ui/format";

export type Draft = string | boolean | string[];
export type Drafts = Record<string, Draft>;

/** A field's value type, seeing through a computed field. */
export function kindOf(field: Field): string {
  return field.type === "computed" ? field.resultType : field.type;
}

export function isNumeric(field: Field): boolean {
  return ["integer", "decimal", "money", "percent"].includes(kindOf(field));
}

export function precisionOf(field: Field): number {
  const kind = kindOf(field);
  if (kind === "integer") return 0;
  return ("precision" in field ? field.precision : undefined) ?? 2;
}

/** Fields a person can type into. A computed field or a list of children isn't one. */
export function isEditable(field: Field): boolean {
  return field.type !== "computed" && field.type !== "child";
}

function localDateTime(value: string): string {
  const moment = new Date(value);
  if (Number.isNaN(moment.getTime())) return value;
  const pad = (part: number): string => String(part).padStart(2, "0");
  return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}T${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
}

/** A stored value as plain text. A value of an unexpected shape stays readable rather than "[object Object]". */
export function textOf(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : JSON.stringify(value);
}

export function toDraft(field: Field, value: unknown, locale: Locale): Draft {
  switch (field.type) {
    case "boolean":
      return value === true;
    case "multichoice":
      return Array.isArray(value) ? (value as string[]) : [];
    case "integer":
    case "decimal":
    case "money":
      return typeof value === "number" ? formatNumber(value, locale, precisionOf(field)).replace(/[\u200e\u200f]/g, "") : "";
    case "percent":
      // Stored as a ratio, as Excel does, and typed as the number a person sees beside the % sign.
      return typeof value === "number" ? formatNumber(value * 100, locale, precisionOf(field)).replace(/[\u200e\u200f]/g, "") : "";
    case "datetime":
      return typeof value === "string" ? localDateTime(value) : "";
    default:
      return textOf(value);
  }
}

export function fromDraft(field: Field, draft: Draft): unknown {
  if (typeof draft === "boolean") return draft;
  if (Array.isArray(draft)) return draft.length ? draft : null;
  const text = draft.trim();
  if (!text) return null;
  switch (field.type) {
    case "integer":
    case "decimal":
    case "money":
      return parseAmount(text) ?? text;
    case "percent": {
      const number = parseAmount(text.replace(/%\s*$/, ""));
      return number === null ? text : number / 100;
    }
    case "datetime": {
      const moment = new Date(text);
      return Number.isNaN(moment.getTime()) ? text : moment.toISOString();
    }
    case "longtext":
      return draft;
    default:
      return text;
  }
}

export function formFields(entity: Entity, keys: readonly string[]): Field[] {
  return keys.flatMap((key) => {
    const field = entity.fields.find((item) => item.key === key);
    return field && isEditable(field) ? [field] : [];
  });
}

export function startingDrafts(fields: readonly Field[], record: Record<string, unknown> | undefined, locale: Locale): Drafts {
  return Object.fromEntries(
    fields.map((field) => {
      const start = record ? record[field.key] : "default" in field ? field.default : undefined;
      return [field.key, toDraft(field, start, locale)];
    }),
  );
}

/** What a new record sends. */
export function allValues(fields: readonly Field[], drafts: Drafts): Record<string, unknown> {
  return Object.fromEntries(fields.flatMap((field) => {
    const value = fromDraft(field, drafts[field.key] ?? "");
    return value === null ? [] : [[field.key, value]];
  }));
}

/** A workbook's number has the decimals it has: a count of 2 isn't "2,00". Six is past anything a person types. */
function decimalsIn(value: unknown): number {
  if (typeof value !== "number" || Number.isInteger(value)) return 0;
  return Math.min(String(value).split(".")[1]?.length ?? 2, 6);
}

/** A calculator's input takes the same input, and the same reading of what's typed, as a field of its type. */
export function fieldOfInput(port: CalculatorInput): Field {
  const { key, label, type, choices } = port;
  const start = port.default === null || port.default === undefined ? {} : { default: port.default };
  if (type === "choice") return choices ? { key, label, type, choices, ...start } : { key, label, type: "text", ...start };
  return { key, label, type, ...start, ...(type === "decimal" ? { precision: decimalsIn(port.default) } : {}) };
}

/**
 * What a calculator sends: every input, blank ones as null. The server gives an input it isn't sent its default, so
 * leaving a cleared one out would calculate with a number the person just removed.
 */
export function everyValue(fields: readonly Field[], drafts: Drafts): Record<string, unknown> {
  return Object.fromEntries(fields.map((field) => [field.key, fromDraft(field, drafts[field.key] ?? "")]));
}

export function outputError(value: unknown): string | undefined {
  if (typeof value !== "object" || value === null || !("error" in value)) return undefined;
  return textOf(value.error);
}

/** A result comes from a workbook's formula, so it isn't always what its type says: `=IF(A1>0,A1,"-")` is common. */
export function fitsType(type: CalculatorOutput["type"], value: unknown): boolean {
  switch (type) {
    case "integer":
    case "decimal":
    case "money":
    case "percent":
      return typeof value === "number";
    case "date":
      return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
    case "boolean":
      return typeof value === "boolean";
    default:
      return true;
  }
}

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** What an edit sends: only what changed, so it can't undo someone else's change to another field. */
export function changedValues(fields: readonly Field[], record: Record<string, unknown>, drafts: Drafts): Record<string, unknown> {
  return Object.fromEntries(fields.flatMap((field) => {
    const value = fromDraft(field, drafts[field.key] ?? "");
    return same(value, record[field.key]) ? [] : [[field.key, value]];
  }));
}
