/** A spec's view becomes query parameters here, because the server has no view route. */
import type { Filter, ViewBoard, ViewList, Workflow } from "@daftar/spec/types";

import type { Meta, MetaCalculator } from "./api.js";
import { isEndState } from "./workflow.js";

export const PAGE_SIZE = 50;

export function isListView(view: ViewList | ViewBoard): view is ViewList {
  return view.type === "list";
}

/** A board's workflow. It can't be drawn for a role that can't see the field its columns come from. */
export function boardWorkflow(meta: Pick<Meta, "workflows" | "entities">, view: ViewBoard): Workflow | undefined {
  const workflow = meta.workflows.find((item) => item.key === view.workflow);
  const entity = meta.entities.find((item) => item.key === view.entity);
  return workflow && entity?.fields.some((field) => field.key === workflow.stateField) ? workflow : undefined;
}

/** An entity's views this role can use, in the spec's order: the first is its page. */
export function viewsOf(meta: Pick<Meta, "views" | "workflows" | "entities">, entity: string): (ViewList | ViewBoard)[] {
  return meta.views.filter((view) => view.entity === entity && (isListView(view) || boardWorkflow(meta, view) !== undefined));
}

/** A role that may read none of a calculator's outputs has nothing to get from it. */
export function usableCalculators(meta: Pick<Meta, "calculators">): MetaCalculator[] {
  return meta.calculators.filter((calculator) => calculator.outputs.length);
}

function addDays(date: string, days: number): string {
  const moment = new Date(`${date}T00:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + days);
  return moment.toISOString().slice(0, 10);
}

function filterValue(filter: Filter, today: string): string | undefined {
  // The server's filter parameter needs a value, even where the operator ignores it.
  if (filter.op === "isEmpty" || filter.op === "isNotEmpty") return "1";
  if (filter.relativeDays !== undefined) return addDays(today, filter.relativeDays);
  if (Array.isArray(filter.value)) return filter.value.join(",");
  if (filter.value === null || filter.value === undefined) return undefined;
  return String(filter.value);
}

export interface ListOptions {
  q: string;
  page: number;
  /** In the app's time zone, for filters written relative to it. */
  today: string;
}

export function listPath(view: ViewList, { q, page, today }: ListOptions): string {
  const params = new URLSearchParams({ page: String(page), pageSize: String(PAGE_SIZE) });
  if (q) params.set("q", q);
  const sort = (view.sort ?? []).map((item) => (item.direction === "desc" ? `-${item.field}` : item.field)).join(",");
  if (sort) params.set("sort", sort);
  if (view.totals?.length) params.set("totals", view.totals.join(","));
  addFilters(params, view.filters, today);
  return `/api/e/${encodeURIComponent(view.entity)}?${params.toString()}`;
}

function addFilters(params: URLSearchParams, filters: readonly Filter[] | undefined, today: string): void {
  for (const filter of filters ?? []) {
    const value = filterValue(filter, today);
    if (value !== undefined) params.append(`filter.${filter.field}.${filter.op}`, value);
  }
}

/**
 * One column of a board: a state's own query, so its count is right however many it holds. A working state shows its
 * oldest first, which is the queue to work through. An end state only grows, so past a page its oldest would hide the
 * job someone just finished, and it shows what changed last.
 */
export function boardPath(view: ViewBoard, workflow: Workflow, state: string, today: string): string {
  const params = new URLSearchParams({ page: "1", pageSize: String(PAGE_SIZE) });
  if (isEndState(workflow, state)) params.set("sort", "-_updatedAt");
  addFilters(params, view.filters, today);
  params.append(`filter.${workflow.stateField}.eq`, state);
  return `/api/e/${encodeURIComponent(view.entity)}?${params.toString()}`;
}
