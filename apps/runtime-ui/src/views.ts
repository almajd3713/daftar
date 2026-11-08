/** A spec's view becomes query parameters here, because the server has no view route. */
import type { Filter, ViewBoard, ViewList } from "@daftar/spec/types";

export const PAGE_SIZE = 50;

export function isListView(view: ViewList | ViewBoard): view is ViewList {
  return view.type === "list";
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
  for (const filter of view.filters ?? []) {
    const value = filterValue(filter, today);
    if (value !== undefined) params.append(`filter.${filter.field}.${filter.op}`, value);
  }
  return `/api/e/${encodeURIComponent(view.entity)}?${params.toString()}`;
}
