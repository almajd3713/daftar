/** A list view: a ledger table on a PC, two-line rows on a phone. Same data, same order, same totals. */
import type { Entity, Field, ViewList } from "@daftar/spec/types";
import {
  Amount,
  Button,
  currencyLabel,
  EmptyState,
  FootRow,
  Gutter,
  LastActions,
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

import { canDo, useFetch, type ListResult, type Meta, type Row } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { FieldValue, RecordTitle } from "./fields.js";
import { navigate } from "./router.js";
import { listPath, PAGE_SIZE, viewsOf } from "./views.js";
import { isNumeric, kindOf, precisionOf } from "./values.js";
import { rangeOf, useWords } from "./words.js";

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

/** The page's add button, for a person who has a form to add with. */
export function useAddButton(meta: Meta, entity: Entity, from: string): ReactNode {
  const t = useWords();
  if (!meta.forms.some((form) => form.entity === entity.key)) return undefined;
  return <Button primary leftSection={<PlusIcon />} onClick={() => navigate({ name: "new", entity: entity.key, from })}>{t("add")}</Button>;
}

/** The way to what's been deleted, under whatever shows an entity's records, for those who could restore it. */
export function DeletedLink({ meta, entity }: { meta: Meta; entity: Entity }): ReactNode {
  const t = useWords();
  if (!canDo(meta, entity.key, "revert")) return null;
  return (
    <Gutter>
      <LastActions><TextLink onClick={() => navigate({ name: "deleted", entity: entity.key, page: 1 })}>{t("deletedList")}</TextLink></LastActions>
    </Gutter>
  );
}

export function ListPage({ meta, view, entity, q, page }: { meta: Meta; view: ViewList; entity: Entity; q: string; page: number }): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const path = listPath(view, { q, page, today: todayIn(meta.app.timezone) });
  const { data, problem, loading, reload } = useFetch<ListResult>(path);
  const creatable = meta.forms.some((form) => form.entity === entity.key);
  const open = (row: Row): void => navigate({ name: "record", entity: entity.key, id: row._id, from: view.key });
  const add = useAddButton(meta, entity, view.key);
  const tabs = viewsOf(meta, entity.key).map((item) => ({ key: item.key, label: say(item.label), ...(item.key === view.key && data ? { count: data.total } : {}) }));
  const header = <ViewTabs label={say(entity.label)} views={tabs} current={view.key} tools={<SearchBox key={view.key} view={view.key} q={q} />} onSelect={(key) => navigate({ name: "view", view: key, q: "", page: 1 })} />;
  const fields = fieldsOf(entity, view.columns);
  const totals = data?.totals ?? {};
  const totalField = fieldsOf(entity, view.totals ?? [])[0];
  const totalValue = totalField ? totals[totalField.key] : undefined;
  const foot = narrow && (add || totalField) ? (
    <FootRow totalLabel={totalField ? say(totalField.label) : undefined} total={totalField && typeof totalValue === "number" ? <Money value={totalValue} precision={precisionOf(totalField)} /> : undefined}>{add}</FootRow>
  ) : undefined;
  // The link waits for the list, or it would jump down the page as the rows arrive.
  const pageChrome = (children: ReactNode): ReactNode => <Page title={say(entity.label)} actions={add} foot={foot} closing={Boolean(totalField)}>{children}{data ? <DeletedLink meta={meta} entity={entity} /> : null}</Page>;

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
          {data.rows.map((row) => {
            const name = row._name !== row[entity.titleField] ? <UserText>{row._name}</UserText> : null;
            const when = date && row[date.key] ? <FieldValue field={date} row={row} /> : null;
            return (
              <RecordRow
                key={row._id}
                title={<RecordTitle entity={entity} row={row} />}
                amount={amount ? <FieldValue field={amount} row={row} /> : undefined}
                meta={<>{name}{name && when ? " · " : null}{when}</>}
                status={status ? <FieldValue field={status} row={row} /> : undefined}
                onClick={() => open(row)}
              />
            );
          })}
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
    cell: (row: Row) => (index === 0 ? <TextLink onClick={() => open(row)}><FieldValue field={field} row={row} /></TextLink> : <FieldValue field={field} row={row} />),
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
