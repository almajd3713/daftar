// Generates src/generated/tokens.css and fonts.css from src/tokens.ts. A test fails if they're out of date.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { arabicSizeAdjust, colors, fontFamily, radii, sizes, spacing, typeScale } from "../src/tokens.ts";

const here = (path) => fileURLToPath(new URL(path, import.meta.url));
const BANNER = "/* Generated from src/tokens.ts by `pnpm generate`. Do not edit. */";

const declare = (entries) => entries.map(([name, value]) => `  --${name}: ${value};`).join("\n");

export function renderTokensCss() {
  const colorEntries = (theme) => Object.entries(colors).map(([name, token]) => [name, token[theme]]);
  const lengths = [
    ...Object.entries(spacing).map(([name, token]) => [name, token.value]),
    ...Object.entries(radii).map(([name, token]) => [name, token.value]),
    ...Object.entries(sizes).map(([name, token]) => [name, token.value]),
  ];
  const type = Object.entries(typeScale).flatMap(([name, token]) => [
    [`t-${name}`, token.size],
    [`l-${name}`, token.line],
  ]);
  const touch = Object.entries(sizes).map(([name, token]) => [name, token.touch]);
  const narrow = Object.entries(typeScale).flatMap(([name, token]) => [
    ...(token.narrow ? [[`t-${name}`, token.narrow]] : []),
    ...(token.narrowLine ? [[`l-${name}`, token.narrowLine]] : []),
  ]);
  return `${BANNER}
:root {
${declare([["font", fontFamily], ["t-input", "var(--t-body)"], ...type, ...lengths, ...colorEntries("light")])}
  color-scheme: light;
}

:root[data-mantine-color-scheme="dark"] {
${declare(colorEntries("dark"))}
  color-scheme: dark;
}

/* A browser font size under 16 px makes iOS zoom into a field. */
@media (pointer: coarse) {
  :root {
${declare([...touch, ["t-input", "1rem"]]).replaceAll(/^/gm, "  ")}
  }
}

[data-layout="narrow"] {
${declare([...touch, ...narrow, ["t-input", "1rem"]])}
}
`;
}

const ARABIC =
  "U+0600-06FF,U+0750-077F,U+0870-088E,U+0890-0891,U+0897-08E1,U+08E3-08FF,U+200C-200E,U+2010-2011,U+204F,U+2E41,U+FB50-FDFF,U+FE70-FE74,U+FE76-FEFC";
const LATIN =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";

export function renderFontsCss() {
  const face = (subset, ranges, weight, adjust) => `@font-face {
  font-family: "Daftar Plex";
  font-style: normal;
  font-weight: ${weight};
  font-display: swap;${adjust ? `\n  size-adjust: ${adjust};` : ""}
  src: url("../fonts/ibm-plex-sans-arabic-${subset}-${weight}-normal.woff2") format("woff2");
  unicode-range: ${ranges};
}
`;
  const faces = [400, 500, 700].flatMap((weight) => [face("arabic", ARABIC, weight, arabicSizeAdjust), face("latin", LATIN, weight)]);
  return `${BANNER}\n${faces.join("\n")}`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(here("../src/generated/tokens.css"), renderTokensCss());
  writeFileSync(here("../src/generated/fonts.css"), renderFontsCss());
}
