/** R-19: a workbook's formula model. The server runs it on demand, and its formulas never reach the browser. */
import type { CalculatorOutput } from "@daftar/spec/types";
import { Button, ErrorSummary, FormBody, FormSection, Gutter, Notice, Page, Statement, StatementLine, TwoColumns, useDaftar, useFrame } from "@daftar/ui";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { call, problemOf, type CalcResult, type MetaCalculator, type Problem } from "./api.js";
import { ProblemNotice } from "./auth.js";
import { FieldInput, inputId, OutputValue } from "./fields.js";
import { everyValue, fieldOfInput, outputError, startingDrafts, type Drafts } from "./values.js";
import { aboutField, useWords } from "./words.js";

/** The last output closes the statement when it's a figure, as a workbook's bottom line does. A spec doesn't say which is the total. */
function closesStatement(output: CalculatorOutput, index: number, outputs: readonly CalculatorOutput[]): boolean {
  return index === outputs.length - 1 && ["money", "integer", "decimal"].includes(output.type);
}

export function CalculatorPage({ calculator }: { calculator: MetaCalculator }): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const fields = useMemo(() => calculator.inputs.map(fieldOfInput), [calculator]);
  const [start] = useState(() => startingDrafts(fields, undefined, locale));
  const [drafts, setDrafts] = useState<Drafts>(start);
  const [outputs, setOutputs] = useState<CalcResult["outputs"]>();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem>();
  const result = useRef<HTMLDivElement>(null);
  const bringIntoView = useRef(false);
  // Only the answer to what's on screen counts: changing a value while one is on its way makes it out of date.
  const asked = useRef(0);

  const run = useCallback(
    (values: Drafts): void => {
      asked.current += 1;
      const turn = asked.current;
      setBusy(true);
      setProblem(undefined);
      call<CalcResult>("POST", `/api/calc/${encodeURIComponent(calculator.key)}`, everyValue(fields, values)).then(
        (answer) => {
          if (turn !== asked.current) return;
          setOutputs(answer.outputs);
          setBusy(false);
        },
        (error: unknown) => {
          if (turn !== asked.current) return;
          setOutputs(undefined);
          setProblem(problemOf(error));
          setBusy(false);
        },
      );
    },
    [calculator.key, fields],
  );

  // What the workbook shows when it's opened. An input with no value yet waits for the person, or the first thing
  // they'd read is what the formula makes of a blank.
  useEffect(() => {
    if (calculator.inputs.every((port) => port.default !== undefined && port.default !== null)) run(start);
  }, [calculator, run, start]);

  // On a phone the result is below the form, and the keyboard would cover it. Moving to it closes the keyboard, and
  // puts a screen reader there too. On a PC it's beside the form, so the person stays in the field to try another value.
  useEffect(() => {
    if (!outputs || !bringIntoView.current) return;
    bringIntoView.current = false;
    result.current?.focus({ preventScroll: true });
    result.current?.scrollIntoView({ block: "start" });
  }, [outputs]);

  const compute = (): void => {
    if (busy) return;
    bringIntoView.current = narrow;
    run(drafts);
  };

  const change = (key: string, value: Drafts[string]): void => {
    setDrafts((current) => ({ ...current, [key]: value }));
    // A figure beside values it didn't come from is how a wrong fee gets quoted, so it goes as soon as they differ.
    asked.current += 1;
    setOutputs(undefined);
    setBusy(false);
    bringIntoView.current = false;
  };

  const fieldErrors = problem?.kind === "fields" ? problem.fields : {};
  const errors = fields.flatMap((field) => {
    const message = fieldErrors[field.key];
    return message ? [{ fieldId: inputId(field), message: aboutField(say(field.label), say(message), locale) }] : [];
  });
  const hasError = outputs ? calculator.outputs.some((output) => outputError(outputs[output.key])) : false;

  return (
    <Page title={say(calculator.label)}>
      <TwoColumns>
        <Gutter>
          <FormBody onSubmit={compute}>
            <ErrorSummary errors={errors} />
            <ProblemNotice problem={problem} title={t("couldNotCompute")} />
            <FormSection>
              {fields.map((field) => {
                const message = fieldErrors[field.key];
                return <FieldInput key={field.key} field={field} value={drafts[field.key] ?? ""} error={message ? say(message) : undefined} onChange={(value) => change(field.key, value)} />;
              })}
              <Button primary type="submit" fullWidth={narrow} loading={busy}>{t("compute")}</Button>
            </FormSection>
          </FormBody>
        </Gutter>
        <Gutter>
          <Statement ref={result} live title={t("result")}>
            {calculator.outputs.map((output, index, all) => (
              <StatementLine key={output.key} label={say(output.label)} total={closesStatement(output, index, all)}>
                {outputs ? <OutputValue output={output} value={outputs[output.key]} /> : "–"}
              </StatementLine>
            ))}
          </Statement>
          {hasError ? <Notice tone="wrong" title={t("computeErrorTitle")}>{t("computeErrorBody")}</Notice> : null}
        </Gutter>
      </TwoColumns>
    </Page>
  );
}
