/**
 * The two charts R-16's dashboards need, drawn here rather than through @mantine/charts: Recharts costs far
 * more than these screens' phones should download for two shapes, and the axis has to follow the reading
 * direction. Every chart has its numbers one tap away, so nothing depends on seeing or hovering.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { chartScale, labelledPoints, labelWidth, lineRuns, pointPositions } from "./chart-scale.js";
import { formatCompact, formatMoney, formatNumber } from "./format.js";
import { useDaftar, useFrame } from "./provider.js";
import classes from "./charts.module.css";

export interface LinePoint {
  key: string;
  /** Under the axis: a month's name, or a short date. */
  label: string;
  /** Null when there's nothing to plot, such as a sum over blanks. The line breaks there. */
  value: number | null;
  /** Its place in time, such as `Date.parse(date)`, when the points aren't evenly spaced. All points or none. */
  at?: number | undefined;
}

const WIDE = { width: 600, height: 240 };
const NARROW = { width: 328, height: 200 };

/** About a month of days. Past this, a tab stop per point is a wall: the numbers are one tap away in the details. */
const MOST_FOCUSABLE_POINTS = 31;

export interface LineChartProps {
  /** Named for screen readers, and shown above the chart by the caller. */
  title: string;
  points: LinePoint[];
  /** A column title for the numbers underneath. */
  valueHeading: ReactNode;
  labelHeading: ReactNode;
  /** Says the currency when a value is shown alone. Leave it off for a count. */
  money?: boolean | undefined;
  /** Decimal places: 2 for money, otherwise 0. */
  precision?: number | undefined;
}

/** One series over time. Time runs with the reading direction, and only the last point has its value on it. */
export function LineChart({ title, points, valueHeading, labelHeading, money, precision = money ? 2 : 0 }: LineChartProps): ReactNode {
  const { locale, dir, ui } = useDaftar();
  const { narrow } = useFrame();
  const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null);
  const figure = useRef<HTMLElement>(null);
  const [measured, setMeasured] = useState<number>();
  // Drawn in real pixels for the width it's been given. A fixed coordinate system would scale its text with the chart,
  // past the type scale in a wide panel and below 13 px in a narrow one, where no check on the CSS could see it.
  useLayoutEffect(() => {
    const element = figure.current;
    if (!element) return undefined;
    setMeasured(Math.round(element.getBoundingClientRect().width));
    const observer = new ResizeObserver(() => setMeasured(Math.round(element.getBoundingClientRect().width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const { width: fallback, height } = narrow ? NARROW : WIDE;
  const width = measured || fallback;
  const rtl = dir === "rtl";
  const padStart = rtl ? 68 : 48;
  const padEnd = 20;
  const padTop = 28;
  const padBottom = 28;
  const plot = width - padStart - padEnd;
  const values = points.map((point) => point.value);
  const known = values.filter((value) => value !== null);
  const { top, bottom, ticks } = chartScale(Math.max(...known, 0), Math.min(...known, 0));
  const places = pointPositions(points.map((point) => point.at));
  const xs = places.map((place) => (rtl ? width - padStart - place * plot : padStart + place * plot));
  const xOf = (index: number): number => xs[index] ?? padStart;
  const y = (value: number): number => padTop + ((height - padTop - padBottom) * (top - value)) / (top - bottom);
  const runs = lineRuns(values);
  const yOf = (index: number): number => y(values[index] ?? 0);
  const segment = (run: number[]): string => run.map((index, order) => `${order ? "L" : "M"}${xOf(index).toFixed(1)} ${yOf(index).toFixed(1)}`).join(" ");
  // A lone point between gaps has no line of its own, so it gets a dot from the round cap.
  const path = runs.map((run) => (run.length === 1 ? `${segment(run)} h0` : segment(run))).join(" ");
  const area = runs.filter((run) => run.length > 1).map((run) => `${segment(run)} L${xOf(run.at(-1) ?? 0).toFixed(1)} ${y(0)} L${xOf(run[0] ?? 0).toFixed(1)} ${y(0)} Z`).join(" ");
  const lastIndex = runs.at(-1)?.at(-1) ?? -1;
  const lastValue = values[lastIndex] ?? null;
  const labelled = labelledPoints(xs, points.map((point) => labelWidth(point.label)));
  const focusable = points.length <= MOST_FOCUSABLE_POINTS;
  const show = (value: number): string => (money ? formatMoney(value, locale, precision) : formatNumber(value, locale, precision));
  if (lastValue === null) return null;
  return (
    <figure ref={figure} className={classes.figure}>
      <svg className={classes.chart} viewBox={`0 0 ${width} ${height}`} role="group" aria-label={title}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={rtl ? padEnd : padStart} x2={rtl ? width - padStart : width - padEnd} y1={y(tick)} y2={y(tick)} className={classes.gridLine} />
            <text x={rtl ? width - padStart + 8 : padStart - 8} y={y(tick) + 4} textAnchor={rtl ? "start" : "end"}>
              {tick === 0 ? "0" : formatCompact(tick, locale)}
            </text>
          </g>
        ))}
        <path d={area} className={classes.area} />
        <path d={path} className={classes.line} />
        {points.map((point, index) =>
          labelled.has(index) ? (
            <text key={point.key} x={xOf(index)} y={height - 8} textAnchor="middle">
              {point.label}
            </text>
          ) : null,
        )}
        <circle cx={xOf(lastIndex)} cy={y(lastValue)} r="4" className={classes.dot} />
        <text className={classes.endLabel} x={xOf(lastIndex)} y={y(lastValue) - 12} textAnchor={rtl ? "start" : "end"}>
          {formatNumber(lastValue, locale, precision)}
        </text>
        {points.map((point, index) => {
          if (point.value === null) return null;
          const text = `${point.label}: ${show(point.value)}`;
          const reveal = (): void => setHover({ text, x: xOf(index), y: y(point.value ?? 0) });
          // Each point owns the ground halfway to its neighbours, wherever they are.
          const before = index > 0 ? (xOf(index - 1) + xOf(index)) / 2 : xOf(index) + (rtl ? 12 : -12);
          const after = index < points.length - 1 ? (xOf(index) + xOf(index + 1)) / 2 : xOf(index) + (rtl ? -12 : 12);
          return (
            <rect
              key={point.key}
              className={classes.hit}
              x={Math.min(before, after)}
              y={padTop}
              width={Math.max(Math.abs(after - before), 1)}
              height={height - padTop - padBottom}
              {...(focusable ? { tabIndex: 0, role: "img", "aria-label": text, onFocus: reveal, onBlur: () => setHover(null) } : { "aria-hidden": true })}
              onPointerEnter={reveal}
              onPointerLeave={() => setHover(null)}
            />
          );
        })}
      </svg>
      {hover ? (
        <div className={classes.tip} style={{ left: `${(hover.x / width) * 100}%`, top: `${(hover.y / height) * 100}%` }} role="status">
          <bdi>{hover.text}</bdi>
        </div>
      ) : null}
      <details className={classes.numbers}>
        <summary>{ui("seeNumbers")}</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{labelHeading}</th>
              <th scope="col" className={classes.numeric}>
                {valueHeading}
              </th>
            </tr>
          </thead>
          <tbody>
            {points.map((point) => (
              <tr key={point.key}>
                <td>{point.label}</td>
                <td className={classes.numeric}>
                  <bdi dir="ltr">{point.value === null ? "–" : formatNumber(point.value, locale, precision)}</bdi>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

export interface BarItem {
  key: string;
  label: ReactNode;
  value: number;
  /** For precise text, when `label` isn't plain. */
  description?: string | undefined;
}

/** Ranked bars in one colour. The label is the identity, the value sits at the bar's tip. */
export function BarList({ items, precision = 0 }: { items: BarItem[]; precision?: number }): ReactNode {
  const { locale } = useDaftar();
  const max = Math.max(...items.map((item) => item.value), 1);
  const texts = items.map((item) => formatNumber(item.value, locale, precision));
  // Room for the longest value, the same on every row. Taken from each bar, a long value would squeeze its bar and
  // leave two different amounts looking the same.
  const room = `${Math.max(...texts.map((text) => text.length), 1)}ch - var(--space-2)`;
  return (
    <ul className={classes.bars}>
      {items.map((item, index) => (
        <li key={item.key} className={classes.bar}>
          <span>{item.label}</span>
          <span className={classes.track}>
            <span className={classes.fill} style={{ width: `calc((100% - ${room}) * ${Math.max(item.value, 0) / max})` }} />
            <span className={classes.value}>{texts[index]}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
