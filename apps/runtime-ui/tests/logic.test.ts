import type { CalculatorInput, CalculatorOutput, Entity, Expr, Field, ViewBoard, ViewList, Widget, WidgetChart, WidgetKpi, Workflow, WorkflowState, WorkflowTransition } from "@daftar/spec/types";
import { describe, expect, it } from "vitest";

import { classify, type AggregateGroup, type AuditChange, type ListResult, type MetaCalculator, type Row } from "../src/api.js";
import { barsInOrder, chartPrecision, heroText, kpiType, kpiValue, linePoints, widgetPath } from "../src/widgets.js";
import { canUndo, deletionOf, isRestoration, linksIn, splitChanges } from "../src/history.js";
import { parseRoute, pathOf, type Route } from "../src/router.js";
import { allValues, changedValues, everyValue, fieldOfInput, fitsType, fromDraft, outputError, startingDrafts, toDraft } from "../src/values.js";
import { boardPath, listPath, PAGE_SIZE, usableCalculators, viewsOf } from "../src/views.js";
import { fieldsToCheck, offeredSteps, stepBetween } from "../src/workflow.js";

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
    { name: "view", view: "repairs_board", q: "", page: 1, state: "in_repair" },
    { name: "new", entity: "repairs", from: "repairs_all" },
    { name: "new", entity: "repairs", from: undefined },
    { name: "edit", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: "repairs_all" },
    { name: "record", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: "repairs_all" },
    { name: "record", entity: "repairs", id: "0b0c2c5e-1111-4222-8333-444455556666", from: undefined },
    { name: "calculator", calculator: "tuition_fee" },
    { name: "dashboard", dashboard: "cash" },
    { name: "deleted", entity: "repairs", page: 1 },
    { name: "deleted", entity: "repairs", page: 3 },
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

  it("find what moving a card attempts, preferring a step this role may take", () => {
    expect(stepBetween(workflow, "a", "b", "staff")?.key).toBe("start");
    expect(stepBetween(workflow, "a", "c", "owner")?.key).toBe("owner_only");
    expect(stepBetween(workflow, "a", "a", "owner")).toBeUndefined();
    const both: Workflow = { ...workflow, transitions: [step("owners", ["a"], "b", { roles: ["owner"] }), step("everyone", ["a"], "b")] };
    expect(stepBetween(both, "a", "b", "staff")?.key).toBe("everyone");
  });

  it("still find a step this role may not take, so the server can say why not", () => {
    expect(stepBetween(workflow, "a", "c", "staff")?.key).toBe("owner_only");
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
  const flow: Workflow = { key: "flow", label, entity: "payments", stateField: "status", initialState: "a", states: [{ key: "a", label }], transitions: [] };
  const board: ViewBoard = { key: "b", label, entity: "payments", type: "board", workflow: "flow", cardFields: ["x"] };

  it("asks for one state of a board, with the view's own filters, a page's worth at a time", () => {
    const params = paramsOf(boardPath({ ...board, filters: [{ field: "kind", op: "ne", value: "z" }] }, flow, "a", today));
    expect(params.get("filter.status.eq")).toBe("a");
    expect(params.get("filter.kind.ne")).toBe("z");
    expect(params.get("pageSize")).toBe(String(PAGE_SIZE));
  });

  it("shows a working state's oldest first, and what changed last in a state no step leaves", () => {
    const step: WorkflowTransition = { key: "go", label, from: ["a"], to: "z", roles: ["owner"] };
    const moving: Workflow = { ...flow, states: [{ key: "a", label }, { key: "z", label }], transitions: [step] };
    expect(paramsOf(boardPath(board, moving, "a", today)).has("sort")).toBe(false);
    expect(paramsOf(boardPath(board, moving, "z", today)).get("sort")).toBe("-_updatedAt");
  });

  it("leaves out a board a role can't draw, and keeps an entity's views in the spec's order", () => {
    const entity = (fields: Field[]): Entity => ({ key: "payments", label, fields }) as Entity;
    const list = view({ key: "l" });
    const meta = (fields: Field[], workflows: Workflow[] = [flow]): Parameters<typeof viewsOf>[0] => ({ views: [board, list], workflows, entities: [entity(fields)] });
    expect(viewsOf(meta([field("status", "choice")]), "payments").map((item) => item.key)).toEqual(["b", "l"]);
    expect(viewsOf(meta([field("other", "text")]), "payments").map((item) => item.key)).toEqual(["l"]);
    expect(viewsOf(meta([field("status", "choice")], []), "payments").map((item) => item.key)).toEqual(["l"]);
    expect(viewsOf(meta([field("status", "choice")]), "elsewhere")).toEqual([]);
  });

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

describe("a dashboard's widgets", () => {
  const today = "2026-11-07";
  const paramsOf = (widget: Widget): URLSearchParams => new URL(widgetPath(widget, today), "http://x").searchParams;
  const kpi = (aggregate: WidgetKpi["aggregate"], extra: Partial<WidgetKpi> = {}): WidgetKpi => ({ key: "k", label, type: "kpi", entity: "sales", aggregate, field: "amount", ...extra });
  const result = (extra: Partial<ListResult>): ListResult => ({ rows: [], total: 0, page: 1, pageSize: 1, totals: {}, ...extra });
  const row = (extra: object): Row => ({ _id: "x", _name: "x", _version: 1, ...extra });

  it("asks the list for a figure, keeping blanks out of what they'd distort", () => {
    expect(widgetPath({ key: "k", label, type: "kpi", entity: "sales", aggregate: "count" }, today)).toBe("/api/e/sales?pageSize=1");
    expect(paramsOf(kpi("sum")).get("totals")).toBe("amount");
    expect(paramsOf(kpi("sum")).has("filter.amount.isNotEmpty")).toBe(false);
    expect(paramsOf(kpi("avg")).get("totals")).toBe("amount");
    expect(paramsOf(kpi("avg")).has("filter.amount.isNotEmpty")).toBe(true);
    expect(paramsOf(kpi("min")).get("sort")).toBe("amount");
    expect(paramsOf(kpi("max")).get("sort")).toBe("-amount");
    expect(paramsOf(kpi("max")).has("filter.amount.isNotEmpty")).toBe(true);
  });

  it("keeps a widget's own filters, with dates relative to today", () => {
    const params = paramsOf(kpi("count", { filters: [{ field: "status", op: "ne", value: "paid" }, { field: "due", op: "lt", relativeDays: 0 }] }));
    expect(params.get("filter.status.ne")).toBe("paid");
    expect(params.get("filter.due.lt")).toBe(today);
  });

  it("asks a line for its newest points, and a bar for its groups", () => {
    const chart = (type: "bar" | "line"): WidgetChart => ({ key: "c", label, type, entity: "sales", aggregate: "count", groupBy: "day" });
    expect(widgetPath(chart("line"), today)).toContain("/api/e/sales/aggregate?");
    expect(paramsOf(chart("line")).get("order")).toBe("desc");
    expect(paramsOf(chart("bar")).has("order")).toBe(false);
    expect(paramsOf(chart("bar")).get("groupBy")).toBe("day");
  });

  it("reads each figure from what the list answers", () => {
    expect(kpiValue(kpi("count"), result({ total: 7 }))).toBe(7);
    expect(kpiValue(kpi("sum"), result({ total: 2, totals: { amount: 900 } }))).toBe(900);
    expect(kpiValue(kpi("avg"), result({ total: 3, totals: { amount: 900 } }))).toBe(300);
    expect(kpiValue(kpi("min"), result({ total: 3, rows: [row({ amount: 100 })] }))).toBe(100);
  });

  it("tells nothing to add up from a total of nothing", () => {
    expect(kpiValue(kpi("sum"), result({ total: 0, totals: { amount: null } }))).toBe(0);
    expect(kpiValue(kpi("sum"), result({ total: 2, totals: { amount: null } }))).toBeNull();
    expect(kpiValue(kpi("avg"), result({ total: 0, totals: { amount: null } }))).toBeNull();
    expect(kpiValue(kpi("max"), result({ total: 0 }))).toBeNull();
  });

  it("knows a figure's kind: a count is whole, and an average rarely is", () => {
    expect(kpiType(kpi("count"), field("amount", "money"))).toBe("integer");
    expect(kpiType(kpi("sum"), field("amount", "money"))).toBe("money");
    expect(kpiType(kpi("sum"), field("qty", "integer"))).toBe("integer");
    expect(kpiType(kpi("avg"), field("qty", "integer"))).toBe("decimal");
    expect(kpiType(kpi("max"), field("rate", "percent"))).toBe("percent");
    expect(kpiType(kpi("min"), field("day", "date"))).toBe("date");
  });

  it("orders a choice's bars by the spec, anything else largest first, and blanks last", () => {
    const choices = [{ key: "west", label }, { key: "east", label }];
    const groups: AggregateGroup[] = [{ key: null, value: 9 }, { key: "east", value: 5 }, { key: "west", value: 1 }, { key: "gone", value: null }];
    expect(barsInOrder(groups, field("zone", "choice", { choices })).map((group) => group.key)).toEqual(["west", "east", null]);
    expect(barsInOrder(groups, field("name", "text")).map((group) => group.key)).toEqual(["east", "west", null]);
  });

  const say = (item: { fr: string }): string => item.fr;
  const dated = (...keys: string[]): AggregateGroup[] => keys.map((key, index) => ({ key, value: index + 1 }));

  it("puts a line back in time order, placed in time, with nothing for rows that have no date", () => {
    const points = linePoints([{ key: "2026-11-09", value: 2 }, { key: "2026-11-02", value: 1 }, { key: null, value: 8 }], field("day", "date"), say, "fr-DZ");
    expect(points.map((point) => point.label)).toEqual(["02/11", "09/11"]);
    expect(points[1]?.at).toBe(Date.parse("2026-11-09"));
  });

  it("names months when every point is a month's first, and the year once they span two", () => {
    expect(linePoints(dated("2026-02-01", "2026-01-01"), field("m", "date"), say, "fr-DZ").map((point) => point.label)).toEqual(["janv.", "févr."]);
    expect(linePoints(dated("2027-01-01", "2026-12-01"), field("m", "date"), say, "fr-DZ").map((point) => point.label)).toEqual(["déc. 26", "janv. 27"]);
    expect(linePoints(dated("2027-01-05", "2026-12-20"), field("d", "date"), say, "fr-DZ").map((point) => point.label)).toEqual(["20/12/26", "05/01/27"]);
  });

  it("keeps a broken line's gap, and labels what isn't a date as itself", () => {
    expect(linePoints([{ key: "2026-11-02", value: null }], field("day", "date"), say, "fr-DZ")[0]?.value).toBeNull();
    const choices = [{ key: "west", label: { fr: "Ouest", ar: "x" } }];
    expect(linePoints([{ key: "west", value: 1 }], field("zone", "choice", { choices }), say, "fr-DZ")[0]).toEqual({ key: "west", label: "Ouest", value: 1 });
  });

  it("gives a chart's numbers the decimals they need", () => {
    expect(chartPrecision("count", false, [1, 2])).toBe(0);
    expect(chartPrecision("sum", true, [1, 2])).toBe(2);
    expect(chartPrecision("sum", false, [1, null])).toBe(0);
    expect(chartPrecision("avg", false, [1.5])).toBe(2);
  });

  it("writes the lead figure, with a dash for nothing rather than a zero", () => {
    expect(heroText("integer", 1200, "fr-DZ", 0)).toBe("1\u00a0200");
    expect(heroText("money", 1200, "fr-DZ", 2)).toBe("1\u00a0200,00");
    expect(heroText("percent", 0.125, "fr-DZ", 2)).toBe("12,50");
    expect(heroText("percent", 0.5, "fr-DZ", 2)).toBe("50");
    expect(heroText("decimal", 2, "fr-DZ", 2)).toBe("2");
    expect(heroText("date", "2026-11-07", "fr-DZ", 0)).toBe("07/11/2026");
    expect(heroText("money", null, "fr-DZ", 2)).toBe("–");
  });
});

describe("a calculator's inputs and results", () => {
  const port = (key: string, type: CalculatorInput["type"], extra: Partial<CalculatorInput> = {}): CalculatorInput => ({ key, label, type, sheet: "S", cell: "A1", ...extra });
  const choices: NonNullable<CalculatorInput["choices"]> = [{ key: "north", label }];

  it("starts each input from the workbook's value, in the person's habits", () => {
    const ports = [port("rate", "percent", { default: 0.19 }), port("price", "money", { default: 3000 }), port("on", "boolean", { default: true }), port("start", "date", { default: "2026-11-01" }), port("zone", "choice", { default: "north", choices })];
    expect(startingDrafts(ports.map(fieldOfInput), undefined, "fr-DZ")).toEqual({ rate: "19,00", price: "3\u00a0000,00", on: true, start: "2026-11-01", zone: "north" });
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
