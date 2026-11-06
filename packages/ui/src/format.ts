/**
 * R-21's formats, written out by hand rather than left to Intl.
 *
 * Intl's output depends on the browser's copy of ICU, so an older phone could show other digits or month
 * names, and `fr-DZ` puts U+202F inside numbers, which no webfont subset here has. Time zones are the one
 * thing still taken from Intl. tests/format.test.ts checks this code against Node's Intl.
 */

export type Locale = "fr-DZ" | "ar-DZ";
export type Lang = "fr" | "ar";

/** The same shape as a spec label or a server message. */
export interface Label {
  fr: string;
  ar: string;
}

export const langOf = (locale: Locale): Lang => (locale === "ar-DZ" ? "ar" : "fr");
export const dirOf = (locale: Locale): "rtl" | "ltr" => (locale === "ar-DZ" ? "rtl" : "ltr");
export const pick = (label: Label, locale: Locale): string => label[langOf(locale)];

const NBSP = "\u00a0";
const RLM = "\u200f";
const MINUS = "\u2212";

const MONTHS: Record<Lang, { long: string[]; short: string[] }> = {
  fr: {
    long: ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    short: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
  },
  ar: {
    long: ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
    short: ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
  },
};

function fixed(value: number, precision: number): string {
  // Rounds half away from zero on the decimal digits, as a person expects, where toFixed may not.
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: precision, maximumFractionDigits: precision, useGrouping: false }).format(Math.abs(value));
}

export function formatNumber(value: number, locale: Locale, precision = 2): string {
  const [whole = "0", fraction] = fixed(value, precision).split(".");
  const group = locale === "fr-DZ" ? NBSP : ".";
  const grouped = whole.replace(/\B(?=(?:\d{3})+$)/g, group);
  const isZero = /^[0.]*$/.test(fixed(value, precision));
  return `${value < 0 && !isZero ? MINUS : ""}${grouped}${fraction ? `,${fraction}` : ""}`;
}

export function formatMoney(value: number, locale: Locale, precision = 2): string {
  const amount = formatNumber(value, locale, precision);
  return locale === "fr-DZ" ? `${amount}${NBSP}DA` : `${RLM}${amount}${NBSP}د.ج.${RLM}`;
}

export const currencyLabel = (locale: Locale): string => (locale === "fr-DZ" ? "DA" : "د.ج.");

/** A ratio: 0.05 is 5 %. French sets a space before the sign, Arabic doesn't. */
export function formatPercent(ratio: number, locale: Locale): string {
  const percent = formatNumber(ratio * 100, locale, 2).replace(/,?0+$/, "");
  return locale === "fr-DZ" ? `${percent}${NBSP}%` : `${percent}%`;
}

/** An Algerian number as people read it out: 0550 12 34 56, 021 12 34 56. Anything else stays as stored. */
export function formatPhone(value: string): string {
  const match = /^(\+213|00213|0)(\d{2,3})(\d{2})(\d{2})(\d{2})$/.exec(value);
  if (!match) return value;
  const [, prefix, area, first, second, third] = match;
  return `${prefix === "0" ? `0${area}` : `${prefix} ${area}`} ${first} ${second} ${third}`;
}

/** For chart axes: 150 k, 150 ألف. */
export function formatCompact(value: number, locale: Locale): string {
  const abs = Math.abs(value);
  if (abs < 1000) return formatNumber(value, locale, 0);
  const [scaled, unit] = abs < 1_000_000 ? [value / 1000, locale === "fr-DZ" ? "k" : "ألف"] : [value / 1_000_000, locale === "fr-DZ" ? "M" : "مليون"];
  return `${formatNumber(scaled, locale, 0)}${NBSP}${unit}`;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

/** A stored `YYYY-MM-DD`. In Arabic the marks keep day, month and year in reading order, from the right. */
export function formatDate(iso: string, locale: Locale): string {
  const match = ISO_DATE.exec(iso);
  if (!match) return iso;
  const [, year, month, day] = match as unknown as [string, string, string, string];
  return locale === "ar-DZ" ? `${day}${RLM}/${month}${RLM}/${year}` : `${day}/${month}/${year}`;
}

export function monthName(month: number, locale: Locale, style: "long" | "short" = "short"): string {
  return MONTHS[langOf(locale)][style][month - 1] ?? String(month);
}

/** A stored instant, shown in the firm's time zone: the date as formatDate gives it, and HH:mm. */
export function formatDateTime(instant: string, locale: Locale, timeZone = "Africa/Algiers"): { date: string; time: string } {
  const moment = new Date(instant);
  if (Number.isNaN(moment.getTime())) return { date: instant, time: "" };
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(moment);
  const part = (type: Intl.DateTimeFormatPartTypes): string => parts.find((item) => item.type === type)?.value ?? "";
  return { date: formatDate(`${part("year")}-${part("month")}-${part("day")}`, locale), time: `${part("hour")}:${part("minute")}` };
}

/** Today's `YYYY-MM-DD` where the firm is, not where the device thinks it is. */
export function todayIn(timeZone = "Africa/Algiers", now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function westernDigits(text: string): string {
  return text.replace(/[٠-٩]/g, (digit) => String(digit.charCodeAt(0) - 0x0660)).replace(/[۰-۹]/g, (digit) => String(digit.charCodeAt(0) - 0x06f0));
}

/** What someone typed into an amount field, in either language's habits. Null when it isn't a number. */
export function parseAmount(text: string): number | null {
  let cleaned = westernDigits(text).replace(/[\s\u00a0\u202f\u200e\u200f]/g, "").replace(/\u2212/g, "-").replace(/(DA|DZD|د\.?ج\.?)$/i, "");
  if (!cleaned) return null;
  const lastComma = cleaned.lastIndexOf(",");
  const lastDot = cleaned.lastIndexOf(".");
  if (lastComma >= 0 && lastDot >= 0) {
    const decimal = lastComma > lastDot ? "," : ".";
    const group = decimal === "," ? "." : ",";
    cleaned = cleaned.split(group).join("").replace(decimal, ".");
  } else if (lastComma >= 0) {
    cleaned = cleaned.replace(",", ".");
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(cleaned)) {
    // `1.234` is how ar-DZ writes a thousand, and nobody types three decimals on a dinar amount.
    cleaned = cleaned.split(".").join("");
  }
  if (!/^-?\d*\.?\d+$/.test(cleaned)) return null;
  return Number(cleaned);
}

function realDate(year: number, month: number, day: number): string | null {
  const moment = new Date(Date.UTC(year, month - 1, day));
  if (moment.getUTCFullYear() !== year || moment.getUTCMonth() !== month - 1 || moment.getUTCDate() !== day) return null;
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** A typed date as `YYYY-MM-DD`: dd/mm/yyyy first, as R-5 reads them, with any separator or digits. */
export function parseDateInput(text: string): string | null {
  const cleaned = westernDigits(text).replace(/[\s\u200e\u200f]/g, "");
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(cleaned);
  if (iso) return realDate(Number(iso[1]), Number(iso[2]), Number(iso[3]));
  const local = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(cleaned);
  if (!local) return null;
  const year = Number(local[3]);
  return realDate(year < 100 ? 2000 + year : year, Number(local[2]), Number(local[1]));
}

/** Arabic counts need more forms than French, so text goes through Intl's plural rules. */
export function plural(count: number, locale: Locale, forms: Partial<Record<Intl.LDMLPluralRule, string>> & { other: string }): string {
  const form = forms[new Intl.PluralRules(locale).select(count)] ?? forms.other;
  return form.replace("{n}", formatNumber(count, locale, 0));
}
