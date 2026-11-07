/** One place that knows each field type: how to show its value, and which input takes it. */
import type { CalculatorOutput, Entity, Field } from "@daftar/spec/types";
import {
  Amount,
  ChoiceField,
  DateField,
  DateText,
  DateTimeText,
  EmailField,
  LongTextField,
  Money,
  MoneyField,
  NumberField,
  Percent,
  PhoneField,
  PhoneLink,
  StatusChip,
  TextField,
  TextLink,
  useDaftar,
  UserText,
} from "@daftar/ui";
import { Checkbox, MultiSelect } from "@mantine/core";
import type { ReactNode } from "react";

import { useFetch, type ListResult, type Row } from "./api.js";
import { fitsType, kindOf, outputError, precisionOf, textOf, type Draft } from "./values.js";
import { useWords } from "./words.js";

function choiceOf(field: Field, key: unknown): { label: { fr: string; ar: string }; colour?: string } | undefined {
  return "choices" in field ? field.choices.find((choice) => choice.key === key) : undefined;
}

interface ValueProps {
  field: Field;
  value: unknown;
  /** The name of a link's target. It's left out when this person may not read that row. */
  linkLabel?: string | undefined;
  excelError?: string | undefined;
  /** A column's zero is a dash, as in Excel's Accounting format. Standing alone, it would read as nothing entered. */
  showZero?: boolean | undefined;
}

function Value({ field, value, linkLabel, excelError, showZero }: ValueProps): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  // An Excel error stays visible beside where its value would be, rather than reading as blank.
  if (excelError) return <bdi dir="ltr">{excelError}</bdi>;
  if (value === null || value === undefined) return null;
  switch (kindOf(field)) {
    case "integer":
    case "decimal":
    case "money":
      return <Amount value={value as number} precision={precisionOf(field)} showZero={showZero} />;
    case "percent":
      return <Percent ratio={value as number} />;
    case "date":
      return <DateText value={value as string} />;
    case "datetime":
      return <DateTimeText value={value as string} />;
    case "boolean":
      return value ? t("yes") : t("no");
    case "choice": {
      const choice = choiceOf(field, value);
      return <StatusChip color={choice?.colour} label={choice ? say(choice.label) : <UserText>{textOf(value)}</UserText>} />;
    }
    case "multichoice":
      return (value as string[]).map((key) => {
        const choice = choiceOf(field, key);
        return choice ? say(choice.label) : key;
      }).join(", ");
    case "phone":
      return <PhoneLink value={value as string} />;
    case "email":
      return <TextLink href={`mailto:${value as string}`}><bdi dir="ltr">{value as string}</bdi></TextLink>;
    case "link":
      return linkLabel ? <UserText>{linkLabel}</UserText> : "–";
    default:
      return <UserText>{textOf(value)}</UserText>;
  }
}

/** A value as a list or a record shows it. */
export function FieldValue({ field, row, showZero }: { field: Field; row: Row; showZero?: boolean }): ReactNode {
  return <Value field={field} value={row[field.key]} linkLabel={row._labels?.[field.key]} excelError={row._errors?.[field.key]} showZero={showZero} />;
}

/** A value in a history line. There a state is a word rather than a chip, and nothing has to read as nothing. */
export function PastValue({ field, value, linkLabel }: { field: Field; value: unknown; linkLabel?: string | undefined }): ReactNode {
  const { say } = useDaftar();
  if (value === null || value === undefined || value === "") return "–";
  if (kindOf(field) === "choice") {
    const choice = choiceOf(field, value);
    return choice ? say(choice.label) : <UserText>{textOf(value)}</UserText>;
  }
  return <Value field={field} value={value} linkLabel={linkLabel} showZero />;
}

/** A calculator's result. It stands alone, so money carries its currency and a zero is a zero. */
export function OutputValue({ output, value }: { output: CalculatorOutput; value: unknown }): ReactNode {
  const { key, label, type } = output;
  const excelError = outputError(value);
  if (excelError) return <Value field={{ key, label, type }} value={null} excelError={excelError} />;
  if (value === null || value === undefined || value === "") return "–";
  if (!fitsType(type, value)) return <UserText>{textOf(value)}</UserText>;
  if (type === "money") return <Money value={value as number} />;
  return <Value field={{ key, label, type }} value={value} showZero />;
}

/** What a record is called: its title field if this person can see one with a value, otherwise its name. */
export function RecordTitle({ entity, row }: { entity: Entity; row: Row }): ReactNode {
  const field = entity.fields.find((item) => item.key === entity.titleField);
  return field && row[field.key] !== null && row[field.key] !== undefined ? <FieldValue field={field} row={row} /> : <UserText>{row._name}</UserText>;
}

export const inputId = (field: Field): string => `field-${field.key}`;

interface InputProps {
  field: Field;
  value: Draft;
  error: string | undefined;
  onChange: (value: Draft) => void;
  /** The current link's name, in case it isn't among the options loaded. */
  linkLabel?: string | undefined;
}

/** For now a link picks from its target's first 500, by name. A searching picker comes with the rest of WP-10. */
function LinkInput({ field, value, error, onChange, linkLabel }: InputProps): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const target = "target" in field ? field.target : "";
  const { data } = useFetch<ListResult>(`/api/e/${encodeURIComponent(target)}?pageSize=500`);
  const options = (data?.rows ?? []).map((row) => ({ value: row._id, label: row._name }));
  const current = typeof value === "string" ? value : "";
  if (current && !options.some((option) => option.value === current)) options.unshift({ value: current, label: linkLabel ?? "–" });
  return (
    <ChoiceField
      id={inputId(field)}
      label={say(field.label)}
      required={"required" in field ? field.required : false}
      error={error}
      data={[{ value: "", label: "required" in field && field.required ? t("choose") : t("none") }, ...options]}
      value={current}
      onChange={(event) => onChange(event.currentTarget.value)}
    />
  );
}

export function FieldInput(props: InputProps): ReactNode {
  const { field, value, error, onChange } = props;
  const { say } = useDaftar();
  const t = useWords();
  const text = typeof value === "string" ? value : "";
  const common = { id: inputId(field), label: say(field.label), required: "required" in field ? (field.required ?? false) : false, error };
  const onText = (event: { currentTarget: { value: string } }): void => onChange(event.currentTarget.value);
  switch (field.type) {
    case "longtext":
      return <LongTextField {...common} value={text} onChange={onText} />;
    case "integer":
      return <NumberField {...common} integer value={text} onChange={onText} />;
    case "decimal":
      return <NumberField {...common} value={text} onChange={onText} />;
    case "money":
      return <MoneyField {...common} value={text} onChange={onText} />;
    case "percent":
      return <NumberField {...common} unit="%" value={text} onChange={onText} />;
    case "date":
      return <DateField {...common} value={text || null} onChange={(next) => onChange(next ?? "")} />;
    case "datetime":
      return <TextField {...common} type="datetime-local" value={text} onChange={onText} />;
    case "boolean":
      return <Checkbox id={common.id} label={common.label} error={error} checked={value === true} onChange={(event) => onChange(event.currentTarget.checked)} />;
    case "choice":
      return (
        <ChoiceField
          {...common}
          // Blank until chosen: a select with nothing blank in it shows its first option as if it had been picked.
          data={[...(common.required ? (text ? [] : [{ value: "", label: t("choose") }]) : [{ value: "", label: t("none") }]), ...field.choices.map((choice) => ({ value: choice.key, label: say(choice.label) }))]}
          value={text}
          onChange={onText}
        />
      );
    case "multichoice":
      return <MultiSelect {...common} data={field.choices.map((choice) => ({ value: choice.key, label: say(choice.label) }))} value={Array.isArray(value) ? value : []} onChange={onChange} />;
    case "phone":
      return <PhoneField {...common} value={text} onChange={onText} />;
    case "email":
      return <EmailField {...common} value={text} onChange={onText} />;
    case "link":
      return <LinkInput {...props} />;
    default:
      return <TextField {...common} value={text} onChange={onText} />;
  }
}
