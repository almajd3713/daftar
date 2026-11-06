import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// @ts-expect-error A plain Node script, with no types of its own.
import { renderFontsCss, renderTokensCss } from "../scripts/generate-tokens.mjs";
import { colors, contrastPairs, sizes, spacing, typeScale } from "../src/tokens.js";

const here = (path: string): string => fileURLToPath(new URL(path, import.meta.url));

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255).map((value) => (value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4));
  const [red = 0, green = 0, blue = 0] = channels;
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(a: string, b: string): number {
  const [high = 0, low = 0] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

describe("generated CSS", () => {
  it("is current", () => {
    expect(readFileSync(here("../src/generated/tokens.css"), "utf8")).toBe(renderTokensCss());
    expect(readFileSync(here("../src/generated/fonts.css"), "utf8")).toBe(renderFontsCss());
  });
});

describe("colour", () => {
  for (const theme of ["light", "dark"] as const) {
    for (const { fg, bg, min } of contrastPairs) {
      it(`${fg} on ${bg} holds ${min}:1 in ${theme}`, () => {
        expect(contrast(colors[fg][theme], colors[bg][theme])).toBeGreaterThanOrEqual(min);
      });
    }
  }

  it("gives every token a usage note and both themes", () => {
    for (const token of Object.values(colors)) {
      expect(token.usage.length).toBeGreaterThan(10);
      expect(token.light).toMatch(/^#[0-9A-F]{6}$/);
      expect(token.dark).toMatch(/^#[0-9A-F]{6}$/);
    }
  });
});

describe("scale", () => {
  const px = (rem: string): number => parseFloat(rem) * 16;

  it("keeps spacing on the 4 px scale, and each name tells its size", () => {
    for (const [name, token] of Object.entries(spacing)) {
      expect(px(token.value)).toBe(Number(name.replace("space-", "")) * 4);
    }
  });

  it("keeps a finger's targets at 44 px or more", () => {
    for (const token of Object.values(sizes)) expect(px(token.touch)).toBeGreaterThanOrEqual(44);
  });

  it("keeps a mouse's targets at WCAG's 24 px or more", () => {
    for (const token of Object.values(sizes)) expect(px(token.value)).toBeGreaterThanOrEqual(24);
  });

  it("allows nothing under 13 px", () => {
    for (const token of Object.values(typeScale)) expect(px(token.size)).toBeGreaterThanOrEqual(13);
  });

  it("keeps Arabic room to breathe at every text size", () => {
    // Arabic renders at 110%, and its dots and tails need more height than Latin. The hero is left out: it sets digits.
    for (const token of [typeScale.small, typeScale.body, typeScale.h2, typeScale.h1]) expect(px(token.line) / (px(token.size) * 1.1)).toBeGreaterThanOrEqual(1.2);
  });
});
