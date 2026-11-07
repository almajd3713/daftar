/** How records are shown: the ledger table, its phone rows, facts, history, statements and the board. */
import type { ReactNode, Ref } from "react";

import { useFrame } from "./provider.js";
import classes from "./data.module.css";

export interface Column<Row> {
  key: string;
  header: ReactNode;
  /** The unit, once, under the heading: never in each cell. */
  unit?: ReactNode;
  /** Right-aligned in both directions, because digits don't reverse and place value has to line up. */
  numeric?: boolean | undefined;
  nowrap?: boolean | undefined;
  cell: (row: Row) => ReactNode;
}

export interface LedgerTableProps<Row> {
  /** Read out to screen readers. */
  caption: string;
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  /** Closes the table with the double rule. Values are by column key. */
  totals?: Record<string, ReactNode> | undefined;
  totalLabel?: ReactNode;
}

/** One hairline per row, an ink rule under the heading, a double rule under the total. No vertical rules, no stripes. */
export function LedgerTable<Row>({ caption, columns, rows, rowKey, totals, totalLabel }: LedgerTableProps<Row>): ReactNode {
  const firstTotal = totals ? columns.findIndex((column) => column.key in totals) : -1;
  const span = firstTotal > 0 ? firstTotal : 1;
  return (
    <div className={classes.scroll} tabIndex={0} role="region" aria-label={caption}>
      <table className={classes.table}>
        <caption className={classes.visuallyHidden}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.numeric ? classes.numeric : undefined}>
                {column.header}
                {column.unit ? <small>{column.unit}</small> : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => {
                const names = [column.numeric ? classes.numeric : "", column.nowrap || column.numeric ? classes.nowrap : ""].filter(Boolean).join(" ");
                return (
                  <td key={column.key} className={names || undefined}>
                    {column.cell(row)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        {totals ? (
          <tfoot>
            <tr>
              <th scope="row" colSpan={span}>
                {totalLabel}
              </th>
              {columns.slice(span).map((column) => (
                <td key={column.key} className={column.numeric ? `${classes.numeric} ${classes.nowrap}` : undefined}>
                  {totals[column.key]}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}

export interface RecordRowProps {
  title: ReactNode;
  amount?: ReactNode;
  /** Number and date, under the title. */
  meta?: ReactNode;
  status?: ReactNode;
  late?: boolean | undefined;
  onClick?: (() => void) | undefined;
}

/** A table row on a phone: two lines, and the whole row is the target. */
export function RecordRow({ title, amount, meta, status, onClick }: RecordRowProps): ReactNode {
  return (
    <li>
      <button type="button" className={classes.row} onClick={onClick}>
        <span className={classes.rowTitle}>{title}</span>
        <span className={classes.rowAmount}>{amount}</span>
        <span className={classes.rowMeta}>{meta}</span>
        <span className={classes.rowStatus}>{status}</span>
      </button>
    </li>
  );
}

/** The list of `RecordRow`s, with what its two columns mean above them. */
export function RecordList({ titleHeading, amountHeading, children }: { titleHeading?: ReactNode; amountHeading?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <>
      {titleHeading || amountHeading ? (
        <div className={classes.rowsHead}>
          <span>{titleHeading}</span>
          <span>{amountHeading}</span>
        </div>
      ) : null}
      <ul>{children}</ul>
    </>
  );
}

/** Says what's true, what belongs here, and offers the way to start. Only after loading has really finished. */
export function EmptyState({ title, children, actions }: { title: ReactNode; children?: ReactNode; actions?: ReactNode }): ReactNode {
  return (
    <div className={classes.empty}>
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {actions ? <div className={classes.emptyActions}>{actions}</div> : null}
    </div>
  );
}

/** Where a long list has got to, and the way on. Pass the two buttons; leave one out at an end. */
export function Pager({ label, status, previous, next }: { label: string; status: ReactNode; previous?: ReactNode; next?: ReactNode }): ReactNode {
  return (
    <nav className={classes.pager} aria-label={label}>
      <span className={classes.pagerStatus}>{status}</span>
      <div className={classes.pagerButtons}>
        {previous}
        {next}
      </div>
    </nav>
  );
}

export interface NoticeProps {
  /** `wrong` is red pen: something failed or needs fixing. `note` is ink: worth reading, but nothing is wrong. */
  tone?: "note" | "wrong" | undefined;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}

/** A message that stays on the page until it stops being true. A mark in the margin, like a field's error: no box. */
export function Notice({ tone = "note", title, children, actions }: NoticeProps): ReactNode {
  return (
    <section className={tone === "wrong" ? `${classes.notice} ${classes.noticeWrong}` : classes.notice} role={tone === "wrong" ? "alert" : "status"}>
      <h2>{title}</h2>
      {children ? <div>{children}</div> : null}
      {actions ? <div className={classes.noticeActions}>{actions}</div> : null}
    </section>
  );
}

/** Work running on the server. Its length isn't known, so it shows movement, and never a percentage it can't back. */
export function Waiting({ children }: { children: ReactNode }): ReactNode {
  return (
    <div className={classes.waiting} role="status">
      <span>{children}</span>
      <span className={classes.waitingTrack} aria-hidden="true">
        <i />
      </span>
    </div>
  );
}

/** A record's values, label and value on one line. */
export function FactList({ children }: { children: ReactNode }): ReactNode {
  return <dl className={classes.facts}>{children}</dl>;
}

export function Fact({ label, children }: { label: ReactNode; children: ReactNode }): ReactNode {
  return (
    <div className={classes.fact}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Two equal columns on a PC, stacked on a phone. A record's facts, then its history. */
export function TwoColumns({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.twoColumns}>{children}</div>;
}

export function Gutter({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.gutter}>{children}</div>;
}

export function SectionHeading({ children, ruled }: { children: ReactNode; ruled?: boolean }): ReactNode {
  return <h2 className={ruled ? classes.headingRuled : classes.heading}>{children}</h2>;
}

export interface HistoryEntry {
  key: string;
  /** When, who and through what: UI, import, workflow or system (R-18). */
  meta: ReactNode;
  /** One line per field changed. */
  changes: ReactNode;
  action?: ReactNode;
}

/** A record's timeline, newest first. */
export function HistoryList({ title, entries }: { title: ReactNode; entries: HistoryEntry[] }): ReactNode {
  return (
    <section>
      <SectionHeading ruled>{title}</SectionHeading>
      <ol>
        {entries.map((entry) => (
          <li key={entry.key} className={classes.historyItem}>
            <p className={classes.historyMeta}>{entry.meta}</p>
            <div>{entry.changes}</div>
            {entry.action}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** One change. The old value is muted rather than struck through, because a strike runs through Arabic. */
export function Change({ label, from, to, arrow }: { label: ReactNode; from: ReactNode; to: ReactNode; arrow: "←" | "→" }): ReactNode {
  return (
    <p>
      {label} <span className={classes.oldValue}>{from}</span> {arrow} {to}
    </p>
  );
}

/** What a page offers last and least, such as deleting: away from what's used every day. */
export function LastActions({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.lastActions}>{children}</div>;
}

/** Label and value lines that may end in a total, like a short account. */
export interface StatementProps {
  title?: ReactNode;
  /** It's where an answer arrives: a screen reader hears it, and `ref` can take focus to it, which closes a phone's keyboard. */
  live?: boolean | undefined;
  ref?: Ref<HTMLDivElement> | undefined;
  children: ReactNode;
}

export function Statement({ title, live, ref, children }: StatementProps): ReactNode {
  return (
    <div ref={ref} className={classes.statement} {...(live ? { tabIndex: -1, "aria-live": "polite" as const } : {})}>
      {title ? <SectionHeading ruled>{title}</SectionHeading> : null}
      <dl>{children}</dl>
    </div>
  );
}

export function StatementLine({ label, children, total }: { label: ReactNode; children: ReactNode; total?: boolean }): ReactNode {
  return (
    <div className={total ? `${classes.line} ${classes.lineTotal}` : classes.line}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export interface HeroFigureProps {
  label: ReactNode;
  /** The figure, formatted. A decimal part is set smaller, because in a headline it's noise. */
  value: string;
  unit?: ReactNode;
  note?: ReactNode;
}

/** The one number a dashboard leads with. One per view. */
export function HeroFigure({ label, value, unit, note }: HeroFigureProps): ReactNode {
  const comma = value.lastIndexOf(",");
  return (
    <div className={classes.hero}>
      <span className={classes.heroLabel}>{label}</span>
      <div className={classes.heroValue}>
        <bdi dir="ltr" className={classes.nowrap}>
          {comma >= 0 ? value.slice(0, comma) : value}
          {comma >= 0 ? <span className={classes.heroPart}>{value.slice(comma)}</span> : null}
        </bdi>
        {unit ? <span className={classes.heroPart}> {unit}</span> : null}
      </div>
      {note ? <span className={classes.heroLabel}>{note}</span> : null}
    </div>
  );
}

/** A dashboard's lead: the figure, and what else matters as a short statement. */
export function LeadRow({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.leadRow}>{children}</div>;
}

export function Panels({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.panels}>{children}</div>;
}

export function Panel({ title, wide, children }: { title?: ReactNode; wide?: boolean; children: ReactNode }): ReactNode {
  return (
    <section className={wide ? classes.panelWide : undefined}>
      {title ? <SectionHeading>{title}</SectionHeading> : null}
      {children}
    </section>
  );
}

/** The board's columns on a PC. On a phone a board shows one state at a time, chosen with `ViewTabs`. */
export function BoardColumns({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.board}>{children}</div>;
}

export function BoardColumn({ heading, count, children }: { heading: ReactNode; count: number; children: ReactNode }): ReactNode {
  return (
    <section className={classes.column}>
      <div className={classes.columnHead}>
        <h2>{heading}</h2>
        <span className={classes.columnCount}>{count}</span>
      </div>
      <div>{children}</div>
    </section>
  );
}

export interface BoardCardProps {
  title: ReactNode;
  number?: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  /** The next step, as a button, so moving a card never depends on dragging (WCAG 2.5.7). */
  action?: ReactNode;
  /** Why a move was refused (R-20). */
  refusal?: { title: ReactNode; reason: ReactNode } | undefined;
}

export function BoardCard({ title, number, subtitle, meta, action, refusal }: BoardCardProps): ReactNode {
  // On a PC a card sits under its column's heading. A phone shows one state, so nothing sits between it and the title.
  const { narrow } = useFrame();
  const Heading = narrow ? "h2" : "h3";
  return (
    <article className={classes.card}>
      <div className={classes.cardTop}>
        <Heading className={classes.cardTitle}>{title}</Heading>
        {number ? <span className={classes.cardNumber}>{number}</span> : null}
      </div>
      {subtitle ? <p>{subtitle}</p> : null}
      {meta ? <p className={classes.cardMeta}>{meta}</p> : null}
      {action ? <div className={classes.cardAction}>{action}</div> : null}
      {refusal ? (
        <div className={classes.refusal} role="status">
          <b>{refusal.title}</b>
          {refusal.reason}
        </div>
      ) : null}
    </article>
  );
}

/** A state and a number, under a record's title. */
export function StateLine({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.stateLine}>{children}</div>;
}

export function MenuList({ children }: { children: ReactNode }): ReactNode {
  return <ul className={classes.menu}>{children}</ul>;
}

export function MenuHeading({ children }: { children: ReactNode }): ReactNode {
  return <li className={classes.menuHeading}>{children}</li>;
}

export function MenuItem({ label, value, onClick }: { label: ReactNode; value?: ReactNode; onClick?: (() => void) | undefined }): ReactNode {
  return (
    <li>
      <button type="button" className={classes.menuItem} onClick={onClick}>
        <span>{label}</span>
        {value ? <span className={classes.menuValue}>{value}</span> : null}
      </button>
    </li>
  );
}
