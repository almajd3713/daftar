/** A list view: a ledger table on a PC, two-line rows on a phone. Same data, same order, same totals. */
import type { Entity, Field, ViewList } from "@daftar/spec/types";
import {
  Amount,
  Button,
  currencyLabel,
  EmptyState,
  FootRow,
  LedgerTable,
  Money,
  Page,
  Pager,
  PlusIcon,
  RecordList,
  RecordRow,
  SearchField,
  TextLink,
  todayIn,
  useDaftar,
  useFrame,
  UserText,
  ViewTabs,
  Waiting,
  type Column,
} from "@daftar/ui";
import { useEffect, useState, type ReactNode } from "react";

import { useFetch, type ListResult, type Meta, type Row } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { FieldValue } from "./fields.js";
import { navigate } from "./router.js";
import { isListView, listPath, PAGE_SIZE } from "./views.js";
import { isNumeric, kindOf, precisionOf } from "./values.js";
import { rangeOf, useWords } from "./words.js";

export const canDo = (meta: Meta, entity: string, action: string): boolean => meta.permissions.some((item) => item.entity === entity && item.actions.includes(action as never));

function SearchBox({ view, q }: { view: string; q: string }): ReactNode {
  const [text, setText] = useState(q);
  useEffect(() => {
    if (text === q) return undefined;
    // Wait for a pause in the typing. A shop's connection shouldn't carry a request per letter.
    const timer = setTimeout(() => navigate({ name: "view", view, q: text, page: 1 }, { replace: true }), 300);
    return () => clearTimeout(timer);
  }, [text, q, view]);
  return <SearchField value={text} onChange={(event) => setText(event.currentTarget.value)} />;
}

function fieldsOf(entity: Entity, keys: readonly string[]): Field[] {
  return keys.flatMap((key) => entity.fields.find((field) => field.key === key) ?? []);
}

export function ListPage({ meta, view, entity, q, page }: { meta: Meta; view: ViewList; entity: Entity; q: string; page: number }): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const path = listPath(view, { q, page, today: todayIn(meta.app.timezone) });
  const { data, problem, loading, reload } = useFetch<ListResult>(path);
  const editable = canDo(meta, entity.key, "update") && meta.forms.some((form) => form.entity === entity.key);
  const creatable = meta.forms.some((form) => form.entity === entity.key);
  const open = (row: Row): void => navigate({ name: "edit", entity: entity.key, id: row._id, from: view.key });
  const add = creatable ? <Button primary leftSection={<PlusIcon />} onClick={() => navigate({ name: "new", entity: entity.key, from: view.key })}>{t("add")}</Button> : undefined;
  const tabs = meta.views.filter(isListView).filter((item) => item.entity === entity.key).map((item) => ({ key: item.key, label: say(item.label), ...(item.key === view.key && data ? { count: data.total } : {}) }));
  const header = <ViewTabs label={say(entity.label)} views={tabs} current={view.key} tools={<SearchBox key={view.key} view={view.key} q={q} />} onSelect={(key) => navigate({ name: "view", view: key, q: "", page: 1 })} />;
  const fields = fieldsOf(entity, view.columns);
  const totals = data?.totals ?? {};
  const totalField = fieldsOf(entity, view.totals ?? [])[0];
  const totalValue = totalField ? totals[totalField.key] : undefined;
  const foot = narrow && (add || totalField) ? (
    <FootRow totalLabel={totalField ? say(totalField.label) : undefined} total={totalField && typeof totalValue === "number" ? <Money value={totalValue} precision={precisionOf(totalField)} /> : undefined}>{add}</FootRow>
  ) : undefined;
  const pageChrome = (children: ReactNode): ReactNode => <Page title={say(entity.label)} actions={add} foot={foot} closing={Boolean(totalField)}>{children}</Page>;

  if (!data) {
    return pageChrome(<>{header}{loading ? <Waiting>{say(view.label)}</Waiting> : <><ProblemNotice problem={problem} /><Button onClick={reload}>{t("retry")}</Button></>}</>);
  }
  if (data.total === 0) {
    const searched = Boolean(q);
    return pageChrome(
      <>
        {header}
        <EmptyState title={searched || view.filters?.length ? t("noResultsTitle") : t("emptyTitle")}>
          {searched || view.filters?.length ? t("noResultsBody") : creatable ? t("emptyBody") : t("emptyReadOnly")}
        </EmptyState>
      </>,
    );
  }

  const last = Math.min(page * PAGE_SIZE, data.total);
  const pager = data.total > PAGE_SIZE ? (
    <Pager
      label={say(view.label)}
      status={rangeOf((page - 1) * PAGE_SIZE + 1, last, data.total, locale)}
      previous={page > 1 ? <Button onClick={() => navigate({ name: "view", view: view.key, q, page: page - 1 })}>{t("previous")}</Button> : undefined}
      next={last < data.total ? <Button onClick={() => navigate({ name: "view", view: view.key, q, page: page + 1 })}>{t("next")}</Button> : undefined}
    />
  ) : null;

  if (narrow) {
    const titleField = entity.fields.find((field) => field.key === entity.titleField);
    const amount = fields.find(isNumeric);
    const status = fields.find((field) => kindOf(field) === "choice");
    const date = fields.find((field) => kindOf(field) === "date");
    return pageChrome(
      <>
        {header}
        <ProblemNotice problem={problem} />
        <RecordList titleHeading={titleField ? say(titleField.label) : undefined} amountHeading={amount ? `${say(amount.label)}${kindOf(amount) === "money" ? ` (${currencyLabel(locale)})` : ""}` : undefined}>
          {data.rows.map((row) => (
            <RecordRow
              key={row._id}
              title={titleField ? <FieldValue field={titleField} row={row} /> : <UserText>{row._name}</UserText>}
              amount={amount ? <FieldValue field={amount} row={row} /> : undefined}
              meta={<>{row._name !== row[entity.titleField] ? <UserText>{row._name}</UserText> : null}{date && row[date.key] ? <> · <FieldValue field={date} row={row} /></> : null}</>}
              status={status ? <FieldValue field={status} row={row} /> : undefined}
              onClick={editable ? () => open(row) : undefined}
            />
          ))}
        </RecordList>
        {pager}
      </>,
    );
  }

  const columns: Column<Row>[] = fields.map((field, index) => ({
    key: field.key,
    header: say(field.label),
    ...(kindOf(field) === "money" ? { unit: currencyLabel(locale) } : {}),
    numeric: isNumeric(field),
    nowrap: kindOf(field) === "date",
    cell: (row: Row) => (index === 0 && editable ? <TextLink onClick={() => open(row)}><FieldValue field={field} row={row} /></TextLink> : <FieldValue field={field} row={row} />),
  }));
  const totalCells = view.totals?.length ? Object.fromEntries(fieldsOf(entity, view.totals).map((field) => [field.key, <Amount key={field.key} value={totals[field.key] ?? 0} precision={precisionOf(field)} showZero />])) : undefined;
  return pageChrome(
    <>
      {header}
      <ProblemNotice problem={problem} />
      <LedgerTable caption={say(view.label)} columns={columns} rows={data.rows} rowKey={(row) => row._id} totals={totalCells} totalLabel={t("total")} />
      {pager}
    </>,
  );
}
