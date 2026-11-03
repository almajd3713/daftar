import { readdirSync, readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { generateTypes } from "../scripts/generate-types.mjs";
import { formatErrors, validateSpec } from "../src/index.js";

type Path = (string | number)[];
interface InvalidCase {
  name: string;
  base: string;
  at: Path;
  set?: unknown;
  remove?: boolean;
  alsoAt?: Path;
  alsoSet?: unknown;
  expect: string[];
}

const fromHere = (path: string) => new URL(path, import.meta.url);
const readJson = (path: string): unknown => JSON.parse(readFileSync(fromHere(path), "utf8"));
const exampleFiles = readdirSync(fromHere("../examples/")).filter((name) => name.endsWith(".spec.json"));
const cases = readJson("../fixtures/invalid-cases.json") as InvalidCase[];

function change(spec: unknown, at: Path, value: unknown, remove = false): void {
  let node = spec as Record<string | number, unknown>;
  for (const part of at.slice(0, -1)) node = node[part] as Record<string | number, unknown>;
  const last = at.at(-1)!;
  if (remove) delete node[last];
  else node[last] = value;
}

describe("example specs", () => {
  it("has one per kind", () => {
    expect(exampleFiles.sort()).toEqual([
      "fee-calculator.spec.json",
      "payments-ledger.spec.json",
      "repair-tracker.spec.json",
      "tutoring-register.spec.json",
    ]);
  });

  it.each(exampleFiles)("%s is valid", (name) => {
    const result = validateSpec(readJson(`../examples/${name}`));
    expect(result.valid ? [] : result.errors).toEqual([]);
  });
});

describe("invalid specs", () => {
  it.each(cases)("$name", (testCase) => {
    const spec = readJson(`../examples/${testCase.base}.spec.json`);
    change(spec, testCase.at, testCase.set, testCase.remove);
    if (testCase.alsoAt) change(spec, testCase.alsoAt, testCase.alsoSet);
    const result = validateSpec(spec);
    expect(result.valid).toBe(false);
    if (!result.valid) {
      expect([...new Set(result.errors.map((error) => error.path))].sort()).toEqual(testCase.expect);
    }
  });

  it("formats errors as path: message", () => {
    const spec = readJson("../examples/fee-calculator.spec.json") as { app: { currency: string } };
    spec.app.currency = "EUR";
    const result = validateSpec(spec);
    if (result.valid) throw new Error("expected an invalid spec");
    expect(formatErrors(result.errors)).toMatch(/^app\.currency: /);
  });
});

describe("generated types", () => {
  it("are up to date with the schema; run `pnpm generate` if this fails", async () => {
    const onDisk = readFileSync(fromHere("../src/generated/spec.ts"), "utf8");
    expect(await generateTypes()).toEqual(onDisk);
  });
});
