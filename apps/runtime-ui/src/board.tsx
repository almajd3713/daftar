/**
 * R-20: a workflow's records by state. Columns on a PC, one state at a time on a phone. Moving a card asks the server,
 * which judges it and says why not. The card stays where it is until the server has answered.
 */
import type { Entity, Field, ViewBoard, Workflow, WorkflowTransition } from "@daftar/spec/types";
import {
  BoardCard,
  BoardColumn,
  BoardColumns,
  Button,
  CodeText,
  EmptyState,
  FootRow,
  Gutter,
  Notice,
  Page,
  StatusChip,
  TextLink,
  todayIn,
  useDaftar,
  useFrame,
  UserText,
  ViewTabs,
  Waiting,
} from "@daftar/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { call, canDo, problemOf, useFetchAll, type ListResult, type Meta, type Problem, type Row } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { FieldValue } from "./fields.js";
import { DeletedLink, useAddButton } from "./list.js";
import { navigate } from "./router.js";
import { boardPath, isListView, viewsOf } from "./views.js";
import { fieldsToCheck, offeredSteps, stepBetween } from "./workflow.js";
import { fieldsToLookAt, noStepBetween, refusedOf, seeAllOf, useWords, withColon } from "./words.js";

const STATE_TAB = "state:";

const cardId = (row: Row): string => `card-${row._id}`;

const hasValue = (row: Row, field: Field): boolean => Boolean(row._errors?.[field.key]) || (row[field.key] !== null && row[field.key] !== undefined && row[field.key] !== "");

interface Refusal {
  title: string;
  reason: ReactNode;
}

interface CardProps {
  entity: Entity;
  fields: readonly Field[];
  row: Row;
  step: WorkflowTransition | undefined;
  busy: boolean;
  blocked: boolean;
  refusal: Refusal | undefined;
  onOpen: () => void;
  onStep: (step: WorkflowTransition) => void;
  onDragStart: (() => void) | undefined;
}

function Card({ entity, fields, row, step, busy, blocked, refusal, onOpen, onStep, onDragStart }: CardProps): ReactNode {
  const { say, locale } = useDaftar();
  const [first, second, ...rest] = fields;
  return (
    <BoardCard
      // A spec lists what a card shows, in order: what it is, then who it's for, then the rest with their names.
      title={<TextLink id={cardId(row)} onClick={onOpen}>{first && hasValue(row, first) ? <FieldValue field={first} row={row} showZero /> : <UserText>{row._name}</UserText>}</TextLink>}
      number={entity.naming.type === "autonumber" ? <CodeText>{row._name}</CodeText> : undefined}
      subtitle={second && hasValue(row, second) ? <FieldValue field={second} row={row} showZero /> : undefined}
      meta={rest.some((field) => hasValue(row, field)) ? rest.filter((field) => hasValue(row, field)).map((field) => <span key={field.key}>{withColon(say(field.label), locale)} <FieldValue field={field} row={row} showZero /></span>) : undefined}
      action={step ? <Button loading={busy} disabled={blocked} onClick={() => onStep(step)}>{say(step.label)}</Button> : undefined}
      refusal={refusal}
      onDragStart={onDragStart}
    />
  );
}

export interface BoardPageProps {
  meta: Meta;
  view: ViewBoard;
  workflow: Workflow;
  entity: Entity;
  /** The state a phone shows, from the address. */
  state: string | undefined;
}

export function BoardPage({ meta, view, workflow, entity, state }: BoardPageProps): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const today = todayIn(meta.app.timezone);
  const { data, problem, loading, reload } = useFetchAll<ListResult>(workflow.states.map((item) => boardPath(view, workflow, item.key, today)));
  const add = useAddButton(meta, entity, view.key);
  const [busy, setBusy] = useState<string>();
  const [failure, setFailure] = useState<Problem>();
  const [refusals, setRefusals] = useState<Readonly<Record<string, Refusal>>>({});
  const [moved, setMoved] = useState<{ name: string; state: string }>();
  const dragged = useRef<Row>(undefined);
  // The button pressed goes when its card moves, so focus follows the card, or the page if the card has left this tab.
  const focusAfterMove = useRef<string>(undefined);

  useEffect(() => {
    if (!data || !focusAfterMove.current) return;
    const card = document.getElementById(focusAfterMove.current);
    focusAfterMove.current = undefined;
    (card ?? document.getElementById("main"))?.focus();
  }, [data]);

  const canMove = canDo(meta, entity.key, "update");
  const stateOf = (key: string): string => {
    const found = workflow.states.find((item) => item.key === key);
    return found ? say(found.label) : key;
  };
  const refuse = (row: Row, refusal: Refusal): void => setRefusals((current) => ({ ...current, [row._id]: refusal }));

  const take = (row: Row, step: WorkflowTransition, focus: boolean): void => {
    if (busy) return;
    setBusy(row._id);
    setFailure(undefined);
    setMoved(undefined);
    setRefusals((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== row._id)));
    call("POST", `/api/e/${encodeURIComponent(entity.key)}/${encodeURIComponent(row._id)}/transition`, { action: step.key })
      .then(
        () => {
          // In the words on the card. Its number is only what the record is called when it has nothing better.
          const title = view.cardFields[0] ? row[view.cardFields[0]] : undefined;
          setMoved({ name: typeof title === "string" && title ? title : row._name, state: step.to });
          if (focus) focusAfterMove.current = cardId(row);
          reload();
        },
        (error: unknown) => {
          const found = problemOf(error);
          if (found.kind !== "reason") {
            setFailure(found);
            return;
          }
          // Someone else may have moved the record meanwhile. Then the record's values aren't what stopped this.
          const stillThere = (step.from as readonly string[]).includes(String(row[workflow.stateField]));
          const look = stillThere ? fieldsToCheck(entity, step).map((field) => say(field.label)) : [];
          refuse(row, { title: refusedOf(say(step.label), locale), reason: <>{say(found.reason)}{look.length ? <><br />{fieldsToLookAt(look, locale)}</> : null}</> });
          // What was refused may be out of date: show the board as it now stands.
          reload();
        },
      )
      .finally(() => setBusy(undefined));
  };

  const drop = (target: string): void => {
    const row = dragged.current;
    dragged.current = undefined;
    const from = String(row?.[workflow.stateField]);
    if (!row || from === target) return;
    const step = stepBetween(workflow, from, target, meta.user.role);
    if (step) {
      take(row, step, false);
      return;
    }
    const options = offeredSteps(workflow, from, meta.user.role).map((item) => stateOf(item.to));
    setMoved(undefined);
    refuse(row, { title: refusedOf(stateOf(target), locale), reason: noStepBetween(stateOf(from), stateOf(target), options, locale) });
  };

  const fields = view.cardFields.flatMap((key) => entity.fields.find((field) => field.key === key) ?? []);
  const lists = viewsOf(meta, entity.key).filter(isListView);
  const others = viewsOf(meta, entity.key).filter((item) => item.key !== view.key);
  const cardsOf = (key: string): readonly Row[] => data?.[workflow.states.findIndex((item) => item.key === key)]?.rows ?? [];
  const countOf = (key: string): number => data?.[workflow.states.findIndex((item) => item.key === key)]?.total ?? 0;
  const anything = workflow.states.some((item) => countOf(item.key) > 0);

  const cards = (key: string): ReactNode => cardsOf(key).map((row) => (
    <Card
      key={row._id}
      entity={entity}
      fields={fields}
      row={row}
      step={canMove ? offeredSteps(workflow, key, meta.user.role)[0] : undefined}
      busy={busy === row._id}
      blocked={Boolean(busy)}
      refusal={refusals[row._id]}
      onOpen={() => navigate({ name: "record", entity: entity.key, id: row._id, from: view.key })}
      onStep={(step) => take(row, step, true)}
      onDragStart={canMove && !narrow ? () => { dragged.current = row; } : undefined}
    />
  ));

  const seeAll = (key: string): ReactNode => {
    const list = lists[0];
    if (!list || countOf(key) <= cardsOf(key).length) return null;
    return <TextLink onClick={() => navigate({ name: "view", view: list.key, q: "", page: 1 })}>{seeAllOf(countOf(key), locale)}</TextLink>;
  };

  // A phone opens on the first state with something in it, and the address keeps whichever a person chose.
  const shown = workflow.states.find((item) => item.key === state)?.key ?? workflow.states.find((item) => countOf(item.key) > 0)?.key ?? workflow.states[0]?.key ?? "";
  const tabs = narrow
    ? <ViewTabs
        label={say(entity.label)}
        views={[
          ...workflow.states.map((item) => ({ key: `${STATE_TAB}${item.key}`, label: say(item.label), ...(data ? { count: countOf(item.key) } : {}) })),
          ...others.map((item) => ({ key: item.key, label: say(item.label) })),
        ]}
        current={`${STATE_TAB}${shown}`}
        onSelect={(key) => {
          if (key.startsWith(STATE_TAB)) navigate({ name: "view", view: view.key, q: "", page: 1, state: key.slice(STATE_TAB.length) }, { replace: true });
          else navigate({ name: "view", view: key, q: "", page: 1 });
        }}
      />
    : <ViewTabs
        label={say(entity.label)}
        views={viewsOf(meta, entity.key).map((item) => ({ key: item.key, label: say(item.label) }))}
        current={view.key}
        onSelect={(key) => navigate({ name: "view", view: key, q: "", page: 1 })}
      />;

  const notices = failure || moved ? (
    <Gutter>
      <ProblemNotice problem={failure} />
      {moved ? <Notice title={withColon(moved.name, locale) + " " + stateOf(moved.state)} /> : null}
    </Gutter>
  ) : null;

  const chrome = (children: ReactNode): ReactNode => (
    <Page title={say(entity.label)} actions={add} foot={narrow && add ? <FootRow>{add}</FootRow> : undefined}>
      {tabs}
      {children}
      {data ? <DeletedLink meta={meta} entity={entity} /> : null}
    </Page>
  );

  if (!data) return chrome(loading ? <Waiting>{say(view.label)}</Waiting> : <><ProblemNotice problem={problem} /><Button onClick={reload}>{t("retry")}</Button></>);
  if (!anything && !moved) return chrome(<EmptyState title={view.filters?.length ? t("noResultsTitle") : t("emptyTitle")}>{view.filters?.length ? t("noResultsBody") : add ? t("emptyBody") : t("emptyReadOnly")}</EmptyState>);
  if (narrow) {
    return chrome(
      <>
        {notices}
        {countOf(shown) ? cards(shown) : <EmptyState title={t("boardStateEmpty")} />}
        {seeAll(shown) ? <Gutter>{seeAll(shown)}</Gutter> : null}
      </>,
    );
  }
  return chrome(
    <>
      {notices}
      <BoardColumns>
        {workflow.states.map((item) => (
          <BoardColumn key={item.key} heading={<StatusChip color={item.colour} label={say(item.label)} />} count={countOf(item.key)} onDropCard={canMove ? () => drop(item.key) : undefined}>
            {cards(item.key)}
            {seeAll(item.key)}
          </BoardColumn>
        ))}
      </BoardColumns>
    </>,
  );
}
