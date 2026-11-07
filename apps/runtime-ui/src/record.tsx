/** One record: its values, the steps its workflow offers, its history, and what can be undone. */
import type { Entity, Field, FieldChild, WorkflowTransition } from "@daftar/spec/types";
import {
  Button,
  Change,
  CodeText,
  DateTimeText,
  Fact,
  FactList,
  FootRow,
  Gutter,
  HistoryList,
  LastActions,
  Notice,
  Page,
  SectionHeading,
  Statement,
  StatementLine,
  StateLine,
  StatusChip,
  TextLink,
  TwoColumns,
  useDaftar,
  useFrame,
  UserText,
  Waiting,
  type Label,
} from "@daftar/ui";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { call, canDo, problemOf, useFetch, type AuditChange, type ListResult, type Meta, type Problem, type Row } from "./api.js";
import { MissingPage, ProblemNotice } from "./auth.js";
import { FieldValue, PastValue, RecordTitle } from "./fields.js";
import { canUndo, deletionOf, isRestoration, linkPath, linksIn, splitChanges } from "./history.js";
import { navigate } from "./router.js";
import { isListView, PAGE_SIZE } from "./views.js";
import { fieldsToLookAt, rangeOf, refusedOf, useWords, withColon, type Word } from "./words.js";
import { fieldsToCheck, offeredSteps, workflowOf } from "./workflow.js";

const DELETE_BUTTON = "delete-record";

const SOURCES: Record<string, Word> = { ui: "sourceUi", workflow: "sourceWorkflow", import: "sourceImport", system: "sourceSystem" };

/** History holds a link's id. Each name is asked for once, and a record since deleted simply has none. */
function useLinkNames(entity: Entity, changes: readonly AuditChange[]): ReadonlyMap<string, string> {
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  const wanted = linksIn(entity, changes).join(" ");
  useEffect(() => {
    if (!wanted) return undefined;
    let current = true;
    const ask = async (path: string): Promise<[string, string] | null> => {
      try {
        return [path, (await call<Row>("GET", `/api/e/${path}`))._name];
      } catch {
        return null;
      }
    };
    void Promise.all(wanted.split(" ").map(ask)).then((found) => {
      if (current) setNames(new Map(found.filter((item) => item !== null)));
    });
    return () => {
      current = false;
    };
  }, [wanted]);
  return names;
}

interface HistoryProps {
  meta: Meta;
  entity: Entity;
  changes: AuditChange[] | undefined;
  problem: Problem | undefined;
  canRevert: boolean;
  onUndo: (change: AuditChange) => void;
}

function RecordHistory({ meta, entity, changes, problem, canRevert, onUndo }: HistoryProps): ReactNode {
  const { say, dir, locale } = useDaftar();
  const t = useWords();
  const names = useLinkNames(entity, changes ?? []);
  const arrow = dir === "rtl" ? "←" : "→";
  // The server answers 404 for a record with no history lines, and that doesn't mean the record is missing.
  if (!changes?.length) {
    return (
      <section>
        <SectionHeading ruled>{t("history")}</SectionHeading>
        {problem?.kind === "missing" || changes ? <p>{t("historyEmpty")}</p> : problem ? <ProblemNotice problem={problem} /> : <Waiting>{t("history")}</Waiting>}
      </section>
    );
  }
  const linkLabel = (field: Field, id: unknown): string | undefined => (field.type === "link" && typeof id === "string" ? names.get(linkPath(field.target, id)) : undefined);
  const describe = (change: AuditChange): ReactNode => {
    if (change.op === "create") return <p>{t("created")}</p>;
    if (change.op === "delete") return <p>{t("deleted")}</p>;
    if (isRestoration(change, changes)) return <p>{t("restored")}</p>;
    const { shown, hidden } = splitChanges(entity, change);
    return (
      <>
        {change.op === "revert" ? <p>{t("undoLine")}</p> : null}
        {shown.map(({ field, from, to }) => (
          <Change
            key={field.key}
            label={withColon(say(field.label), locale)}
            from={<PastValue field={field} value={from} linkLabel={linkLabel(field, from)} />}
            to={<PastValue field={field} value={to} linkLabel={linkLabel(field, to)} />}
            arrow={arrow}
          />
        ))}
        {hidden ? <p>{t("hiddenChanged")}</p> : null}
      </>
    );
  };
  return (
    <HistoryList
      title={t("history")}
      entries={changes.map((change) => {
        const source = SOURCES[change.source];
        return {
          key: change.id,
          meta: (
            <>
              <DateTimeText value={change.at} timeZone={meta.app.timezone} /> · <UserText>{change.actor}</UserText> · {source ? t(source) : <UserText>{change.source}</UserText>}
              {change.revertedBy ? <> · {t("undone")}</> : null}
            </>
          ),
          changes: describe(change),
          action: canRevert && canUndo(change) ? <TextLink onClick={() => onUndo(change)}>{t("undo")}</TextLink> : undefined,
        };
      })}
    />
  );
}

/** A link's value leads to the record it names. */
function FactValue({ field, row }: { field: Field; row: Row }): ReactNode {
  const value = row[field.key];
  if (!row._errors?.[field.key] && (value === null || value === undefined || value === "")) return "–";
  const label = row._labels?.[field.key];
  if (field.type === "link" && label && typeof value === "string") {
    return <TextLink onClick={() => navigate({ name: "record", entity: field.target, id: value, from: undefined })}><UserText>{label}</UserText></TextLink>;
  }
  return <FieldValue field={field} row={row} showZero />;
}

/** The records pointing at this one, such as a class's students. A person doesn't type these: each has its own page. */
function ChildRecords({ meta, field, parent }: { meta: Meta; field: FieldChild; parent: string }): ReactNode {
  const { say, locale } = useDaftar();
  const t = useWords();
  const target = meta.entities.find((item) => item.key === field.target);
  // The server refuses a filter on a field this person can't see.
  const readable = target?.fields.some((item) => item.key === field.via);
  const { data, problem } = useFetch<ListResult>(readable ? `/api/e/${encodeURIComponent(field.target)}?filter.${encodeURIComponent(field.via)}.eq=${encodeURIComponent(parent)}&pageSize=${PAGE_SIZE}` : null);
  if (!target || !readable) return null;
  if (!data) {
    return <Statement title={say(field.label)}>{problem ? <ProblemNotice problem={problem} /> : <Waiting>{say(field.label)}</Waiting>}</Statement>;
  }
  // One more thing to tell them apart by: the first column of its list that this page doesn't already say.
  const view = meta.views.filter(isListView).find((item) => item.entity === target.key);
  const detail = view?.columns.flatMap((key) => target.fields.find((item) => item.key === key) ?? []).find((item) => item.key !== target.titleField && item.key !== field.via);
  return (
    <Statement title={`${say(field.label)} (${data.total})`}>
      {data.rows.length ? null : <StatementLine label={t("none")}>{null}</StatementLine>}
      {data.rows.map((row) => (
        <StatementLine key={row._id} label={<TextLink onClick={() => navigate({ name: "record", entity: target.key, id: row._id, from: undefined })}><RecordTitle entity={target} row={row} /></TextLink>}>
          {detail ? <FieldValue field={detail} row={row} /> : null}
        </StatementLine>
      ))}
      {data.total > data.rows.length ? <StatementLine label={rangeOf(1, data.rows.length, data.total, locale)}>{null}</StatementLine> : null}
    </Statement>
  );
}

/** Deleting asks first, and offers keeping the record as the easy answer. */
function DeleteRecord({ undoable, busy, onDelete }: { undoable: boolean; busy: boolean; onDelete: () => void }): ReactNode {
  const t = useWords();
  const [asking, setAsking] = useState(false);
  const asked = useRef(false);
  useEffect(() => {
    // Answering no removes the button that had the focus, so it goes back to where the person started.
    if (asked.current && !asking) document.getElementById(DELETE_BUTTON)?.focus();
    asked.current = asking;
  }, [asking]);
  if (!asking) return <LastActions><Button id={DELETE_BUTTON} onClick={() => setAsking(true)}>{t("delete")}</Button></LastActions>;
  return (
    <LastActions>
      <Notice
        title={t("deleteQuestion")}
        actions={
          <>
            {/* It takes the focus from the button it replaced, and keeping the record is the safe answer. */}
            <Button autoFocus onClick={() => setAsking(false)}>{t("deleteNo")}</Button>
            <Button loading={busy} onClick={onDelete}>{t("deleteYes")}</Button>
          </>
        }
      >
        {t(undoable ? "deleteUndoable" : "deleteFinal")}
      </Notice>
    </LastActions>
  );
}

interface Refusal {
  step: WorkflowTransition;
  reason: Label;
}

/** Why a step didn't go through, in the server's words, and where to look if its condition wasn't met. */
function RefusalNotice({ refusal, entity, state }: { refusal: Refusal; entity: Entity; state: unknown }): ReactNode {
  const { say, locale } = useDaftar();
  // Someone else may have moved the record meanwhile. Then the record's values aren't what stopped this.
  const possible = (refusal.step.from as readonly string[]).includes(String(state));
  const look = possible ? fieldsToCheck(entity, refusal.step).map((field) => say(field.label)) : [];
  return (
    <Notice tone="wrong" title={refusedOf(say(refusal.step.label), locale)}>
      <p>{say(refusal.reason)}</p>
      {look.length ? <p>{fieldsToLookAt(look, locale)}</p> : null}
    </Notice>
  );
}

export interface RecordPageProps {
  meta: Meta;
  entity: Entity;
  id: string;
  /** The list this was opened from, carried on to the form so its way back is the same. */
  from: string | undefined;
  onBack: () => void;
}

export function RecordPage({ meta, entity, id, from, onBack }: RecordPageProps): ReactNode {
  const { say } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const base = `/api/e/${encodeURIComponent(entity.key)}/${encodeURIComponent(id)}`;
  const record = useFetch<Row>(base);
  const history = useFetch<{ changes: AuditChange[] }>(`${base}/history`);
  const [busy, setBusy] = useState<string>();
  const [problem, setProblem] = useState<Problem>();
  const [refusal, setRefusal] = useState<Refusal>();
  const notice = useRef<HTMLDivElement>(null);

  // A phone's page may be scrolled well past where this appears, and the button pressed is pinned at the bottom.
  useEffect(() => {
    if (problem || refusal) notice.current?.scrollIntoView({ block: "nearest" });
  }, [problem, refusal]);

  const deleted = !record.data && record.problem?.kind === "missing" && Boolean(history.data);
  const wasDeleted = useRef(deleted);
  useEffect(() => {
    // The button just pressed has gone, along with the page it was on.
    if (wasDeleted.current !== deleted) document.getElementById("main")?.focus();
    wasDeleted.current = deleted;
  }, [deleted]);

  const reload = (): void => {
    record.reload();
    history.reload();
  };

  const act = (name: string, request: () => Promise<unknown>, whenRefused?: (reason: Label) => void): void => {
    if (busy) return;
    setBusy(name);
    setProblem(undefined);
    setRefusal(undefined);
    void request()
      .then(reload, (error: unknown) => {
        const found = problemOf(error);
        if (found.kind === "reason" && whenRefused) whenRefused(found.reason);
        else setProblem(found);
        // What was refused may be out of date: show the record as it now stands.
        if (found.kind === "reason") reload();
      })
      .finally(() => setBusy(undefined));
  };

  const canRevert = canDo(meta, entity.key, "revert");
  const undo = (change: AuditChange): void => act(change.id, () => call("POST", `/api/changes/${encodeURIComponent(change.id)}/revert`));
  const historyBlock = <RecordHistory meta={meta} entity={entity} changes={history.data?.changes} problem={history.problem} canRevert={canRevert} onUndo={undo} />;
  const row = record.data;
  const workflow = workflowOf(meta.workflows, entity.key);
  const state = row && workflow ? row[workflow.stateField] : undefined;
  const notices = problem || refusal ? (
    <Gutter>
      <div ref={notice}>
        <ProblemNotice problem={problem} />
        {refusal ? <RefusalNotice refusal={refusal} entity={entity} state={state} /> : null}
      </div>
    </Gutter>
  ) : null;

  if (deleted) {
    const deletion = deletionOf(history.data?.changes ?? []);
    return (
      <Page title={deletion?.name ? <UserText>{deletion.name}</UserText> : say(entity.label)} subtitle={deletion?.name ? say(entity.label) : undefined} onBack={onBack}>
        <Gutter>
          <Notice title={t("deletedTitle")} actions={canRevert && deletion ? <Button primary loading={busy === deletion.id} onClick={() => undo(deletion)}>{t("restore")}</Button> : undefined} />
        </Gutter>
        {notices}
        <Gutter>{historyBlock}</Gutter>
      </Page>
    );
  }
  if (!row) {
    if (record.problem?.kind === "missing" && !history.loading) return <MissingPage />;
    const failed = record.problem && record.problem.kind !== "missing" ? record.problem : undefined;
    return (
      <Page title={say(entity.label)} onBack={onBack}>
        <Gutter>
          {failed ? (
            <>
              <ProblemNotice problem={failed} />
              <Button onClick={reload}>{t("retry")}</Button>
            </>
          ) : (
            <Waiting>{say(entity.label)}</Waiting>
          )}
        </Gutter>
      </Page>
    );
  }

  const canUpdate = canDo(meta, entity.key, "update");
  const editable = canUpdate && meta.forms.some((form) => form.entity === entity.key);
  const steps = workflow && canUpdate ? offeredSteps(workflow, state, meta.user.role) : [];
  const stateInfo = workflow?.states.find((item) => item.key === state);
  const facts = entity.fields.filter((field) => field.key !== entity.titleField && field.key !== workflow?.stateField && field.type !== "child");
  const children = entity.fields.filter((field): field is FieldChild => field.type === "child");
  const number = entity.naming.type === "autonumber" ? <CodeText>{row._name}</CodeText> : null;
  const buttons = steps.length || editable ? (
    <>
      {steps.map((step, index) => (
        <Button
          key={step.key}
          primary={index === 0}
          loading={busy === step.key}
          disabled={Boolean(busy)}
          onClick={() => act(step.key, () => call("POST", `${base}/transition`, { action: step.key }), (reason) => setRefusal({ step, reason }))}
        >
          {say(step.label)}
        </Button>
      ))}
      {editable ? <Button primary={!steps.length} disabled={Boolean(busy)} onClick={() => navigate({ name: "edit", entity: entity.key, id, from })}>{t("edit")}</Button> : null}
    </>
  ) : undefined;

  return (
    <Page title={<RecordTitle entity={entity} row={row} />} onBack={onBack} actions={buttons} foot={narrow && buttons ? <FootRow>{buttons}</FootRow> : undefined}>
      {stateInfo || number ? (
        <StateLine>
          {stateInfo ? <StatusChip color={stateInfo.colour} label={say(stateInfo.label)} /> : null}
          {number}
        </StateLine>
      ) : null}
      {notices}
      <TwoColumns>
        <Gutter>
          <FactList>
            {facts.map((field) => (
              <Fact key={field.key} label={say(field.label)}><FactValue field={field} row={row} /></Fact>
            ))}
          </FactList>
          {children.map((field) => <ChildRecords key={field.key} meta={meta} field={field} parent={id} />)}
        </Gutter>
        <Gutter>{historyBlock}</Gutter>
      </TwoColumns>
      {canDo(meta, entity.key, "delete") ? (
        <Gutter>
          <DeleteRecord undoable={canRevert} busy={busy === DELETE_BUTTON} onDelete={() => act(DELETE_BUTTON, () => call("DELETE", base))} />
        </Gutter>
      ) : null}
    </Page>
  );
}
