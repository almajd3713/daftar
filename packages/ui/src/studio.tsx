/**
 * The Studio's review screen (R-12). The grid uses the ledger's own marks, so what the analyser found reads
 * as a marked-up sheet: an ink rule under the titles, a double rule on the total, a tint on the evidence,
 * and a red-pen box on a cell to check.
 */
import { useId, type ReactNode } from "react";

import { Confidence, type ConfidenceLevel } from "./text.js";
import classes from "./studio.module.css";

/** How a cell reads on the grid, from a finding's evidence. */
export type CellMark = "header" | "total" | "evidence" | "flagged";

export interface SheetCell {
  ref: string;
  /** Already formatted the way the workbook shows it. */
  text: ReactNode;
  numeric?: boolean | undefined;
  mark?: CellMark | undefined;
  colSpan?: number | undefined;
}

export interface SheetGridProps {
  /** Named for screen readers. */
  label: string;
  /** Column letters across the top. */
  columns: string[];
  rows: { row: number; cells: SheetCell[] }[];
  /** A workbook's own direction: a French sheet stays left to right inside an Arabic Studio. */
  dir?: "rtl" | "ltr" | undefined;
}

const MARKS: Record<CellMark, string | undefined> = { header: classes.markHeader, total: classes.markTotal, evidence: classes.markEvidence, flagged: classes.markFlagged };

export function SheetGrid({ label, columns, rows, dir = "ltr" }: SheetGridProps): ReactNode {
  return (
    <div className={classes.scroll} dir={dir} tabIndex={0} role="region" aria-label={label}>
      <table className={classes.sheet}>
        <thead>
          <tr>
            <th aria-hidden="true" />
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ row, cells }) => (
            <tr key={row}>
              <th scope="row">{row}</th>
              {cells.map((cell) => (
                <td key={cell.ref} colSpan={cell.colSpan} className={[cell.numeric ? classes.numeric : "", cell.mark ? MARKS[cell.mark] : ""].filter(Boolean).join(" ") || undefined}>
                  <bdi dir="auto">{cell.text}</bdi>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Names each mark on the grid, drawn the way the grid draws it. */
export function SheetLegend({ header, total, evidence, flagged }: Record<CellMark, ReactNode>): ReactNode {
  return (
    <div className={classes.legend}>
      <span>
        <i aria-hidden="true" className={classes.legendHeader} />
        {header}
      </span>
      <span>
        <i aria-hidden="true" className={classes.legendTotal} />
        {total}
      </span>
      <span>
        <i aria-hidden="true" className={classes.legendEvidence} />
        {evidence}
      </span>
      <span>
        <i aria-hidden="true" className={classes.legendFlagged} />
        {flagged}
      </span>
    </div>
  );
}

export interface FindingProps {
  kind: ReactNode;
  level: ConfidenceLevel;
  /** The explanation, with Latin, ranges and formulas already wrapped so they keep their order in Arabic. */
  children: ReactNode;
  active?: boolean | undefined;
  /** Accept, edit, reject: only on the active one. */
  actions?: ReactNode;
  /** Set once decided. Undecided findings say nothing, so a list isn't a wall of "pending". */
  state?: ReactNode;
  onSelect?: (() => void) | undefined;
}

export function Finding({ kind, level, children, active, actions, state, onSelect }: FindingProps): ReactNode {
  return (
    <li className={active ? `${classes.finding} ${classes.findingActive}` : classes.finding} aria-current={active ? "true" : undefined}>
      <button type="button" className={classes.findingBody} onClick={onSelect}>
        <span className={classes.findingHead}>
          <span className={classes.findingKind}>{kind}</span>
          <Confidence level={level} />
        </span>
        <span className={classes.findingText}>{children}</span>
      </button>
      {actions ? <div className={classes.findingActions}>{actions}</div> : null}
      {state ? <p className={classes.findingState}>{state}</p> : null}
    </li>
  );
}

export function FindingList({ count, order, progress, bulkAction, children }: { count: ReactNode; order?: ReactNode; progress: number; bulkAction?: ReactNode; children: ReactNode }): ReactNode {
  const countId = useId();
  return (
    <div className={classes.pane}>
      <div className={classes.paneTools}>
        <div className={classes.paneCount}>
          <span id={countId}>{count}</span>
          {order ? <span className={classes.paneOrder}>{order}</span> : null}
        </div>
        <div className={classes.progress} role="progressbar" aria-labelledby={countId} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}>
          <i style={{ width: `${progress * 100}%` }} />
        </div>
        {bulkAction}
      </div>
      <ol>{children}</ol>
    </div>
  );
}

/** The review screen's frame: file and actions on top, then any notices, then the sheet and its findings. */
export function ReviewLayout({ file, actions, notices, tabs, sheet, legend, findings }: { file: ReactNode; actions?: ReactNode; notices?: ReactNode; tabs?: ReactNode; sheet: ReactNode; legend?: ReactNode; findings: ReactNode }): ReactNode {
  return (
    <div className={classes.review}>
      <header className={classes.top}>
        <h1 className={classes.file}>{file}</h1>
        {actions ? <div className={classes.topActions}>{actions}</div> : null}
      </header>
      {notices ? <div className={classes.notices}>{notices}</div> : null}
      <main id="main" className={classes.body} tabIndex={-1}>
        <div className={classes.sheetPane}>
          {tabs}
          <div className={classes.sheetArea}>{sheet}</div>
          {legend}
        </div>
        {findings}
      </main>
    </div>
  );
}

export function SheetTabs({ label, tabs, current, onSelect }: { label: string; tabs: string[]; current?: string | undefined; onSelect?: ((tab: string) => void) | undefined }): ReactNode {
  return (
    <nav className={classes.tabs} aria-label={label} dir="ltr">
      {tabs.map((tab) => (
        <button key={tab} type="button" className={classes.tab} aria-current={tab === current ? "true" : undefined} onClick={() => onSelect?.(tab)}>
          <bdi dir="auto">{tab}</bdi>
        </button>
      ))}
    </nav>
  );
}
