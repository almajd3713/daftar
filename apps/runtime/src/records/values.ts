/** Check what a form sends against a field's type, and turn values into what the evaluator reads. */
import type { Entity, Field } from "@daftar/spec/types";

import { MESSAGES, type Message } from "../messages.js";
import { ExcelError, toSerial, type Scalar } from "../expr/evaluate.js";

const DIGITS: Record<string, string> = Object.fromEntries(
  [..."٠١٢٣٤٥٦٧٨٩"].map((digit, index) => [digit, String(index)]).concat([..."۰۱۲۳۴۵۶۷۸۹"].map((digit, index) => [digit, String(index)])),
);
const DATE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const PHONE = /^(\+213|00213|0)([5-7][0-9]{8}|[2-4][0-9]{7,8})$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isRealDate(text: string): boolean {
  if (!DATE.test(text)) return false;
  const moment = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(moment.getTime()) && moment.toISOString().startsWith(text);
}

export function westernDigits(text: string): string {
  return text.replace(/[٠-٩۰-۹]/g, (digit) => DIGITS[digit] ?? digit);
}

export type Checked = { value: unknown } | { error: Message };

export function checkValue(field: Field, input: unknown): Checked {
  if (input === null || input === "") return { value: null };
  switch (field.type) {
    case "text":
    case "longtext":
      return typeof input === "string" ? { value: input } : { error: MESSAGES.invalidText };
    case "integer": {
      const number = typeof input === "string" ? Number(westernDigits(input)) : input;
      return typeof number === "number" && Number.isInteger(number) ? { value: number } : { error: MESSAGES.invalidInteger };
    }
    case "decimal":
    case "money":
    case "percent": {
      const number = typeof input === "string" ? Number(westernDigits(input).replace(",", ".")) : input;
      return typeof number === "number" && Number.isFinite(number) ? { value: number } : { error: MESSAGES.invalidNumber };
    }
    case "date": {
      const text = typeof input === "string" ? westernDigits(input) : "";
      return isRealDate(text) ? { value: text } : { error: MESSAGES.invalidDate };
    }
    case "datetime": {
      const moment = typeof input === "string" ? new Date(input) : new Date(Number.NaN);
      return Number.isNaN(moment.getTime()) ? { error: MESSAGES.invalidDate } : { value: moment.toISOString() };
    }
    case "boolean":
      return typeof input === "boolean" ? { value: input } : { error: MESSAGES.invalidBoolean };
    case "choice":
      return field.choices.some((choice) => choice.key === input) ? { value: input } : { error: MESSAGES.invalidChoice };
    case "multichoice": {
      const allowed = new Set(field.choices.map((choice) => choice.key));
      return Array.isArray(input) && input.every((item) => allowed.has(item as string)) ? { value: input } : { error: MESSAGES.invalidChoice };
    }
    case "phone": {
      const text = typeof input === "string" ? westernDigits(input).replace(/[\s.\-()]/g, "") : "";
      return PHONE.test(text) ? { value: text } : { error: MESSAGES.invalidPhone };
    }
    case "email":
      return typeof input === "string" && EMAIL.test(input) ? { value: input.trim() } : { error: MESSAGES.invalidEmail };
    case "link":
      return typeof input === "string" && UUID.test(input) ? { value: input } : { error: MESSAGES.invalidLink };
    default:
      return { error: MESSAGES.readOnly };
  }
}

/** A stored value as the formula evaluator reads it: dates are serial numbers. */
export function toScalar(field: Field | undefined, value: unknown): Scalar {
  if (value === null || value === undefined) return null;
  const kind = field?.type === "computed" ? field.resultType : field?.type;
  if ((kind === "date" || kind === "datetime") && typeof value === "string") {
    const moment = new Date(kind === "date" ? `${value}T00:00:00Z` : value);
    return Number.isNaN(moment.getTime()) ? null : toSerial(moment);
  }
  if (typeof value === "number" || typeof value === "string" || typeof value === "boolean") return value;
  return JSON.stringify(value);
}

export function recordScalars(entity: Entity, row: Record<string, unknown>): Record<string, Scalar> {
  const errors = (row._errors ?? {}) as Record<string, string>;
  const record: Record<string, Scalar> = {};
  for (const field of entity.fields) {
    const error = errors[field.key];
    record[field.key] = error ? new ExcelError(error) : toScalar(field, row[field.key]);
  }
  return record;
}
