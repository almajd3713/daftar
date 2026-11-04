import { describe, expect, it } from "vitest";

import type { DaftarSpec } from "@daftar/spec/types";

import { checkReferences } from "../src/spec/checks.js";
import { SpecLoadError, parseSpec } from "../src/spec/loader.js";
import { example } from "./helpers.js";

const EXAMPLES = ["tutoring-register", "payments-ledger", "fee-calculator", "repair-tracker"];

function broken(name: string, change: (spec: any) => void): string[] {
  const spec = structuredClone(example(name)) as any;
  change(spec);
  return checkReferences(spec as DaftarSpec);
}

describe("spec checks", () => {
  it.each(EXAMPLES)("%s has no broken references", (name) => {
    expect(checkReferences(example(name))).toEqual([]);
  });

  it.each([
    ["a view of a missing entity", "tutoring-register", (s: any) => { s.views[0].entity = "ghost"; }, "isn't an entity"],
    ["a view column that isn't a field", "tutoring-register", (s: any) => { s.views[0].columns.push("ghost"); }, "ghost isn't a field"],
    ["two fields with one key", "tutoring-register", (s: any) => { s.entities[0].fields.push(s.entities[0].fields[0]); }, "duplicate key"],
    ["a link to nowhere", "tutoring-register", (s: any) => { s.entities[1].fields[5].target = "ghost"; }, "isn't an entity"],
    ["a title field that isn't a field", "tutoring-register", (s: any) => { s.entities[0].titleField = "ghost"; }, "titleField"],
    ["a child with no link back", "tutoring-register", (s: any) => { s.entities[0].fields[3].via = "full_name"; }, "isn't a link back"],
    ["a formula reading a missing field", "payments-ledger", (s: any) => { s.entities[0].fields[7].computed.expr.args[0].field = "ghost"; }, "reads ghost"],
    ["a workflow state that isn't a choice", "repair-tracker", (s: any) => { s.workflows[0].states.push({ key: "ghost", label: { fr: "x", ar: "س" } }); }, "isn't a choice"],
    ["a transition to a missing state", "repair-tracker", (s: any) => { s.workflows[0].transitions[0].to = "ghost"; }, "ghost isn't a state"],
    ["a key column outside the columns", "repair-tracker", (s: any) => { s.mapping[0].keyColumns = ["margin_x"]; }, "isn't in its columns"],
    ["a calculator port with no cell", "fee-calculator", (s: any) => { s.calculators[0].inputs[0].cell = "Z9"; }, "doesn't have"],
    ["a board on another entity's workflow", "repair-tracker", (s: any) => { s.views[0].workflow = "ghost"; }, "workflow ghost"],
  ])("refuses %s", (_, name, change, expected) => {
    expect(broken(name, change).join("\n")).toContain(expected);
  });

  it("refuses to load an invalid spec, with the path to the error", () => {
    const spec = structuredClone(example("fee-calculator")) as any;
    spec.app.currency = "EUR";
    expect(() => parseSpec(spec)).toThrow(SpecLoadError);
    expect(() => parseSpec(spec)).toThrow(/app\.currency/);
  });
});
