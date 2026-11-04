/** The same cases the Python evaluator passes, so the two can't drift apart. */
import { readFileSync } from "node:fs";

import { beforeAll, describe, expect, it } from "vitest";

import type { Expr } from "@daftar/spec/types";

import { evaluateCells, loadEngine, shiftRows } from "../src/expr/engine.js";
import { evaluate, ExcelError, fromSerial, TRANSLATABLE, toSerial, type Scalar } from "../src/expr/evaluate.js";

interface Case {
  formula: string;
  expr: Expr;
  value?: Scalar;
  error?: string;
}
const fixture = JSON.parse(readFileSync(new URL("../../../packages/spec/fixtures/expression-cases.json", import.meta.url), "utf8")) as {
  record: Record<string, Scalar>;
  now: string;
  cases: Case[];
};
const RECORD_COLUMNS = ["col_a", "col_b", "col_c", "col_d", "col_e", "col_f", "col_g"];

function same(actual: Scalar, expected: Case): void {
  if (expected.error !== undefined) {
    expect(actual).toBeInstanceOf(ExcelError);
    expect((actual as ExcelError).code).toBe(expected.error);
  } else if (typeof expected.value === "number") {
    expect(typeof actual).toBe("number");
    expect(actual as number).toBeCloseTo(expected.value, 9);
  } else {
    expect(actual).toBe(expected.value);
  }
}

describe("the TypeScript evaluator", () => {
  it.each(fixture.cases)("$formula", (item) => {
    same(evaluate(item.expr, { record: fixture.record, now: new Date(fixture.now) }), item);
  });

  it("covers the same functions as the Python one", () => {
    const used = new Set<string>();
    const visit = (expr: Expr): void => {
      if (expr.kind === "call") used.add(expr.fn);
      if (expr.kind === "call" || expr.kind === "op") expr.args.forEach(visit);
    };
    fixture.cases.forEach((item) => visit(item.expr));
    expect([...TRANSLATABLE].filter((name) => !used.has(name)).sort()).toEqual([]);
  });

  it("handles the 1900 leap-year bug", () => {
    expect(toSerial(new Date(Date.UTC(2026, 0, 15)))).toBe(46037);
    expect(toSerial(new Date(Date.UTC(1900, 1, 28)))).toBe(59);
    expect(toSerial(new Date(Date.UTC(1900, 2, 1)))).toBe(61);
    expect(fromSerial(46037).toISOString()).toBe("2026-01-15T00:00:00.000Z");
    expect(fromSerial(59).toISOString()).toBe("1900-02-28T00:00:00.000Z");
  });
});

describe("the Node engine binding", () => {
  beforeAll(loadEngine);
  const clockFree = fixture.cases.filter((item) => !/TODAY|NOW/.test(item.formula));

  it.each(clockFree)("$formula agrees with the evaluator", (item) => {
    const cells = RECORD_COLUMNS.map((key, index) => ({ sheet: "S", row: 2, column: index + 1, value: fixture.record[key] ?? null }));
    const [result] = evaluateCells([...cells, { sheet: "S", row: 2, column: 9, formula: item.formula }], [{ sheet: "S", row: 2, column: 9 }]);
    same(result ?? null, item);
  });

  it.each([
    ["=C2-D2", 3, "=C5-D5"],
    ["=C2*$F$1", 1, "=C3*$F$1"],
    ["=SUM(B$2:B2)", 2, "=SUM(B$2:B4)"],
    ['="C2"&C2', 1, '="C2"&C3'],
    ["=Prix!A2+'Mes prix'!B2", 1, "=Prix!A3+'Mes prix'!B3"],
    ["=ROUND(A2,2)", 1, "=ROUND(A3,2)"],
  ])("copies %s down %i rows", (formula, delta, expected) => {
    expect(shiftRows(formula, delta)).toBe(expected);
  });
});
