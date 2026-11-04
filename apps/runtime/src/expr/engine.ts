/** Our interface to the formula engine. This is the only module that may import Formualizer (D-5). */
import { Workbook, initializeWasm } from "formualizer";

import { ExcelError, fromSerial, toSerial, type Scalar } from "./evaluate.js";

let ready: Promise<unknown> | undefined;

export async function loadEngine(): Promise<void> {
  ready ??= Promise.resolve(initializeWasm?.());
  await ready;
}

export interface EngineCell {
  sheet: string;
  row: number;
  column: number;
  value?: Scalar;
  formula?: string;
}

const ERROR_TEXT = /^#[A-Z0-9/!?_]+$/;

function fromEngine(raw: unknown): Scalar {
  if (raw === null || raw === undefined) return null;
  if (raw instanceof Date) return toSerial(raw);
  if (typeof raw === "number" || typeof raw === "boolean") return raw;
  if (typeof raw === "string") return ERROR_TEXT.test(raw) ? new ExcelError(raw) : raw;
  return new ExcelError("#VALUE!");
}

/** Build a small workbook and evaluate the targets. Dates go in and come out as serial numbers. */
export function evaluateCells(cells: EngineCell[], targets: { sheet: string; row: number; column: number }[]): Scalar[] {
  const workbook = new Workbook();
  const sheets = new Set<string>();
  try {
    for (const target of [...cells, ...targets]) {
      if (!sheets.has(target.sheet)) {
        workbook.addSheet(target.sheet);
        sheets.add(target.sheet);
      }
    }
    for (const cell of cells) {
      if (cell.formula !== undefined) workbook.setFormula(cell.sheet, cell.row, cell.column, cell.formula);
      else if (cell.value !== null && cell.value !== undefined && !(cell.value instanceof ExcelError)) {
        workbook.setValue(cell.sheet, cell.row, cell.column, cell.value);
      }
    }
    return targets.map((target) => fromEngine(workbook.evaluateCell(target.sheet, target.row, target.column)));
  } finally {
    workbook.free?.();
  }
}

/** Move a formula's relative references by a number of rows, as copying it down would. */
export function shiftRows(formula: string, delta: number): string {
  return formula.replace(/"(?:[^"]|"")*"|'(?:[^']|'')+'!|(?<![\w.\]$])(\$?[A-Z]{1,3})(\$?)([1-9][0-9]*)(?![\w(.[])/g, (match, column: string | undefined, absolute: string, row: string) => {
    if (column === undefined || absolute === "$") return match;
    return `${column}${Number(row) + delta}`;
  });
}

export { fromSerial, toSerial };
