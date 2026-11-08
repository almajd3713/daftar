/**
 * Between what a form holds and what the server stores. A form holds what a person typed: text in their own
 * language's habits, where `9.800,00` is a number. The server takes numbers and `YYYY-MM-DD`, and it stays the
 * only judge of what's valid: text that can't be read is sent as it is, so the error is in the server's words.
 */
import type { Entity, Field } from "@daftar/spec/types";
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

const same = (a: unknown, b: unknown): boolean => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** What an edit sends: only what changed, so it can't undo someone else's change to another field. */
export function changedValues(fields: readonly Field[], record: Record<string, unknown>, drafts: Drafts): Record<string, unknown> {
  return Object.fromEntries(fields.flatMap((field) => {
    const value = fromDraft(field, drafts[field.key] ?? "");
    return same(value, record[field.key]) ? [] : [[field.key, value]];
  }));
}
