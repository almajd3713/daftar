/**
 * Evaluate a C-3 expression tree on one record, with Excel's semantics. Dates are serial numbers.
 * This mirrors the worker's evaluate.py; `packages/spec/fixtures/expression-cases.json` holds them together.
 */
import type { Expr } from "@daftar/spec/types";

export class ExcelError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

const DIV0 = "#DIV/0!";
const NA = "#N/A";
const NUM = "#NUM!";
const VALUE = "#VALUE!";

export type Scalar = number | string | boolean | null | ExcelError;
type Plain = number | string | boolean | null;
const MS_PER_DAY = 86_400_000;
const EPOCH = Date.UTC(1899, 11, 30);

export function toSerial(date: Date): number {
  const whole = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
  let days = Math.round((whole - EPOCH) / MS_PER_DAY);
  if (days < 61) days -= 1; // Excel's 1900 leap-year bug shifts everything before 1 March 1900.
  const seconds = date.getUTCHours() * 3600 + date.getUTCMinutes() * 60 + date.getUTCSeconds();
  return days + seconds / 86_400;
}

export function fromSerial(serial: number): Date {
  const days = Math.floor(serial);
  if (days < 1) throw new ExcelError(NUM);
  const offset = days < 60 ? days + 1 : days;
  const seconds = Math.round((serial - days) * 86_400);
  return new Date(EPOCH + offset * MS_PER_DAY + seconds * 1000);
}

export function toNumber(value: Plain): number {
  if (value === null) return 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  const text = value.trim();
  const parsed = Number(text);
  if (text === "" || Number.isNaN(parsed)) throw new ExcelError(VALUE);
  return parsed;
}

export function toText(value: Plain): string {
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "number") {
    if (Number.isInteger(value) && Math.abs(value) < 1e15) return String(value);
    return String(Number(value.toPrecision(15)));
  }
  return value;
}

function toBool(value: Plain): boolean {
  if (typeof value === "boolean") return value;
  if (value === null) return false;
  if (typeof value === "number") return value !== 0;
  const text = value.trim().toUpperCase();
  if (text === "TRUE") return true;
  if (text === "FALSE") return false;
  throw new ExcelError(VALUE);
}

function rank(value: Plain): number {
  if (typeof value === "boolean") return 2;
  return typeof value === "string" ? 1 : 0;
}

/** Excel's order: numbers, then text ignoring case, then booleans. Blank adapts to the other side. */
export function compare(leftIn: Plain, rightIn: Plain): number {
  let left = leftIn;
  let right = rightIn;
  if (left === null) left = typeof right === "string" ? "" : typeof right === "boolean" ? false : 0;
  if (right === null) right = typeof left === "string" ? "" : typeof left === "boolean" ? false : 0;
  if (rank(left) !== rank(right)) return rank(left) < rank(right) ? -1 : 1;
  if (typeof left === "string" && typeof right === "string") {
    const a = left.toLowerCase();
    const b = right.toLowerCase();
    return a === b ? 0 : a > b ? 1 : -1;
  }
  return left === right ? 0 : (left as number) > (right as number) ? 1 : -1;
}

function nearZero(result: number, a: number, b: number): number {
  // Excel's near-zero compensation: a sum that cancels to within 15 digits is exactly zero.
  return result !== 0 && Math.abs(result) < 1e-15 * Math.max(Math.abs(a), Math.abs(b)) ? 0 : result;
}

function binary(op: string, left: Plain, right: Plain): Plain {
  if (op === "concat") return toText(left) + toText(right);
  if (["eq", "ne", "lt", "le", "gt", "ge"].includes(op)) {
    const order = compare(left, right);
    return { eq: order === 0, ne: order !== 0, lt: order < 0, le: order <= 0, gt: order > 0, ge: order >= 0 }[op] ?? false;
  }
  const a = toNumber(left);
  const b = toNumber(right);
  switch (op) {
    case "add":
      return nearZero(a + b, a, b);
    case "sub":
      return nearZero(a - b, a, b);
    case "mul":
      return a * b;
    case "div":
      if (b === 0) throw new ExcelError(DIV0);
      return a / b;
    case "pow": {
      if (a === 0 && b === 0) throw new ExcelError(NUM);
      if (a === 0 && b < 0) throw new ExcelError(DIV0);
      const result = a ** b;
      if (Number.isNaN(result)) throw new ExcelError(NUM);
      return result;
    }
    default:
      throw new ExcelError(VALUE);
  }
}

/** Rounds on 15 significant digits, as Excel sees a number, so 1.005 rounds to 1.01. */
function roundDigits(number: number, digits: number, mode: "half" | "up" | "down"): number {
  const places = Math.trunc(digits);
  const scaled = Number(`${Number(Math.abs(number).toPrecision(15))}e${places}`);
  let rounded: number;
  if (mode === "half") rounded = Math.floor(scaled + 0.5);
  else if (mode === "up") rounded = Math.ceil(scaled);
  else rounded = Math.floor(scaled);
  const result = Number(`${rounded}e${-places}`);
  return number < 0 ? -result : result;
}

function numbers(args: { value: Plain; fromCell: boolean }[]): number[] {
  const found: number[] = [];
  for (const { value, fromCell } of args) {
    if (fromCell) {
      if (typeof value === "number") found.push(value);
    } else if (value !== null) {
      found.push(toNumber(value));
    }
  }
  return found;
}

function makeDate(yearIn: number, monthIn: number, dayIn: number): number {
  let year = Math.trunc(yearIn);
  const day = Math.trunc(dayIn);
  if (year >= 0 && year < 1900) year += 1900;
  const total = Math.trunc(monthIn) - 1;
  year += Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12;
  if (year < 1 || year > 9999) throw new ExcelError(NUM);
  return toSerial(new Date(Date.UTC(year, month, 1) + (day - 1) * MS_PER_DAY));
}

function addMonths(serial: number, months: number): Date {
  const moment = fromSerial(serial);
  const total = moment.getUTCFullYear() * 12 + moment.getUTCMonth() + Math.trunc(months);
  const year = Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12;
  const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(moment.getUTCDate(), last)));
}

function endOfMonth(serial: number, months: number): number {
  const moment = addMonths(serial, months);
  return toSerial(new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth() + 1, 0)));
}

function weekday(serial: number, kind: number): number {
  const day = (((Math.floor(serial) - 1) % 7) + 7) % 7; // 0 is Sunday.
  if (kind === 1) return day + 1;
  if (kind === 2) return ((day + 6) % 7) + 1;
  if (kind === 3) return (day + 6) % 7;
  throw new ExcelError(NUM);
}

function find(needle: string, haystack: string, start: number): number {
  const position = start < 1 ? -1 : haystack.indexOf(needle, Math.trunc(start) - 1);
  if (position < 0) throw new ExcelError(VALUE);
  return position + 1;
}

function substitute(text: string, old: string, next: string, instance: number | null): string {
  if (!old) return text;
  if (instance === null) return text.split(old).join(next);
  let position = -1;
  for (let i = 0; i < Math.trunc(instance); i += 1) {
    position = text.indexOf(old, position + 1);
    if (position < 0) return text;
  }
  return text.slice(0, position) + next + text.slice(position + old.length);
}

function proper(text: string): string {
  let start = true;
  let out = "";
  for (const letter of text) {
    out += start ? letter.toUpperCase() : letter.toLowerCase();
    start = !/\p{L}/u.test(letter);
  }
  return out;
}

const N = toNumber;
const T = toText;
const time = (value: Plain): Date => fromSerial(N(value) >= 1 ? N(value) : N(value) + 1);
const nth = (args: Plain[], index: number, fallback: Plain = null): Plain => (index < args.length ? (args[index] as Plain) : fallback);

function mod(a: number, b: number): number {
  if (b === 0) throw new ExcelError(DIV0);
  return a - b * Math.floor(a / b);
}

function significance(number: number, step: number, up: boolean): number {
  if (step === 0) {
    if (up) return 0;
    throw new ExcelError(DIV0);
  }
  if (number > 0 && step < 0) throw new ExcelError(NUM);
  const ratio = roundDigits(number / step, 12, "half");
  return (up ? Math.ceil(ratio) : Math.floor(ratio)) * step;
}

const SIMPLE: Record<string, (args: Plain[]) => Plain> = {
  ABS: (a) => Math.abs(N(nth(a, 0))),
  INT: (a) => Math.floor(N(nth(a, 0))),
  SQRT: (a) => {
    const value = N(nth(a, 0));
    if (value < 0) throw new ExcelError(NUM);
    return Math.sqrt(value);
  },
  POWER: (a) => binary("pow", nth(a, 0), nth(a, 1)),
  MOD: (a) => mod(N(nth(a, 0)), N(nth(a, 1))),
  ROUND: (a) => roundDigits(N(nth(a, 0)), N(nth(a, 1, 0)), "half"),
  ROUNDUP: (a) => roundDigits(N(nth(a, 0)), N(nth(a, 1, 0)), "up"),
  ROUNDDOWN: (a) => roundDigits(N(nth(a, 0)), N(nth(a, 1, 0)), "down"),
  MROUND: (a) => {
    const value = N(nth(a, 0));
    const step = N(nth(a, 1));
    if (step === 0) return 0;
    if (value * step < 0) throw new ExcelError(NUM);
    return roundDigits(value / step, 0, "half") * step;
  },
  CEILING: (a) => significance(N(nth(a, 0)), N(nth(a, 1, 1)), true),
  FLOOR: (a) => significance(N(nth(a, 0)), N(nth(a, 1, 1)), false),
  NOT: (a) => !toBool(nth(a, 0)),
  CONCATENATE: (a) => a.map((item) => T(item)).join(""),
  CONCAT: (a) => a.map((item) => T(item)).join(""),
  LEFT: (a) => {
    const count = N(nth(a, 1, 1));
    if (count < 0) throw new ExcelError(VALUE);
    return T(nth(a, 0)).slice(0, Math.trunc(count));
  },
  RIGHT: (a) => {
    const count = N(nth(a, 1, 1));
    if (count < 0) throw new ExcelError(VALUE);
    return count >= 1 ? T(nth(a, 0)).slice(-Math.trunc(count)) : "";
  },
  MID: (a) => {
    const start = Math.trunc(N(nth(a, 1)));
    const length = Math.trunc(N(nth(a, 2)));
    if (start < 1 || length < 0) throw new ExcelError(VALUE);
    return T(nth(a, 0)).slice(start - 1, start - 1 + length);
  },
  LEN: (a) => T(nth(a, 0)).length,
  TRIM: (a) => T(nth(a, 0)).split(" ").filter(Boolean).join(" "),
  UPPER: (a) => T(nth(a, 0)).toUpperCase(),
  LOWER: (a) => T(nth(a, 0)).toLowerCase(),
  PROPER: (a) => proper(T(nth(a, 0))),
  SUBSTITUTE: (a) => substitute(T(nth(a, 0)), T(nth(a, 1)), T(nth(a, 2)), a.length > 3 ? N(nth(a, 3)) : null),
  REPLACE: (a) => {
    const text = T(nth(a, 0));
    const start = Math.trunc(N(nth(a, 1))) - 1;
    return text.slice(0, start) + T(nth(a, 3)) + text.slice(start + Math.trunc(N(nth(a, 2))));
  },
  FIND: (a) => find(T(nth(a, 0)), T(nth(a, 1)), N(nth(a, 2, 1))),
  SEARCH: (a) => find(T(nth(a, 0)).toLowerCase(), T(nth(a, 1)).toLowerCase(), N(nth(a, 2, 1))),
  VALUE: (a) => toNumber(nth(a, 0) ?? 0),
  EXACT: (a) => T(nth(a, 0)) === T(nth(a, 1)),
  REPT: (a) => T(nth(a, 0)).repeat(Math.trunc(N(nth(a, 1)))),
  DATE: (a) => makeDate(N(nth(a, 0)), N(nth(a, 1)), N(nth(a, 2))),
  YEAR: (a) => fromSerial(N(nth(a, 0))).getUTCFullYear(),
  MONTH: (a) => fromSerial(N(nth(a, 0))).getUTCMonth() + 1,
  DAY: (a) => fromSerial(N(nth(a, 0))).getUTCDate(),
  HOUR: (a) => time(nth(a, 0)).getUTCHours(),
  MINUTE: (a) => time(nth(a, 0)).getUTCMinutes(),
  SECOND: (a) => time(nth(a, 0)).getUTCSeconds(),
  WEEKDAY: (a) => weekday(N(nth(a, 0)), N(nth(a, 1, 1))),
  EDATE: (a) => toSerial(addMonths(N(nth(a, 0)), N(nth(a, 1)))),
  EOMONTH: (a) => endOfMonth(N(nth(a, 0)), N(nth(a, 1))),
  DAYS: (a) => Math.floor(N(nth(a, 0))) - Math.floor(N(nth(a, 1))),
  ISBLANK: (a) => nth(a, 0) === null,
  ISNUMBER: (a) => typeof nth(a, 0) === "number",
  ISTEXT: (a) => typeof nth(a, 0) === "string",
  NA: () => {
    throw new ExcelError(NA);
  },
  TRUE: () => true,
  FALSE: () => false,
};
const AGGREGATES = new Set(["SUM", "MIN", "MAX", "AVERAGE", "COUNT", "COUNTA", "PRODUCT"]);
const LAZY = new Set(["IF", "IFS", "AND", "OR", "IFERROR", "IFNA", "ISERROR", "ISNA", "SWITCH"]);
const CLOCK = new Set(["TODAY", "NOW"]);
export const TRANSLATABLE = new Set([...Object.keys(SIMPLE), ...AGGREGATES, ...LAZY, ...CLOCK]);

export interface EvalContext {
  record: Record<string, Scalar>;
  related?: (via: string, field: string) => Scalar;
  rollup?: (via: string, fn: string, field: string | undefined) => Scalar;
  now?: Date;
}

function plain(value: Scalar): Plain {
  if (value instanceof ExcelError) throw value;
  return value;
}

export function evaluate(expr: Expr, context: EvalContext): Scalar {
  try {
    return run(expr, context);
  } catch (error) {
    if (error instanceof ExcelError) return error;
    throw error;
  }
}

function run(expr: Expr, context: EvalContext): Plain {
  switch (expr.kind) {
    case "literal":
      return expr.value;
    case "field":
      return plain(context.record[expr.field] ?? null);
    case "related":
      if (!context.related) throw new ExcelError(NA);
      return plain(context.related(expr.via, expr.field));
    case "rollup":
      if (!context.rollup) throw new ExcelError(NA);
      return plain(context.rollup(expr.via, expr.fn, expr.field));
    case "op": {
      const [first, second] = expr.args;
      if (expr.op === "neg") return -toNumber(run(first, context));
      if (expr.op === "pct") return toNumber(run(first, context)) / 100;
      return binary(expr.op, run(first, context), run(second as Expr, context));
    }
    case "call":
      return call(expr.fn, expr.args, context);
    default:
      throw new ExcelError(VALUE);
  }
}

function aggregate(name: string, args: Expr[], context: EvalContext): Plain {
  const values = args.map((arg) => ({ value: run(arg, context), fromCell: arg.kind === "field" || arg.kind === "related" }));
  if (name === "COUNTA") return values.filter(({ value, fromCell }) => value !== null || !fromCell).length;
  const found = numbers(values);
  if (name === "COUNT") return found.length;
  if (name === "SUM") return found.reduce((sum, value) => sum + value, 0);
  if (name === "PRODUCT") return found.length ? found.reduce((product, value) => product * value, 1) : 0;
  if (name === "AVERAGE") {
    if (!found.length) throw new ExcelError(DIV0);
    return found.reduce((sum, value) => sum + value, 0) / found.length;
  }
  if (!found.length) return 0;
  return name === "MAX" ? Math.max(...found) : Math.min(...found);
}

function lazy(name: string, args: Expr[], context: EvalContext): Plain {
  const at = (index: number): Expr => args[index] as Expr;
  switch (name) {
    case "IF":
      if (toBool(run(at(0), context))) return args.length > 1 ? run(at(1), context) : true;
      return args.length > 2 ? run(at(2), context) : false;
    case "IFS":
      for (let i = 0; i + 1 < args.length; i += 2) {
        if (toBool(run(at(i), context))) return run(at(i + 1), context);
      }
      throw new ExcelError(NA);
    case "SWITCH": {
      const subject = run(at(0), context);
      const pairs = args.length - 1;
      for (let i = 1; i + 1 < args.length; i += 2) {
        if (compare(subject, run(at(i), context)) === 0) return run(at(i + 1), context);
      }
      if (pairs % 2) return run(at(args.length - 1), context);
      throw new ExcelError(NA);
    }
    case "AND":
    case "OR": {
      const values = args.map((arg) => run(arg, context)); // Excel evaluates all, so errors propagate.
      const tests = values.filter((value) => value !== null).map(toBool);
      if (!tests.length) throw new ExcelError(VALUE);
      return name === "AND" ? tests.every(Boolean) : tests.some(Boolean);
    }
    default:
      break;
  }
  let value: Plain;
  try {
    value = run(at(0), context);
  } catch (error) {
    if (!(error instanceof ExcelError)) throw error;
    if (name === "ISERROR") return true;
    if (name === "ISNA") return error.code === NA;
    if (name === "IFERROR" || error.code === NA) return run(at(1), context);
    throw error;
  }
  if (name === "ISERROR" || name === "ISNA") return false;
  return value === null ? "" : value;
}

function call(name: string, args: Expr[], context: EvalContext): Plain {
  if (LAZY.has(name)) return lazy(name, args, context);
  if (AGGREGATES.has(name)) return aggregate(name, args, context);
  if (CLOCK.has(name)) {
    if (!context.now) throw new ExcelError(NA);
    const serial = toSerial(context.now);
    return name === "TODAY" ? Math.floor(serial) : serial;
  }
  const fn = SIMPLE[name];
  if (!fn) throw new ExcelError("#NAME?");
  return fn(args.map((arg) => run(arg, context)));
}
