import { describe, expect, it } from "vitest";

import {
  formatCompact,
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPhone,
  monthName,
  parseAmount,
  parseDateInput,
  plural,
  todayIn,
  westernDigits,
} from "../src/format.js";
import { chartScale, labelledPoints, labelWidth, lineRuns, pointPositions } from "../src/chart-scale.js";

describe("R-21's formats", () => {
  it("groups an Algerian phone number, in every form the server accepts, and leaves anything else alone", () => {
    expect(formatPhone("0550123456")).toBe("0550 12 34 56");
    expect(formatPhone("021123456")).toBe("021 12 34 56");
    expect(formatPhone("+213550123456")).toBe("+213 550 12 34 56");
    expect(formatPhone("00213550123456")).toBe("00213 550 12 34 56");
    expect(formatPhone("+33612345678")).toBe("+33612345678");
    expect(formatPhone("appeler Rafik")).toBe("appeler Rafik");
  });

  it("writes DZD the way the blueprint spells it", () => {
    expect(formatMoney(1234567.89, "fr-DZ")).toBe("1\u00a0234\u00a0567,89\u00a0DA");
    expect(formatMoney(1234567.89, "ar-DZ")).toBe("\u200f1.234.567,89\u00a0د.ج.\u200f");
  });

  it("uses Western digits in both languages", () => {
    expect(formatNumber(1234.5, "ar-DZ")).toBe("1.234,50");
    expect(formatDate("2026-01-17", "ar-DZ")).toMatch(/^[0-9/\u200f]+$/);
  });

  it("names months the Algerian way", () => {
    expect(monthName(1, "ar-DZ", "long")).toBe("جانفي");
    expect(monthName(8, "ar-DZ", "long")).toBe("أوت");
    expect(monthName(1, "fr-DZ", "long")).toBe("janvier");
  });

  it("agrees with Node's Intl, apart from the narrow space", () => {
    for (const value of [0, 0.5, 12, 999, 1000, 1234.5, 100750, 1234567.89, 123456789]) {
      for (const locale of ["fr-DZ", "ar-DZ"] as const) {
        const expected = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value).replace(/\u202f/g, "\u00a0");
        expect(formatNumber(value, locale)).toBe(expected);
      }
    }
    for (const locale of ["fr-DZ", "ar-DZ"] as const) {
      const expected = new Intl.NumberFormat(locale, { style: "currency", currency: "DZD" }).format(1234567.89).replace(/\u202f/g, "\u00a0");
      expect(formatMoney(1234567.89, locale)).toBe(expected);
      const date = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Africa/Algiers" }).format(new Date("2026-01-17T12:00:00Z"));
      expect(formatDate("2026-01-17", locale)).toBe(date);
      for (let month = 1; month <= 12; month += 1) {
        const name = new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" }).format(new Date(Date.UTC(2026, month - 1, 15)));
        expect(monthName(month, locale, "long")).toBe(name);
      }
    }
  });

  it("never lets U+202F through, which no webfont here has", () => {
    expect(formatMoney(1234567, "fr-DZ")).not.toContain("\u202f");
    expect(formatCompact(150000, "fr-DZ")).not.toContain("\u202f");
  });

  it("doesn't call a rounded zero negative", () => {
    expect(formatNumber(-0.001, "fr-DZ")).toBe("0,00");
    expect(formatNumber(-5, "fr-DZ")).toBe("\u22125,00");
  });

  it("rounds on the decimal digits", () => {
    expect(formatNumber(1.005, "fr-DZ")).toBe("1,01");
  });

  it("writes percentages by each language's rule", () => {
    expect(formatPercent(0.05, "fr-DZ")).toBe("5\u00a0%");
    expect(formatPercent(0.05, "ar-DZ")).toBe("5%");
    expect(formatPercent(0.125, "ar-DZ")).toBe("12,5%");
    expect(formatPercent(1, "fr-DZ")).toBe("100\u00a0%");
  });

  it("shortens chart axis numbers", () => {
    expect(formatCompact(150000, "fr-DZ")).toBe("150\u00a0k");
    expect(formatCompact(150000, "ar-DZ")).toBe("150\u00a0ألف");
    expect(formatCompact(2000000, "ar-DZ")).toBe("2\u00a0مليون");
    expect(formatCompact(0, "fr-DZ")).toBe("0");
  });

  it("shows instants in Algiers, whatever the device's zone", () => {
    expect(formatDateTime("2026-11-05T09:42:00Z", "fr-DZ")).toEqual({ date: "05/11/2026", time: "10:42" });
    expect(formatDateTime("2026-12-31T23:30:00Z", "fr-DZ")).toEqual({ date: "01/01/2027", time: "00:30" });
    expect(todayIn("Africa/Algiers", new Date("2026-12-31T23:30:00Z"))).toBe("2027-01-01");
  });
});

describe("reading what people type", () => {
  it("reads amounts in either language's habits", () => {
    expect(parseAmount("1 234,50")).toBe(1234.5);
    expect(parseAmount("1\u00a0234,50")).toBe(1234.5);
    expect(parseAmount("1.234,50")).toBe(1234.5);
    expect(parseAmount("1,234.50")).toBe(1234.5);
    expect(parseAmount("9.800")).toBe(9800);
    expect(parseAmount("9.5")).toBe(9.5);
    expect(parseAmount("٣٤٥")).toBe(345);
    expect(parseAmount("1 200 DA")).toBe(1200);
    expect(parseAmount("1.200 د.ج.")).toBe(1200);
    expect(parseAmount("\u22125")).toBe(-5);
    expect(parseAmount("-5,5")).toBe(-5.5);
  });

  it("refuses what isn't a number", () => {
    for (const text of ["", "  ", "abc", "12a", "1,2,3", "--5"]) expect(parseAmount(text)).toBeNull();
  });

  it("reads dates day first", () => {
    expect(parseDateInput("01/11/2026")).toBe("2026-11-01");
    expect(parseDateInput("1-11-26")).toBe("2026-11-01");
    expect(parseDateInput("٠١/١١/٢٠٢٦")).toBe("2026-11-01");
    expect(parseDateInput("2026-11-01")).toBe("2026-11-01");
    expect(parseDateInput("29/02/2024")).toBe("2024-02-29");
  });

  it("refuses dates that don't exist", () => {
    for (const text of ["31/02/2026", "29/02/2026", "13/13/2026", "hier", ""]) expect(parseDateInput(text)).toBeNull();
  });

  it("reads Arabic and Persian digits", () => {
    expect(westernDigits("٠١٢٣٤٥٦٧٨٩")).toBe("0123456789");
    expect(westernDigits("۰۱۲۳۴۵۶۷۸۹")).toBe("0123456789");
  });
});

describe("chart scale", () => {
  it("labels only values the data reaches", () => {
    for (const max of [3, 8, 12, 95, 152300, 999999, 1234567]) {
      const { top, ticks } = chartScale(max);
      expect(ticks[0]).toBe(0);
      expect(ticks.at(-1)).toBeLessThanOrEqual(max);
      expect(top).toBeGreaterThan(max);
      expect(ticks.length).toBeGreaterThanOrEqual(2);
      expect(ticks.length).toBeLessThanOrEqual(5);
    }
  });

  it("gives the approved dashboard its ticks", () => {
    expect(chartScale(152300).ticks).toEqual([0, 50000, 100000, 150000]);
  });

  it("survives no data", () => {
    expect(chartScale(0)).toEqual({ top: 1, bottom: 0, ticks: [0] });
  });

  it("goes below zero for a ledger's refunds, and keeps zero on the scale", () => {
    const { top, bottom, ticks } = chartScale(150000, -40000);
    expect(ticks).toEqual([0, 50000, 100000, 150000]);
    expect(top).toBeGreaterThan(150000);
    expect(bottom).toBeLessThan(-40000);
    expect(chartScale(150000, -60000).ticks).toEqual([-50000, 0, 50000, 100000, 150000]);
  });

  it("copes with a series that is all below zero", () => {
    const { top, bottom, ticks } = chartScale(-1000, -9000);
    expect(top).toBe(0);
    expect(bottom).toBeLessThan(-9000);
    expect(ticks).toContain(0);
  });
});

describe("a line chart's points", () => {
  it("spaces points by their place in time, so a gap in the dates shows", () => {
    expect(pointPositions([0, 1, 10])).toEqual([0, 0.1, 1]);
  });

  it("spaces them evenly unless every point has a place", () => {
    expect(pointPositions([undefined, undefined, undefined])).toEqual([0, 0.5, 1]);
    expect(pointPositions([0, undefined, 10])).toEqual([0, 0.5, 1]);
    expect(pointPositions([5, 5, 5])).toEqual([0, 0.5, 1]);
  });

  it("handles one point and none", () => {
    expect(pointPositions([7])).toEqual([0]);
    expect(pointPositions([])).toEqual([]);
  });

  it("labels every point that fits, and otherwise thins them back from the last", () => {
    expect([...labelledPoints([0, 50, 100, 150], [30, 30, 30, 30])].sort((a, b) => a - b)).toEqual([0, 1, 2, 3]);
    const xs = Array.from({ length: 500 }, (_, index) => index / 2);
    const thinned = labelledPoints(xs, xs.map(() => 40));
    expect(thinned.has(499)).toBe(true);
    const kept = [...thinned].map((index) => xs[index] ?? 0).sort((a, b) => a - b);
    kept.slice(1).forEach((x, order) => expect(x - (kept[order] ?? 0)).toBeGreaterThanOrEqual(48));
  });

  it("drops a label that bunches up, even where the rest fit", () => {
    expect([...labelledPoints([0, 100, 104, 200], [30, 30, 30, 30])].sort((a, b) => a - b)).toEqual([0, 2, 3]);
  });

  it("allows less room for joined Arabic letters than for digits", () => {
    expect(labelWidth("سبتمبر")).toBeLessThan(labelWidth("05/11/"));
  });

  it("breaks the line at a gap rather than drawing it as zero", () => {
    expect(lineRuns([1, 2, null, 3, null, null, 4, 5])).toEqual([[0, 1], [3], [6, 7]]);
    expect(lineRuns([null, null])).toEqual([]);
    expect(lineRuns([])).toEqual([]);
  });
});

describe("counts", () => {
  const fields = { one: "يجب تصحيح حقل واحد", two: "يجب تصحيح حقلين", few: "يجب تصحيح {n} حقول", many: "يجب تصحيح {n} حقلا", other: "يجب تصحيح {n} حقل" };

  it("agrees an Arabic noun with its number", () => {
    expect(plural(1, "ar-DZ", fields)).toBe("يجب تصحيح حقل واحد");
    expect(plural(2, "ar-DZ", fields)).toBe("يجب تصحيح حقلين");
    expect(plural(4, "ar-DZ", fields)).toBe("يجب تصحيح 4 حقول");
    expect(plural(12, "ar-DZ", fields)).toBe("يجب تصحيح 12 حقلا");
  });

  it("keeps French to one and many", () => {
    const french = { one: "{n} champ à corriger", other: "{n} champs à corriger" };
    expect(plural(1, "fr-DZ", french)).toBe("1 champ à corriger");
    expect(plural(3, "fr-DZ", french)).toBe("3 champs à corriger");
  });
});
