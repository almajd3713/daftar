/**
 * What a dashboard's widgets ask the server, and how to read what it answers. The server has no route for a widget, so
 * a figure comes from the list and a chart from `/aggregate`, and either is limited to this person's rows by the server.
 */
import type { Field, Widget, WidgetKpi } from "@daftar/spec/types";
import { formatDate, formatNumber, monthName, type Locale } from "@daftar/ui/format";

import type { AggregateGroup, ListResult } from "./api.js";
import { kindOf, textOf } from "./values.js";
import { addFilters } from "./views.js";

/** A chart with more bars than this stops being one anyone can read. */
export const MOST_BARS = 20;

export function widgetPath(widget: Widget, today: string): string {
  const entity = encodeURIComponent(widget.entity);
  const field = widget.field;
  const params = new URLSearchParams();
  if (widget.type === "kpi") {
    params.set("pageSize", "1");
    if (field && widget.aggregate !== "count") {
      // A blank isn't a zero: it mustn't lower an average, or be the smallest value there is.
      if (widget.aggregate !== "sum") params.set(`filter.${field}.isNotEmpty`, "1");
      if (widget.aggregate === "sum" || widget.aggregate === "avg") params.set("totals", field);
      if (widget.aggregate === "min") params.set("sort", field);
      if (widget.aggregate === "max") params.set("sort", `-${field}`);
    }
    addFilters(params, widget.filters, today);
    return `/api/e/${entity}?${params.toString()}`;
  }
  params.set("groupBy", widget.groupBy);
  params.set("aggregate", widget.aggregate);
  if (field) params.set("field", field);
  // Past the server's limit a line keeps its newest points, and these get put back in order to draw.
  if (widget.type === "line") params.set("order", "desc");
  addFilters(params, widget.filters, today);
  return `/api/e/${entity}/aggregate?${params.toString()}`;
}

/** A figure from its list answer. Null means there's nothing to work it out from, which isn't the same as zero. */
export function kpiValue(widget: WidgetKpi, result: ListResult): unknown {
  const field = widget.field;
  if (widget.aggregate === "count" || !field) return result.total;
  const total = result.totals[field] ?? null;
  if (widget.aggregate === "sum") return total ?? (result.total === 0 ? 0 : null);
  if (widget.aggregate === "avg") return total === null || result.total === 0 ? null : total / result.total;
  return result.rows[0]?.[field] ?? null;
}

export type KpiType = "integer" | "decimal" | "money" | "percent" | "date";

/** What kind of value a figure is. A count is a whole number, whatever it counts, and an average rarely is. */
export function kpiType(widget: Pick<WidgetKpi, "aggregate">, field: Field | undefined): KpiType {
  if (widget.aggregate === "count" || !field) return "integer";
  const kind = kindOf(field);
  if (kind === "money" || kind === "percent" || kind === "date") return kind;
  return kind === "integer" && widget.aggregate !== "avg" ? "integer" : "decimal";
}

/** Bars in the order a person knows them by, where a spec gives one, and otherwise largest first. Blanks go last. */
export function barsInOrder(groups: readonly AggregateGroup[], field: Field | undefined): AggregateGroup[] {
  const known = groups.filter((group) => group.value !== null);
  const blank = known.filter((group) => group.key === null);
  const rest = known.filter((group) => group.key !== null);
  if (field && "choices" in field) {
    const place = (group: AggregateGroup): number => {
      const index = field.choices.findIndex((choice) => choice.key === group.key);
      return index < 0 ? field.choices.length : index;
    };
    return [...rest.sort((a, b) => place(a) - place(b)), ...blank];
  }
  return [...rest.sort((a, b) => (b.value ?? 0) - (a.value ?? 0)), ...blank];
}

export interface PlottedPoint {
  key: string;
  label: string;
  value: number | null;
  at?: number;
}

const DAY = /^\d{4}-\d{2}-\d{2}$/;

function dateLabels(dates: readonly string[], locale: Locale): (date: string) => string {
  const years = new Set(dates.map((date) => date.slice(0, 4)));
  const monthly = dates.length > 1 && dates.every((date) => date.endsWith("-01"));
  return (date) => {
    const short = date.slice(2, 4);
    if (monthly) return `${monthName(Number(date.slice(5, 7)), locale)}${years.size > 1 ? ` ${short}` : ""}`;
    return `${date.slice(8)}/${date.slice(5, 7)}${years.size > 1 ? `/${short}` : ""}`;
  };
}

/**
 * A line in the order it's read, oldest first. Rows with no value in the field they're grouped by have no place on it,
 * and a date keeps its place in time, so a gap in the data shows as one.
 */
export function linePoints(groups: readonly AggregateGroup[], field: Field | undefined, say: (label: { fr: string; ar: string }) => string, locale: Locale): PlottedPoint[] {
  const placed = groups.filter((group) => group.key !== null).reverse();
  const dates = placed.map((group) => String(group.key));
  const isDates = dates.length > 0 && dates.every((date) => DAY.test(date));
  const label = isDates ? dateLabels(dates, locale) : undefined;
  return placed.map((group) => {
    const key = String(group.key);
    if (label) return { key, label: label(key), value: group.value, at: Date.parse(key) };
    const choice = field && "choices" in field ? field.choices.find((item) => item.key === group.key) : undefined;
    const number = typeof group.key === "number" ? formatNumber(group.key, locale, 0) : undefined;
    return { key, label: choice ? say(choice.label) : (number ?? textOf(group.key)), value: group.value };
  });
}

/** A chart's numbers have as many decimals as a person needs: none for a count, and none for what's whole anyway. */
export function chartPrecision(aggregate: Widget["aggregate"], money: boolean, values: readonly (number | null)[]): number {
  if (aggregate === "count") return 0;
  if (money) return 2;
  return values.every((value) => value === null || Number.isInteger(value)) ? 0 : 2;
}

/** The figure a dashboard leads with, as text. A hero sets it in type no component can format for it. */
export function heroText(type: KpiType, value: unknown, locale: Locale, precision: number): string {
  if (type === "date") return typeof value === "string" ? formatDate(value, locale) : "–";
  if (typeof value !== "number") return "–";
  if (type === "percent") return formatNumber(value * 100, locale, Number.isInteger(value * 100) ? 0 : 2);
  if (type === "integer") return formatNumber(value, locale, 0);
  if (type === "decimal") return formatNumber(value, locale, Number.isInteger(value) ? 0 : 2);
  return formatNumber(value, locale, precision);
}
