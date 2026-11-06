/**
 * Mantine's inputs with Registre's rules built in: the theme already sets the order (label, hint, error,
 * field) and the required mark. These add what each kind of value needs: its direction, its keyboard,
 * and how its text turns into what the server stores.
 */
import { FileInput, NativeSelect, PasswordInput, Textarea, TextInput, type FileInputProps, type NativeSelectProps, type PasswordInputProps, type TextareaProps, type TextInputProps } from "@mantine/core";
import { DateInput, type DateInputProps } from "@mantine/dates";
import { useId, type ReactNode } from "react";

import { currencyLabel, parseDateInput } from "./format.js";
import { fieldsToFix } from "./messages.js";
import { langOf, plural } from "./format.js";
import { useDaftar, useFrame } from "./provider.js";
import { WarningIcon, SearchIcon } from "./layout.js";
import classes from "./form.module.css";

/** What a field shows beside its label when it's wrong. The hidden word is for screen readers. */
function ErrorText({ children }: { children: ReactNode }): ReactNode {
  const { ui } = useDaftar();
  return (
    <>
      <WarningIcon />
      <span>
        <span className={classes.visuallyHidden}>{ui("errorPrefix")} </span>
        {children}
      </span>
    </>
  );
}

const errorNode = (error: ReactNode): ReactNode => (error ? <ErrorText>{error}</ErrorText> : undefined);

/** Text in any script. Its direction follows what's typed. */
export function TextField({ error, ...props }: TextInputProps): ReactNode {
  return <TextInput dir="auto" error={errorNode(error)} {...props} />;
}

export function LongTextField({ error, ...props }: TextareaProps): ReactNode {
  return <Textarea dir="auto" autosize minRows={2} error={errorNode(error)} {...props} />;
}

export interface NumberFieldProps extends TextInputProps {
  /** Shown inside the field, at its end. */
  unit?: ReactNode;
  integer?: boolean | undefined;
}

/** A number: digits left to right and aligned right, in both languages. Text, so it can hold `9.800,00`. */
export function NumberField({ unit, integer, error, classNames, ...props }: NumberFieldProps): ReactNode {
  return (
    <TextInput
      inputMode={integer ? "numeric" : "decimal"}
      autoComplete="off"
      rightSection={unit ? <span className={classes.unit}>{unit}</span> : undefined}
      rightSectionWidth={unit ? "3.25rem" : undefined}
      classNames={{ ...(classNames as object | undefined), input: unit ? `${classes.numberInput} ${classes.withUnit}` : (classes.numberInput ?? "") }}
      error={errorNode(error)}
      {...props}
    />
  );
}

/** Money: a NumberField whose unit is the dinar in the current language. */
export function MoneyField(props: NumberFieldProps): ReactNode {
  const { locale } = useDaftar();
  return <NumberField unit={currencyLabel(locale)} {...props} />;
}

/** A phone number never mirrors, and stays at the left in both directions. */
export function PhoneField({ error, classNames, ...props }: TextInputProps): ReactNode {
  return <TextInput type="tel" inputMode="tel" autoComplete="tel" classNames={{ ...(classNames as object | undefined), input: classes.ltrInput ?? "" }} error={errorNode(error)} {...props} />;
}

export function EmailField({ error, classNames, ...props }: TextInputProps): ReactNode {
  return <TextInput type="email" inputMode="email" autoComplete="email" classNames={{ ...(classNames as object | undefined), input: classes.ltrInput ?? "" }} error={errorNode(error)} {...props} />;
}

/** The value is a stored `YYYY-MM-DD`. Typed day first, in any digits, or picked from a calendar starting on Saturday. */
export function DateField({ error, classNames, popoverProps, ...props }: DateInputProps): ReactNode {
  const { ui } = useDaftar();
  const { narrow } = useFrame();
  return (
    <DateInput
      valueFormat="DD/MM/YYYY"
      placeholder={ui("datePlaceholder")}
      dateParser={(text) => parseDateInput(text)}
      highlightToday
      // The calendar floats outside the frame, so it has to be told the frame's layout, or a phone gets a PC's targets.
      popoverProps={{ ...popoverProps, attributes: { dropdown: { "data-layout": narrow ? "narrow" : "wide" } } }}
      // The month's own name already labels the control between these, so only the arrows need words.
      ariaLabels={{
        previousMonth: ui("previousMonth"),
        nextMonth: ui("nextMonth"),
        previousYear: ui("previousYear"),
        nextYear: ui("nextYear"),
        previousDecade: ui("previousYears"),
        nextDecade: ui("nextYears"),
      }}
      classNames={{ ...(classNames as object | undefined), input: classes.ltrInput ?? "" }}
      error={errorNode(error)}
      {...props}
    />
  );
}

/** A choice. The native control, because on a phone it opens the system's own picker. */
export function ChoiceField({ error, ...props }: NativeSelectProps): ReactNode {
  return <NativeSelect error={errorNode(error)} {...props} />;
}

/** Typing on a phone is error-prone, so the password can be shown. */
export function PasswordField({ error, ...props }: PasswordInputProps): ReactNode {
  const { ui } = useDaftar();
  return <PasswordInput rightSectionWidth="2.75rem" visibilityToggleButtonProps={{ "aria-label": ui("showPassword") }} error={errorNode(error)} {...props} />;
}

/** A file's name can be in either script, so it keeps its own direction. */
function FileName({ value }: { value: File | File[] | null }): ReactNode {
  return <bdi dir="auto">{value instanceof File ? value.name : null}</bdi>;
}

/** One file from the device: a workbook to analyse or import. The form sends it; this only picks it. */
export function FileField({ error, ...props }: FileInputProps): ReactNode {
  const { ui } = useDaftar();
  return <FileInput placeholder={ui("chooseFile")} valueComponent={FileName} error={errorNode(error)} {...props} />;
}

/** The list's search. Its label is hidden because the icon and placeholder say the same, and screen readers still get it. */
export function SearchField(props: Omit<TextInputProps, "label">): ReactNode {
  const { ui } = useDaftar();
  const { narrow } = useFrame();
  return (
    <TextInput
      type="search"
      aria-label={ui("search")}
      placeholder={ui("search")}
      leftSection={<SearchIcon />}
      className={narrow ? undefined : classes.search}
      enterKeyHint="search"
      {...props}
    />
  );
}

/** A form's named group of fields. */
export function FormSection({ title, children }: { title?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <section className={classes.section}>
      {title ? <h2>{title}</h2> : null}
      <div className={classes.fields}>{children}</div>
    </section>
  );
}

/** Two short related fields on one line on a PC, stacked on a phone. Otherwise forms are one column. */
export function FieldPair({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.pair}>{children}</div>;
}

export function FormBody({ children, onSubmit }: { children: ReactNode; onSubmit?: (() => void) | undefined }): ReactNode {
  return (
    <form
      className={classes.form}
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit?.();
      }}
    >
      {children}
    </form>
  );
}

export function FormActions({ children }: { children: ReactNode }): ReactNode {
  return <div className={classes.actions}>{children}</div>;
}

export interface ErrorSummaryProps {
  /** The same words as beside each field, linked to it. */
  errors: { fieldId: string; message: ReactNode }[];
}

/** Top of the form, shown even for one error. On a long phone form the bad field may be off screen. Move focus here. */
export function ErrorSummary({ errors }: ErrorSummaryProps): ReactNode {
  const { locale } = useDaftar();
  const id = useId();
  if (!errors.length) return null;
  return (
    <div className={classes.summary} role="alert" tabIndex={-1} aria-labelledby={id}>
      <h2 id={id}>{plural(errors.length, locale, fieldsToFix[langOf(locale)])}</h2>
      <ul>
        {errors.map((error) => (
          <li key={error.fieldId}>
            <a href={`#${error.fieldId}`}>{error.message}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
