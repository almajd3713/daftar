/**
 * Registre's design tokens: the one source for every colour, size and space.
 *
 * `scripts/generate-tokens.mjs` writes src/generated/tokens.css and fonts.css from this file, and a test
 * fails if they're out of date. Components read the CSS variables; theme.ts points Mantine at the same ones.
 * Keep this file free of imports: Node runs it directly when generating.
 */

export interface ColorToken {
  light: string;
  dark: string;
  usage: string;
}

/** Each is exposed as `--<name>`. */
export const colors = {
  paper: { light: "#FBFCFE", dark: "#12161F", usage: "The page. Everything sits directly on it: no cards." },
  surface: { light: "#FFFFFF", dark: "#191E2A", usage: "Inside inputs, so a field reads as a place to write." },
  raised: { light: "#F1F4FA", dark: "#1C2230", usage: "Hover on a row or quiet button, and the active finding." },
  fill: { light: "#EEF1F7", dark: "#1F2533", usage: "Row and column headings on a sheet grid, and progress tracks." },
  ink: { light: "#161E31", dark: "#E8ECF4", usage: "Body text on paper, surface, raised and fill." },
  muted: { light: "#4C566B", dark: "#A7B1C4", usage: "Secondary text on paper, surface, raised and fill: labels, hints, table headings." },
  rule: { light: "#D3DAE6", dark: "#2F3848", usage: "The hairline between rows and sections. Decorative, so no contrast floor." },
  "rule-input": { light: "#7C879B", dark: "#6F7A90", usage: "Borders of inputs and quiet buttons. Holds 3:1 on paper and surface." },
  "rule-strong": { light: "#161E31", dark: "#C6CEDD", usage: "The ink rule under a table heading, and both lines of a total's double rule." },
  accent: { light: "#1C2F80", dark: "#9DBEF5", usage: "Ballpoint blue: the primary action, links, the current tab. Text on paper, surface and raised." },
  "accent-hover": { light: "#142362", dark: "#BCD3FA", usage: "The primary action under the pointer." },
  "on-accent": { light: "#FFFFFF", dark: "#101726", usage: "Text and icons on accent and accent-hover." },
  late: { light: "#A81C24", dark: "#FF9A9A", usage: "Red pen: only what is overdue or wrong. Text on paper, surface, raised and late-soft. Always beside a word." },
  "late-soft": { light: "#FCEBEC", dark: "#3B1F24", usage: "The ground of a flagged cell on a sheet grid." },
  focus: { light: "#1C2F80", dark: "#9DBEF5", usage: "The 2px focus ring. Holds 3:1 on every surface." },
  chart: { light: "#2A4BC4", dark: "#5B8DEB", usage: "Chart marks and progress fill. Never text." },
  evidence: { light: "#DCE4F8", dark: "#25315A", usage: "The cells a finding is based on, on a sheet grid. Ink text stays readable on it." },
} as const satisfies Record<string, ColorToken>;

export type ColorName = keyof typeof colors;

/** Pairs that must stay readable, checked in both themes by tests/tokens.test.ts. Minimum is the WCAG ratio. */
export const contrastPairs: readonly { fg: ColorName; bg: ColorName; min: number }[] = [
  ...(["paper", "surface", "raised", "fill", "evidence"] as const).map((bg) => ({ fg: "ink" as const, bg, min: 4.5 })),
  ...(["paper", "surface", "raised", "fill"] as const).map((bg) => ({ fg: "muted" as const, bg, min: 4.5 })),
  ...(["paper", "surface", "raised"] as const).map((bg) => ({ fg: "accent" as const, bg, min: 4.5 })),
  ...(["paper", "surface", "raised", "late-soft"] as const).map((bg) => ({ fg: "late" as const, bg, min: 4.5 })),
  { fg: "ink", bg: "late-soft", min: 4.5 },
  { fg: "on-accent", bg: "accent", min: 4.5 },
  { fg: "on-accent", bg: "accent-hover", min: 4.5 },
  ...(["paper", "surface"] as const).map((bg) => ({ fg: "rule-input" as const, bg, min: 3 })),
  ...(["paper", "surface", "raised"] as const).map((bg) => ({ fg: "focus" as const, bg, min: 3 })),
  ...(["paper", "surface"] as const).map((bg) => ({ fg: "rule-strong" as const, bg, min: 3 })),
  { fg: "chart", bg: "paper", min: 3 },
];

export interface LengthToken {
  value: string;
  usage: string;
}

/** A 4 px scale, in rem so it follows the phone's text size. Named by multiples of 4 px. */
export const spacing = {
  "space-1": { value: ".25rem", usage: "Between a label and its input." },
  "space-2": { value: ".5rem", usage: "Inside a group: buttons side by side, a row's own padding on a phone." },
  "space-3": { value: ".75rem", usage: "Table cell padding, input padding." },
  "space-4": { value: "1rem", usage: "Between fields, and the side gutter on a phone." },
  "space-6": { value: "1.5rem", usage: "Between groups: tabs under a heading, panels of a dashboard." },
  "space-8": { value: "2rem", usage: "The page's padding on a PC." },
  "space-12": { value: "3rem", usage: "Between big blocks: the two columns of a record." },
} as const satisfies Record<string, LengthToken>;

/** Square by default. A ledger's edges are ruled, not rounded. */
export const radii = {
  radius: { value: "2px", usage: "Inputs and buttons. Nothing else is rounded, except a chart bar's end." },
} as const satisfies Record<string, LengthToken>;

export interface SizeToken extends LengthToken {
  /** Where the screen is narrow or the pointer is a finger. */
  touch: string;
}

export const sizes = {
  control: { value: "2.25rem", touch: "3rem", usage: "Height of inputs and buttons." },
  row: { value: "2.5rem", touch: "2.75rem", usage: "Height of a table row. Fixed, so switching language doesn't move the layout." },
  target: { value: "1.5rem", touch: "2.75rem", usage: "The smallest pointer target: WCAG's 24 px with a mouse, 44 px with a finger." },
} as const satisfies Record<string, SizeToken>;

export interface TypeToken {
  size: string;
  line: string;
  weight: number;
  /** The size at narrow widths, where it differs. */
  narrow?: string;
  narrowLine?: string;
  usage: string;
}

/** One scale for both languages. The Arabic face carries size-adjust, so never add a per-language size. */
export const typeScale = {
  small: { size: ".8125rem", line: "1.25rem", weight: 400, usage: "Table headings, labels on facts, hints, status of a row. The smallest size allowed." },
  body: { size: ".875rem", line: "1.5rem", weight: 400, narrow: ".9375rem", usage: "Running text and table cells." },
  h2: { size: "1rem", line: "1.5rem", weight: 700, usage: "Section headings." },
  h1: { size: "1.5rem", line: "2rem", weight: 700, narrow: "1.25rem", narrowLine: "1.75rem", usage: "The page's one title." },
  hero: { size: "2.5rem", line: "3rem", weight: 700, narrow: "2rem", narrowLine: "2.5rem", usage: "The one lead figure on a dashboard." },
} as const satisfies Record<string, TypeToken>;

export const fontFamily = '"Daftar Plex", system-ui, sans-serif';
export const fontWeights = { regular: 400, medium: 500, bold: 700 } as const;

/** Arabic reads smaller than Latin at one size (heh .41 em, x-height .52 em). This evens them out on one line. */
export const arabicSizeAdjust = "110%";

/** Below this frame width the layout turns into the phone one, wherever the frame sits. */
export const narrowBelowPx = 768;
