import type { CalculatorInput, CalculatorOutput, Entity, Expr, Field, ViewList, Workflow, WorkflowState, WorkflowTransition } from "@daftar/spec/types";
import { describe, expect, it } from "vitest";

import { classify, type AuditChange, type MetaCalculator } from "../src/api.js";
import { canUndo, deletionOf, isRestoration, linksIn, splitChanges } from "../src/history.js";
import { parseRoute, pathOf, type Route } from "../src/router.js";
import { allValues, changedValues, everyValue, fieldOfInput, fitsType, fromDraft, outputError, startingDrafts, toDraft } from "../src/values.js";
import { listPath, usableCalculators } from "../src/views.js";
import { fieldsToCheck, offeredSteps } from "../src/workflow.js";

const label = { fr: "x", ar: "x" };
const field = (key: string, type: string, extra: object = {}): Field => ({ key, label, type, ...extra }) as Field;
const money = field("price", "money", { precision: 2 });
const view = (extra: Partial<ViewList> = {}): ViewList => ({ key: "v", label, entity: "payments", type: "list", columns: ["a"], ...extra });

describe("routes", () => {
  const routes: Route[] = [
    { name: "home" },
    { name: "more" },
    { name: "view", view: "payments_all", q: "", page: 1 },
    { name: "view", view: "payments_all", q: "حورية سعيدي", page: 3 },
    { name: "new", entity: "repairs", from: "repairs_all" },
    { name: "new", entity: "repairs", from: undefined },
    { name: "edit", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: "repairs_all" },
    { name: "record", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: "repairs_all" },
    { name: "record", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: undefined },
    { name: "calculator", calculator: "tuition_fee" },
  ];

  it("read back what they wrote, so a reload lands on the same page", () => {
    for (const route of routes) {
      const url = new URL(pathOf(route), "http://x");
      expect(parseRoute(url.pathname, url.search)).toEqual(route);
    }
  });

  it("treat an address they don't know as missing, not as a crash", () => {
    expect(parseRoute("/nothing/here", "").name).toBe("missing");
    expect(parseRoute("/%E0%A4%A", "").name).toBe("missing");
    expect(parseRoute("/e/repairs", "").name).toBe("missing");
  });

  it("fall back to the first page on a nonsense page number", () => {
    for (const page of ["0", "-1", "1.5", "abc"]) expect(parseRoute("/v/a", `?page=${page}`)).toMatchObject({ page: 1 });
  });
});

describe("a workflow's steps", () => {
  const state = (key: string): WorkflowState => ({ key, label });
  const step = (key: string, from: [string, ...string[]], to: string, extra: Partial<WorkflowTransition> = {}): WorkflowTransition => ({ key, label, from, to, roles: ["owner", "staff"], ...extra });
  const workflow: Workflow = {
    key: "flow",
    label,
    entity: "repairs",
    stateField: "status",
    initialState: "a",
    states: [state("a"), state("b"), state("c")],
    transitions: [step("back", ["b"], "a"), step("on", ["b"], "c"), step("start", ["a"], "b"), step("owner_only", ["a"], "c", { roles: ["owner"] })],
  };
  const keys = (items: WorkflowTransition[]): string[] => items.map((item) => item.key);

  it("are those from this state that this role may take", () => {
    expect(keys(offeredSteps(workflow, "a", "staff"))).toEqual(["start"]);
    expect(keys(offeredSteps(workflow, "c", "owner"))).toEqual([]);
    expect(keys(offeredSteps(workflow, "a", "viewer"))).toEqual([]);
    expect(keys(offeredSteps(workflow, null, "owner"))).toEqual([]);
  });

  it("come furthest along first, whatever order the spec lists them in", () => {
    expect(keys(offeredSteps(workflow, "b", "owner"))).toEqual(["on", "back"]);
    expect(keys(offeredSteps(workflow, "a", "owner"))).toEqual(["owner_only", "start"]);
  });

  const entity = { key: "repairs", label, titleField: "device", fields: [field("price", "money"), field("device", "text"), field("items", "child")] } as unknown as Entity;
  const read = (fieldKey: string): Expr => ({ kind: "field", valueType: "number", field: fieldKey });

  it("point a refusal at the fields a condition reads, however deep", () => {
    const deep: Expr = { kind: "op", valueType: "boolean", op: "gt", args: [{ kind: "call", valueType: "number", fn: "SUM", args: [read("price"), { kind: "rollup", valueType: "number", via: "items", fn: "count" }] }, { kind: "literal", valueType: "number", value: 0 }] };
    expect(fieldsToCheck(entity, step("x", ["a"], "b", { condition: deep })).map((item) => item.key)).toEqual(["price", "items"]);
  });

  it("never name a field this person can't see, or anything for a step with no condition", () => {
    expect(fieldsToCheck(entity, step("x", ["a"], "b", { condition: read("margin") }))).toEqual([]);
    expect(fieldsToCheck(entity, step("x", ["a"], "b"))).toEqual([]);
  });
});

describe("a record's history", () => {
  const change = (id: string, op: string, extra: Partial<AuditChange> = {}): AuditChange => ({ id, at: "2026-11-05T09:42:00Z", actor: "samira", source: "ui", op, changes: {}, ...extra });
  const entity = { key: "students", label, titleField: "name", fields: [field("name", "text"), field("class", "link", { target: "classes" })] } as unknown as Entity;

  it("offers undoing an edit or a step, once", () => {
    expect(canUndo(change("a", "update"))).toBe(true);
    expect(canUndo(change("a", "transition"))).toBe(true);
    expect(canUndo(change("a", "update", { revertedBy: "b" }))).toBe(false);
    for (const op of ["create", "delete", "revert"]) expect(canUndo(change("a", op))).toBe(false);
  });

  it("restores the newest deletion that hasn't been undone", () => {
    const older = change("old", "delete", { revertedBy: "x" });
    expect(deletionOf([change("n", "update"), change("new", "delete"), older])?.id).toBe("new");
    expect(deletionOf([change("x", "revert", { revertOf: "old" }), older])).toBeUndefined();
  });

  it("tells a restoration from an undone edit", () => {
    const changes = [change("r", "revert", { revertOf: "d" }), change("d", "delete"), change("u", "revert", { revertOf: "e" }), change("e", "update")];
    expect(isRestoration(changes[0] as AuditChange, changes)).toBe(true);
    expect(isRestoration(changes[2] as AuditChange, changes)).toBe(false);
    expect(isRestoration(changes[3] as AuditChange, changes)).toBe(false);
  });

  it("only says that a hidden field changed, because it has no label to show", () => {
    const split = splitChanges(entity, change("a", "update", { changes: { name: ["A", "B"], parts_cost: ["*", "*"] } }));
    expect(split.shown).toEqual([{ field: entity.fields[0], from: "A", to: "B" }]);
    expect(split.hidden).toBe(true);
    expect(splitChanges(entity, change("a", "update", { changes: { name: ["A", "B"] } })).hidden).toBe(false);
  });

  it("asks once for each link's name, and only where a line will show it", () => {
    const changes = [
      change("c", "update", { changes: { class: ["id-1", "id-2"], name: ["A", "B"] } }),
      change("b", "update", { changes: { class: [null, "id-1"] } }),
      change("a", "create", { changes: { class: [null, "id-9"] } }),
    ];
    expect(linksIn(entity, changes)).toEqual(["classes/id-1", "classes/id-2"]);
  });
});

describe("a view as query parameters", () => {
  const today = "2026-11-06";
  const paramsOf = (path: string): URLSearchParams => new URL(path, "http://x").searchParams;

  it("sends its sort, with a minus for descending", () => {
    expect(paramsOf(listPath(view({ sort: [{ field: "a", direction: "desc" }, { field: "b", direction: "asc" }] }), { q: "", page: 1, today })).get("sort")).toBe("-a,b");
  });

  it("asks for its totals, and for the page and search it's on", () => {
    const params = paramsOf(listPath(view({ totals: ["a", "b"] }), { q: "benali", page: 2, today }));
    expect(params.get("totals")).toBe("a,b");
    expect(params.get("q")).toBe("benali");
    expect(params.get("page")).toBe("2");
  });

  it("turns each filter into the server's filter syntax", () => {
    const params = paramsOf(listPath(view({ filters: [{ field: "status", op: "ne", value: "paid" }, { field: "kind", op: "in", value: ["a", "b"] }, { field: "note", op: "isEmpty" }] }), { q: "", page: 1, today }));
    expect(params.get("filter.status.ne")).toBe("paid");
    expect(params.get("filter.kind.in")).toBe("a,b");
    expect(params.get("filter.note.isEmpty")).not.toBeNull();
  });

  it("resolves a relative date against today, across a month's end", () => {
    const at = (relativeDays: number, day: string): string | null => paramsOf(listPath(view({ filters: [{ field: "due", op: "lt", relativeDays }] }), { q: "", page: 1, today: day })).get("filter.due.lt");
    expect(at(0, today)).toBe("2026-11-06");
    expect(at(-7, "2026-03-03")).toBe("2026-02-24");
    expect(at(1, "2026-12-31")).toBe("2027-01-01");
  });

  it("leaves out a filter with nothing to compare", () => {
    expect(paramsOf(listPath(view({ filters: [{ field: "a", op: "eq", value: null }] }), { q: "", page: 1, today })).has("filter.a.eq")).toBe(false);
  });
});

describe("what a form holds, and what the server stores", () => {
  it("reads a number in either language's habits, because the server's parser wouldn't", () => {
    for (const text of ["9.800,00", "9 800,00", "9800", "9800,5", "٩٨٠٠"]) expect(typeof fromDraft(money, text)).toBe("number");
    expect(fromDraft(money, "9.800,00")).toBe(9800);
    expect(fromDraft(money, "9\u00a0800,50")).toBe(9800.5);
  });

  it("sends text it can't read as it is, so the error is in the server's words", () => {
    expect(fromDraft(money, "beaucoup")).toBe("beaucoup");
  });

  it("shows a stored number the way this language writes it", () => {
    expect(toDraft(money, 9800, "ar-DZ")).toBe("9.800,00");
    expect(toDraft(money, 9800, "fr-DZ")).toBe("9\u00a0800,00");
  });

  it("round-trips a value through the form unchanged, in both languages", () => {
    const cases: [Field, unknown][] = [
      [money, 1234567.89],
      [field("n", "integer"), 42],
      [field("p", "percent"), 0.075],
      [field("d", "date"), "2026-11-06"],
      [field("t", "text"), "حورية سعيدي"],
      [field("b", "boolean"), true],
      [field("c", "choice", { choices: [{ key: "a", label }] }), "a"],
      [field("m", "multichoice", { choices: [{ key: "a", label }] }), ["a"]],
    ];
    for (const locale of ["fr-DZ", "ar-DZ"] as const) {
      for (const [item, value] of cases) expect(fromDraft(item, toDraft(item, value, locale)), `${item.key} ${locale}`).toEqual(value);
    }
  });

  it("types a percent as the number beside the sign, and stores the ratio", () => {
    const percent = field("p", "percent");
    expect(toDraft(percent, 0.05, "fr-DZ")).toBe("5,00");
    expect(fromDraft(percent, "5")).toBe(0.05);
    expect(fromDraft(percent, "5 %")).toBe(0.05);
  });

  it("treats a blank as no value", () => {
    for (const item of [money, field("t", "text"), field("d", "date")]) expect(fromDraft(item, "  ")).toBeNull();
    expect(fromDraft(field("m", "multichoice", { choices: [{ key: "a", label }] }), [])).toBeNull();
  });

  it("starts a new record from the spec's defaults", () => {
    const status = field("status", "choice", { default: "received", choices: [{ key: "received", label }] });
    const paid = field("paid", "money", { default: 0 });
    expect(startingDrafts([status, paid], undefined, "fr-DZ")).toEqual({ status: "received", paid: "0,00" });
  });

  it("sends a new record without its blanks", () => {
    expect(allValues([money, field("t", "text")], { price: "12", t: "" })).toEqual({ price: 12 });
  });

  it("sends only what changed on an edit, so it can't undo someone else's change", () => {
    const fields = [money, field("name", "text"), field("note", "longtext")];
    const record = { price: 9800, name: "Samir", note: null };
    const drafts = startingDrafts(fields, record, "ar-DZ");
    expect(changedValues(fields, record, drafts)).toEqual({});
    expect(changedValues(fields, record, { ...drafts, name: "Samira" })).toEqual({ name: "Samira" });
    expect(changedValues(fields, record, { ...drafts, price: "" })).toEqual({ price: null });
  });
});

describe("a calculator's inputs and results", () => {
  const port = (key: string, type: CalculatorInput["type"], extra: Partial<CalculatorInput> = {}): CalculatorInput => ({ key, label, type, sheet: "S", cell: "A1", ...extra });
  const choices: NonNullable<CalculatorInput["choices"]> = [{ key: "north", label }];

  it("starts each input from the workbook's value, in the person's habits", () => {
    const ports = [port("rate", "percent", { default: 0.19 }), port("price", "money", { default: 3000 }), port("on", "boolean", { default: true }), port("start", "date", { default: "2026-11-01" }), port("zone", "choice", { default: "north", choices })];
    expect(startingDrafts(ports.map(fieldOfInput), undefined, "fr-DZ")).toEqual({ rate: "19,00", price: "3 000,00", on: true, start: "2026-11-01", zone: "north" });
  });

  it("shows a workbook's number with the decimals it has, because the analyser calls a count a decimal", () => {
    const draftOf = (value: number): unknown => startingDrafts([fieldOfInput(port("n", "decimal", { default: value }))], undefined, "fr-DZ").n;
    expect(draftOf(2)).toBe("2");
    expect(draftOf(2.5)).toBe("2,5");
    expect(draftOf(0.125)).toBe("0,125");
    expect(draftOf(0.1 + 0.2)).toBe("0,300000");
  });

  it("leaves an input with no value blank", () => {
    const fields = [fieldOfInput(port("a", "money")), fieldOfInput(port("b", "money", { default: null }))];
    expect(startingDrafts(fields, undefined, "fr-DZ")).toEqual({ a: "", b: "" });
  });

  it("treats a choice with no list as text, since there's nothing to pick from", () => {
    expect(fieldOfInput(port("a", "choice")).type).toBe("text");
    expect(fieldOfInput(port("a", "choice", { choices })).type).toBe("choice");
  });

  it("sends a cleared input as null, because one left out would take its default", () => {
    const fields = [fieldOfInput(port("a", "integer", { default: 1 })), fieldOfInput(port("b", "integer", { default: 1 }))];
    expect(everyValue(fields, { a: "", b: "2" })).toEqual({ a: null, b: 2 });
  });

  it("sends text it can't read as it is, so the error is in the server's words", () => {
    expect(everyValue([fieldOfInput(port("a", "integer"))], { a: "beaucoup" })).toEqual({ a: "beaucoup" });
  });

  it("knows an Excel error from a value", () => {
    expect(outputError({ error: "#DIV/0!" })).toBe("#DIV/0!");
    for (const value of [0, "", null, undefined, "#DIV/0!", true]) expect(outputError(value)).toBeUndefined();
  });

  it("notices when a formula gives something other than its output's type", () => {
    expect(fitsType("money", 12)).toBe(true);
    expect(fitsType("money", "-")).toBe(false);
    expect(fitsType("percent", "n/a")).toBe(false);
    expect(fitsType("date", "2026-11-01")).toBe(true);
    expect(fitsType("date", "bientôt")).toBe(false);
    expect(fitsType("date", 46357)).toBe(false);
    expect(fitsType("boolean", false)).toBe(true);
    expect(fitsType("boolean", "oui")).toBe(false);
    expect(fitsType("text", 12)).toBe(true);
  });

  it("offers a calculator only to a role that may read something it gives", () => {
    const calculator = (key: string, outputs: CalculatorOutput[]): MetaCalculator => ({ key, label, inputs: [port("a", "integer")], outputs });
    const usable = usableCalculators({ calculators: [calculator("none", []), calculator("some", [{ key: "x", label, type: "money", sheet: "S", cell: "A2" }])] });
    expect(usable.map((item) => item.key)).toEqual(["some"]);
  });
});

describe("what a failure means", () => {
  it("follows the contract's table", () => {
    expect(classify(400, { fields: { a: label } }).kind).toBe("fields");
    expect(classify(400, { error: "bad_query", what: "x" }).kind).toBe("failed");
    expect(classify(401, { reason: label }).kind).toBe("reason");
    expect(classify(401, { error: "unauthorized" }).kind).toBe("signedOut");
    expect(classify(403, { error: "forbidden" }).kind).toBe("refused");
    expect(classify(403, { reason: label }).kind).toBe("reason");
    expect(classify(404, { error: "not_found" }).kind).toBe("missing");
    expect(classify(409, { reason: label }).kind).toBe("reason");
    expect(classify(503, { reason: label }).kind).toBe("reason");
    expect(classify(500, undefined).kind).toBe("failed");
  });
});
