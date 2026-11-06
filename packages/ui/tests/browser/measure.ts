/** What can be measured about a screen, for the reference app and the real one alike. */
import { expect } from "@playwright/test";

/** Runs in the page: returns one string per problem. */
export function measure(): Record<string, string[]> {
  const SCALE = new Set([0, 4, 8, 12, 16, 24, 32, 48]);
  const out: Record<string, string[]> = { overflow: [], tap: [], contrast: [], small: [], arabic: [], tabular: [], spacing: [], clipped: [] };
  const narrow = document.querySelector("[data-layout]")?.getAttribute("data-layout") === "narrow";
  const rgb = (text: string): { r: number; g: number; b: number; a: number } | null => {
    const match = /rgba?\(([^)]+)\)/.exec(text);
    if (!match?.[1]) return null;
    const [r = 0, g = 0, b = 0, a = 1] = match[1].split(/[ ,/]+/).map(Number);
    return { r, g, b, a };
  };
  const lum = (color: { r: number; g: number; b: number }): number => {
    const [r = 0, g = 0, b = 0] = [color.r, color.g, color.b].map((value) => {
      const v = value / 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: { r: number; g: number; b: number }, b: { r: number; g: number; b: number }): number => {
    const [high = 0, low = 0] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (high + 0.05) / (low + 0.05);
  };
  const background = (element: Element): { r: number; g: number; b: number } => {
    const stack: { r: number; g: number; b: number; a: number }[] = [];
    for (let node: Element | null = element; node; node = node.parentElement) {
      const color = rgb(getComputedStyle(node).backgroundColor);
      if (color && color.a > 0) {
        stack.push(color);
        if (color.a === 1) break;
      }
    }
    let base = { r: 255, g: 255, b: 255 };
    for (const color of stack.reverse()) base = { r: color.r * color.a + base.r * (1 - color.a), g: color.g * color.a + base.g * (1 - color.a), b: color.b * color.a + base.b * (1 - color.a) };
    return base;
  };
  const name = (element: Element): string => `${element.tagName.toLowerCase()} "${(element.textContent ?? "").trim().slice(0, 24)}"`;
  const hidden = (element: Element): boolean => {
    const box = element.getBoundingClientRect();
    return !box.width || !box.height || getComputedStyle(element).visibility === "hidden";
  };

  const main = document.querySelector("main");
  if (document.documentElement.scrollWidth > document.documentElement.clientWidth + 1) out.overflow?.push(`page ${document.documentElement.scrollWidth} > ${document.documentElement.clientWidth}`);
  if (main && narrow && main.scrollWidth > main.clientWidth + 1) out.overflow?.push(`main ${main.scrollWidth} > ${main.clientWidth}`);

  const need = narrow ? 44 : 24;
  document.querySelectorAll("button, a[href], input, select, textarea, summary").forEach((element) => {
    if (hidden(element) || element.closest("[class*=skip]") || element.closest("details:not([open]) table")) return;
    const box = element.getBoundingClientRect();
    if (box.height < need - 0.5 || (narrow && box.width < need - 0.5 && !element.matches("input, select, textarea"))) out.tap?.push(`${name(element)} ${Math.round(box.width)}x${Math.round(box.height)}`);
  });

  document.querySelectorAll("body *").forEach((element) => {
    if (element.closest("svg") || element.closest("details:not([open]) > :not(summary)") || hidden(element)) return;
    const style = getComputedStyle(element);
    for (const property of ["paddingTop", "paddingBottom", "marginTop", "marginBottom", "rowGap"] as const) {
      const raw = style[property];
      if (raw === "normal" || raw === "auto") continue;
      const value = Math.abs(parseFloat(raw));
      if (element.closest("[data-layout]") && value > 1 && !SCALE.has(Math.round(value * 100) / 100) && !element.closest("[class*=mantine], [class*=m_]") && !element.matches("[class*=mantine], [class*=m_], option, i, [style]") && property !== "marginTop") out.spacing?.push(`${name(element)} ${property} ${raw}`);
    }
    const own = [...element.childNodes].filter((node) => node.nodeType === 3 && node.textContent?.trim());
    const value = element.matches("input, textarea") ? (element as HTMLInputElement).value : own.map((node) => node.textContent).join("");
    if (!value.trim()) return;
    if (style.clipPath !== "none") return;
    const size = parseFloat(style.fontSize);
    const color = rgb(style.color);
    if (color) {
      const contrast = ratio(color, background(element));
      const big = size >= 24 || (size >= 18.66 && Number(style.fontWeight) >= 700);
      if (contrast < (big ? 3 : 4.5) - 0.01) out.contrast?.push(`${contrast.toFixed(2)} ${name(element)} ${style.color}`);
    }
    if (size < 12.99) out.small?.push(`${size}px ${name(element)}`);
    if (/[؀-ۿ]/.test(value)) {
      if (style.letterSpacing !== "normal" && parseFloat(style.letterSpacing) !== 0) out.arabic?.push(`spacing ${style.letterSpacing} ${name(element)}`);
      const line = parseFloat(style.lineHeight);
      if (!Number.isNaN(line) && line / (size * 1.1) < 1.15) out.arabic?.push(`tight ${(line / size).toFixed(2)} ${name(element)}`);
    }
    if (element.scrollWidth > element.clientWidth + 1 && style.overflowX === "hidden" && style.display !== "inline") out.clipped?.push(`${name(element)} ${element.scrollWidth} > ${element.clientWidth}`);
  });

  document.querySelectorAll("td[class*=numeric] bdi, [class*=rowAmount] bdi").forEach((element) => {
    if (!getComputedStyle(element).fontVariantNumeric.includes("tabular")) out.tabular?.push(name(element));
  });
  return out;
}

export function expectClean(problems: Record<string, string[]>): void {
  for (const [kind, list] of Object.entries(problems)) expect(list, kind).toEqual([]);
}
