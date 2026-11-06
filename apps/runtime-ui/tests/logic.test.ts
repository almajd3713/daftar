import type { Field, ViewList } from "@daftar/spec/types";
import { describe, expect, it } from "vitest";

import { classify } from "../src/api.js";
import { parseRoute, pathOf, type Route } from "../src/router.js";
import { allValues, changedValues, fromDraft, startingDrafts, toDraft } from "../src/values.js";
import { listPath } from "../src/views.js";

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
