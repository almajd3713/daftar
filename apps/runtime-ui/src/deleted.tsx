/** What can still be brought back. A row opens the record's own page, which names it and restores it. */
import type { Entity } from "@daftar/spec/types";
import { Button, DateTimeText, EmptyState, LedgerTable, Page, Pager, RecordList, RecordRow, TextLink, useDaftar, useFrame, UserText, Waiting, type Column } from "@daftar/ui";
import { useEffect, type ReactNode } from "react";

import { useFetch, type DeletedList, type DeletedRecord } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { navigate } from "./router.js";
import { PAGE_SIZE } from "./views.js";
import { rangeOf, useWords } from "./words.js";

export function DeletedPage({ entity, page, onBack }: { entity: Entity; page: number; onBack: () => void }): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const key = entity.key;
  const { data, problem, loading, reload } = useFetch<DeletedList>(`/api/e/${encodeURIComponent(key)}/deleted?page=${page}&pageSize=${PAGE_SIZE}`);

  // Restoring the only record on the last page leaves that page empty, and the rest are on an earlier one.
  const emptied = data !== undefined && !data.rows.length && data.total > 0;
  useEffect(() => {
    if (emptied) navigate({ name: "deleted", entity: key, page: 1 }, { replace: true });
  }, [emptied, key]);

  const open = (row: DeletedRecord): void => navigate({ name: "record", entity: key, id: row.recordId, from: undefined });
  const nameOf = (row: DeletedRecord): ReactNode => (row.name ? <UserText>{row.name}</UserText> : "–");
  const chrome = (children: ReactNode): ReactNode => <Page title={t("deletedList")} subtitle={say(entity.label)} onBack={onBack}>{children}</Page>;

  if (!data) {
    return chrome(loading ? <Waiting>{t("deletedList")}</Waiting> : <><ProblemNotice problem={problem} /><Button onClick={reload}>{t("retry")}</Button></>);
  }
  if (data.total === 0) return chrome(<EmptyState title={t("deletedEmptyTitle")}>{t("deletedEmptyBody")}</EmptyState>);

  const last = Math.min(page * PAGE_SIZE, data.total);
  const pager = data.total > PAGE_SIZE ? (
    <Pager
      label={t("deletedList")}
      status={rangeOf((page - 1) * PAGE_SIZE + 1, last, data.total, locale)}
      previous={page > 1 ? <Button onClick={() => navigate({ name: "deleted", entity: key, page: page - 1 })}>{t("previous")}</Button> : undefined}
      next={last < data.total ? <Button onClick={() => navigate({ name: "deleted", entity: key, page: page + 1 })}>{t("next")}</Button> : undefined}
    />
  ) : null;

  if (narrow) {
    return chrome(
      <>
        <ProblemNotice problem={problem} />
        <RecordList titleHeading={t("deletedName")}>
          {data.rows.map((row) => (
            <RecordRow key={row.changeId} title={nameOf(row)} meta={<><DateTimeText value={row.at} /> · <UserText>{row.actor}</UserText></>} onClick={() => open(row)} />
          ))}
        </RecordList>
        {pager}
      </>,
    );
  }

  const columns: Column<DeletedRecord>[] = [
    { key: "name", header: t("deletedName"), cell: (row) => <TextLink onClick={() => open(row)}>{nameOf(row)}</TextLink> },
    { key: "at", header: t("deletedOn"), nowrap: true, cell: (row) => <DateTimeText value={row.at} /> },
    { key: "actor", header: t("deletedBy"), cell: (row) => <UserText>{row.actor}</UserText> },
  ];
  return chrome(
    <>
      <ProblemNotice problem={problem} />
      <LedgerTable caption={t("deletedList")} columns={columns} rows={data.rows} rowKey={(row) => row.changeId} />
      {pager}
    </>,
  );
}
