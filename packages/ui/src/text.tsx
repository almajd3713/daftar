/** Small pieces of text that carry a rule: how a number, a date or a name of unknown script must be set. */
import type { ReactNode } from "react";

import { formatDate, formatDateTime, formatMoney, formatNumber, formatPercent } from "./format.js";
import { useDaftar } from "./provider.js";
import classes from "./text.module.css";

/** Text someone typed, in whatever script they typed it. It sits in any layout without reordering around it. */
export function UserText({ children }: { children: ReactNode }): ReactNode {
  return <bdi dir="auto">{children}</bdi>;
}

/** Left to right, always: a receipt number, a cell reference, a formula. */
export function CodeText({ children }: { children: ReactNode }): ReactNode {
  return (
    <bdi dir="ltr" className={classes.figures}>
      {children}
    </bdi>
  );
}

export interface AmountProps {
  value: number | null | undefined;
  precision?: number | undefined;
  /** Red pen. Put a word beside it too: colour alone doesn't say late. */
  late?: boolean | undefined;
  /** A total should show 0,00. A row's zero shows as a dash, as in Excel's Accounting format. */
  showZero?: boolean | undefined;
}

/** A number for a column: tabular, no currency (the column heading has it), and a dash for zero. */
export function Amount({ value, precision = 2, late, showZero }: AmountProps): ReactNode {
  const { locale } = useDaftar();
  if (value === null || value === undefined) return null;
  const text = formatNumber(value, locale, precision);
  if (value === 0 && !showZero) {
    return (
      <span className={classes.zero} role="img" aria-label={text}>
        –
      </span>
    );
  }
  return (
    <bdi dir="ltr" className={late ? `${classes.figures} ${classes.lateFigure}` : classes.figures}>
      {text}
    </bdi>
  );
}

/** An amount that stands alone, so it carries its currency. */
export function Money({ value, precision = 2, late }: { value: number; precision?: number; late?: boolean }): ReactNode {
  const { locale } = useDaftar();
  return <bdi className={late ? `${classes.figures} ${classes.nowrap} ${classes.lateFigure}` : `${classes.figures} ${classes.nowrap}`}>{formatMoney(value, locale, precision)}</bdi>;
}

export function Percent({ ratio }: { ratio: number }): ReactNode {
  const { locale } = useDaftar();
  return <bdi className={`${classes.figures} ${classes.nowrap}`}>{formatPercent(ratio, locale)}</bdi>;
}

/** A stored `YYYY-MM-DD`. */
export function DateText({ value }: { value: string | null | undefined }): ReactNode {
  const { locale } = useDaftar();
  if (!value) return null;
  return <bdi className={`${classes.figures} ${classes.nowrap}`}>{formatDate(value, locale)}</bdi>;
}

/** A stored instant, in the firm's time zone. */
export function DateTimeText({ value, timeZone }: { value: string; timeZone?: string }): ReactNode {
  const { locale } = useDaftar();
  const { date, time } = formatDateTime(value, locale, timeZone);
  return (
    <>
      <bdi className={`${classes.figures} ${classes.nowrap}`}>{date}</bdi>{" "}
      <bdi dir="ltr" className={classes.figures}>
        {time}
      </bdi>
    </>
  );
}

/** Calling a customer is what a phone number is for here. Never mirrored, per Wikimedia's guidance. */
export function PhoneLink({ value, display }: { value: string; display?: string }): ReactNode {
  return (
    <a className={classes.phone} href={`tel:${value.replace(/[^+\d]/g, "")}`}>
      <bdi dir="ltr" className={classes.figures}>
        {display ?? value}
      </bdi>
    </a>
  );
}

/** The word that goes with red, so late never depends on seeing colour. */
export function LateTag({ label }: { label?: string }): ReactNode {
  const { ui } = useDaftar();
  return <span className={classes.lateTag}>{label ?? ui("late")}</span>;
}

/** A link that reads as one on any ground. The ink blue is too close to body text for colour to do it alone. */
export function TextLink({ children, onClick, href }: { children: ReactNode; onClick?: (() => void) | undefined; href?: string | undefined }): ReactNode {
  if (href) {
    return (
      <a className={classes.link} href={href} onClick={onClick}>
        {children}
      </a>
    );
  }
  return (
    <button type="button" className={classes.link} onClick={onClick}>
      {children}
    </button>
  );
}

const HEX = /^#[0-9a-fA-F]{6}$/;

export interface StatusChipProps {
  /** The workbook's colour, whatever it is. Only a swatch wears it, so it can't make the text unreadable. */
  color?: string | null | undefined;
  label: ReactNode;
}

/** A state: a square of the workbook's colour, and always the word. */
export function StatusChip({ color, label }: StatusChipProps): ReactNode {
  return (
    <span className={classes.chip}>
      <i aria-hidden="true" className={classes.swatch} style={color && HEX.test(color) ? { background: color } : undefined} />
      <span>{label}</span>
    </span>
  );
}

export type ConfidenceLevel = "low" | "medium" | "high";

const LEVELS = { low: 1, medium: 2, high: 3 } as const;
const WORDS = { low: "confidenceLow", medium: "confidenceMedium", high: "confidenceHigh" } as const;

/** How sure the analyser is: three squares and the word (R-10). */
export function Confidence({ level }: { level: ConfidenceLevel }): ReactNode {
  const { ui } = useDaftar();
  return (
    <span className={classes.confidence}>
      <i aria-hidden="true" className={classes.confidenceMarks}>
        {[1, 2, 3].map((step) => (
          <b key={step} className={step <= LEVELS[level] ? classes.confidenceOn : undefined} />
        ))}
      </i>
      {ui(WORDS[level])}
    </span>
  );
}
