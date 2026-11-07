/** R-16: a spec's dashboard. The first figure leads, the rest are a short statement beside it, and charts follow. */
import type { Dashboard, Field, WidgetChart, WidgetKpi } from "@daftar/spec/types";
import { BarList, Button, currencyLabel, HeroFigure, LeadRow, LineChart, Page, Panel, PanelNote, Panels, Statement, StatementLine, todayIn, useDaftar, Waiting } from "@daftar/ui";
import type { ReactNode } from "react";

import { useFetchAll, type AggregateResult, type ListResult, type Meta } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { GroupLabel, OutputValue } from "./fields.js";
import { kindOf, precisionOf } from "./values.js";
import { barsInOrder, chartPrecision, heroText, kpiType, kpiValue, linePoints, MOST_BARS, widgetPath } from "./widgets.js";
import { topOf, useWords } from "./words.js";

interface Figure {
  widget: WidgetKpi;
  field: Field | undefined;
  value: unknown;
}

function Figures({ figures }: { figures: readonly Figure[] }): ReactNode {
  const { say, locale } = useDaftar();
  const [lead, ...others] = figures;
  if (!lead) return null;
  const type = kpiType(lead.widget, lead.field);
  const unit = type === "money" ? currencyLabel(locale) : type === "percent" ? "%" : undefined;
  return (
    <LeadRow>
      <HeroFigure label={say(lead.widget.label)} value={heroText(type, lead.value, locale, lead.field ? precisionOf(lead.field) : 0)} unit={unit} />
      {others.length ? (
        <Statement>
          {others.map(({ widget, field, value }) => (
            <StatementLine key={widget.key} label={say(widget.label)}>
              <OutputValue output={{ key: widget.key, label: widget.label, type: kpiType(widget, field) }} value={value} />
            </StatementLine>
          ))}
        </Statement>
      ) : null}
    </LeadRow>
  );
}

function Chart({ widget, field, measured, result }: { widget: WidgetChart; field: Field | undefined; measured: Field | undefined; result: AggregateResult }): ReactNode {
  const { say, locale } = useDaftar();
  const t = useWords();
  const money = widget.aggregate !== "count" && measured !== undefined && kindOf(measured) === "money";
  const title = say(widget.label);
  if (widget.type === "line") {
    const points = linePoints(result.groups, field, say, locale);
    if (!points.some((point) => point.value !== null)) return <Panel title={title}><PanelNote>{t("chartEmpty")}</PanelNote></Panel>;
    return (
      <Panel title={title}>
        <LineChart title={title} points={points} money={money} precision={chartPrecision(widget.aggregate, money, points.map((point) => point.value))} labelHeading={field ? say(field.label) : ""} valueHeading={money ? currencyLabel(locale) : title} />
      </Panel>
    );
  }
  const bars = barsInOrder(result.groups, field);
  // A bar's value has no currency of its own, so its heading says it once, as a column's would.
  const heading = money ? `${title} (${currencyLabel(locale)})` : title;
  if (!bars.length) return <Panel title={heading}><PanelNote>{t("chartEmpty")}</PanelNote></Panel>;
  const shown = bars.slice(0, MOST_BARS);
  return (
    <Panel title={heading}>
      <BarList
        items={shown.map((group) => ({ key: String(group.key), label: field ? <GroupLabel field={field} group={group} /> : String(group.key), value: group.value ?? 0 }))}
        precision={chartPrecision(widget.aggregate, money, bars.map((group) => group.value))}
      />
      {bars.length > shown.length || result.truncated ? <PanelNote>{topOf(shown.length, bars.length, result.truncated, locale)}</PanelNote> : null}
    </Panel>
  );
}

export function DashboardPage({ meta, dashboard }: { meta: Meta; dashboard: Dashboard }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const today = todayIn(meta.app.timezone);
  const { data, problem, loading, reload } = useFetchAll<unknown>(dashboard.widgets.map((widget) => widgetPath(widget, today)));
  const fieldOf = (entity: string, key: string | undefined): Field | undefined => (key ? meta.entities.find((item) => item.key === entity)?.fields.find((field) => field.key === key) : undefined);
  const page = (children: ReactNode): ReactNode => <Page title={say(dashboard.label)}>{children}</Page>;

  if (!data) return page(loading ? <Waiting>{say(dashboard.label)}</Waiting> : <><ProblemNotice problem={problem} /><Button onClick={reload}>{t("retry")}</Button></>);

  const figures = dashboard.widgets.flatMap((widget, index): Figure[] => (widget.type === "kpi" ? [{ widget, field: fieldOf(widget.entity, widget.field), value: kpiValue(widget, data[index] as ListResult) }] : []));
  const charts = dashboard.widgets.flatMap((widget, index): { widget: WidgetChart; result: AggregateResult }[] => (widget.type === "kpi" ? [] : [{ widget, result: data[index] as AggregateResult }]));
  return page(
    <>
      <Figures figures={figures} />
      {charts.length ? (
        <Panels>
          {charts.map(({ widget, result }) => (
            <Chart key={widget.key} widget={widget} field={fieldOf(widget.entity, widget.groupBy)} measured={fieldOf(widget.entity, widget.field)} result={result} />
          ))}
        </Panels>
      ) : null}
    </>,
  );
}
