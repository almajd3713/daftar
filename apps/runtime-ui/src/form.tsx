/** A spec's form, for a new record or an existing one. The server decides what's valid; this shows what it says. */
import type { Entity, Field, Form } from "@daftar/spec/types";
import { Button, ErrorSummary, FootRow, FormActions, FormBody, FormSection, Page, useDaftar, useFrame, Waiting } from "@daftar/ui";
import { useState, type ReactNode } from "react";

import { call, problemOf, useFetch, type Problem, type Row } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { FieldInput, inputId } from "./fields.js";
import { allValues, changedValues, formFields, startingDrafts, type Drafts } from "./values.js";
import { aboutField, useWords } from "./words.js";

const FORM_ID = "record-form";

interface RecordFormProps {
  entity: Entity;
  form: Form;
  record: Row | undefined;
  onClose: () => void;
}

function RecordForm({ entity, form, record, onClose }: RecordFormProps): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const fields: Field[] = formFields(entity, form.sections.flatMap((section) => section.fields));
  const [drafts, setDrafts] = useState<Drafts>(() => startingDrafts(fields, record, locale));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem>();

  const save = (): void => {
    if (busy) return;
    setBusy(true);
    setProblem(undefined);
    const path = `/api/e/${encodeURIComponent(entity.key)}`;
    const request = record
      ? call("PATCH", `${path}/${encodeURIComponent(record._id)}`, { ...changedValues(fields, record, drafts), _version: record._version })
      : call("POST", path, allValues(fields, drafts));
    request.then(onClose, (error: unknown) => {
      setProblem(problemOf(error));
      setBusy(false);
    });
  };

  const fieldErrors = problem?.kind === "fields" ? problem.fields : {};
  const onForm = new Set(fields.map((field) => field.key));
  const errors = fields.flatMap((field) => {
    const message = fieldErrors[field.key];
    return message ? [{ fieldId: inputId(field), message: aboutField(say(field.label), say(message), locale) }] : [];
  });
  // A field the form doesn't show can still be refused, such as a required one left off it. It must still be said.
  const elsewhere = Object.entries(fieldErrors).filter(([key]) => !onForm.has(key)).map(([key, message]) => {
    const field = entity.fields.find((item) => item.key === key);
    return { fieldId: FORM_ID, message: field ? aboutField(say(field.label), say(message), locale) : say(message) };
  });
  const actions = (
    <>
      <Button primary type="submit" form={FORM_ID} loading={busy}>{t("save")}</Button>
      <Button onClick={onClose}>{t("cancel")}</Button>
    </>
  );
  return (
    <Page title={say(form.label)} subtitle={record ? record._name : undefined} onBack={onClose} foot={narrow ? <FootRow>{actions}</FootRow> : undefined}>
      <FormBody id={FORM_ID} onSubmit={save}>
        <ErrorSummary errors={[...errors, ...elsewhere]} />
        <ProblemNotice problem={problem} title={t("couldNotSave")} />
        {form.sections.map((section) => (
          <FormSection key={section.key} title={say(section.label)}>
            {formFields(entity, section.fields).map((field) => (
              <FieldInput
                key={field.key}
                field={field}
                value={drafts[field.key] ?? ""}
                error={fieldErrors[field.key] ? say(fieldErrors[field.key] as { fr: string; ar: string }) : undefined}
                linkLabel={record?._labels?.[field.key]}
                onChange={(value) => setDrafts((current) => ({ ...current, [field.key]: value }))}
              />
            ))}
          </FormSection>
        ))}
        {narrow ? null : <FormActions>{actions}</FormActions>}
      </FormBody>
    </Page>
  );
}

export function NewRecordPage(props: Omit<RecordFormProps, "record">): ReactNode {
  return <RecordForm {...props} record={undefined} />;
}

export function EditRecordPage({ id, ...props }: Omit<RecordFormProps, "record"> & { id: string }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const { data, problem, reload } = useFetch<Row>(`/api/e/${encodeURIComponent(props.entity.key)}/${encodeURIComponent(id)}`);
  if (data) return <RecordForm key={`${id}:${data._version}`} {...props} record={data} />;
  return (
    <Page title={say(props.form.label)} onBack={props.onClose}>
      {problem ? (
        <>
          <ProblemNotice problem={problem} />
          {problem.kind === "failed" ? <Button onClick={reload}>{t("retry")}</Button> : null}
        </>
      ) : (
        <Waiting>{say(props.form.label)}</Waiting>
      )}
    </Page>
  );
}
