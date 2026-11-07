/**
 * Mantine, pointed at Registre's tokens. Mantine stays the engine for inputs, dropdowns, dialogs and focus
 * handling; every colour and size it reads comes from the CSS variables that tokens.ts generates, so
 * nothing below repeats a value.
 */
import { Button, Checkbox, createTheme, Input, InputWrapper, Modal, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";
import { DateInput, PickerControl } from "@mantine/dates";

import { colors, fontFamily, fontWeights } from "./tokens.js";

// Only so Mantine's colour functions have a full tuple. Screens use the tokens, never these steps.
const ink: MantineColorsTuple = ["#EEF1FA", "#DCE2F5", "#B9C5EA", "#96A8DF", "#7A90D6", "#5F78CC", "#4560B8", "#2F479C", "#1C2F80", "#142362"];

const sharp = "var(--radius)";

// A full target on a phone. With a mouse, 36 px rather than the 24 px minimum, because a calendar is all small buttons.
const calendarControl = "max(var(--target), 2.25rem)";
const pickerControlVars = { "--dpc-size": calendarControl, "--dpc-fz": "var(--t-body)" };

export const theme = createTheme({
  fontFamily,
  fontFamilyMonospace: fontFamily,
  black: colors.ink.light,
  white: "#FFFFFF",
  primaryColor: "ink",
  primaryShade: 8,
  colors: { ink },
  defaultRadius: "xs",
  radius: { xs: sharp, sm: sharp, md: sharp, lg: sharp, xl: sharp },
  spacing: { xs: "var(--space-2)", sm: "var(--space-3)", md: "var(--space-4)", lg: "var(--space-6)", xl: "var(--space-8)" },
  fontSizes: { xs: "var(--t-small)", sm: "var(--t-small)", md: "var(--t-body)", lg: "var(--t-h2)", xl: "var(--t-h1)" },
  lineHeights: { xs: "var(--l-small)", sm: "var(--l-small)", md: "var(--l-body)", lg: "var(--l-h2)", xl: "var(--l-h1)" },
  fontWeights: { regular: String(fontWeights.regular), medium: String(fontWeights.medium), bold: String(fontWeights.bold) },
  // Only a layer that really floats gets a shadow. Nothing on the page has one.
  shadows: { xs: "none", sm: "none", md: "0 .25rem .75rem rgb(22 30 49 / 18%)", lg: "0 .25rem .75rem rgb(22 30 49 / 18%)", xl: "0 .25rem .75rem rgb(22 30 49 / 18%)" },
  headings: {
    fontFamily,
    fontWeight: String(fontWeights.bold),
    sizes: {
      h1: { fontSize: "var(--t-h1)", lineHeight: "var(--l-h1)" },
      h2: { fontSize: "var(--t-h2)", lineHeight: "var(--l-h2)" },
      h3: { fontSize: "var(--t-h2)", lineHeight: "var(--l-h2)" },
      h4: { fontSize: "var(--t-body)", lineHeight: "var(--l-body)" },
      h5: { fontSize: "var(--t-body)", lineHeight: "var(--l-body)" },
      h6: { fontSize: "var(--t-body)", lineHeight: "var(--l-body)" },
    },
  },
  cursorType: "pointer",
  respectReducedMotion: true,
  components: {
    Button: Button.extend({
      defaultProps: { variant: "default" },
      vars: (_theme, props) => ({
        root: {
          "--button-height": "var(--control)",
          "--button-padding-x": "var(--space-4)",
          "--button-fz": "var(--t-body)",
          "--button-radius": sharp,
          ...(props.variant === "filled"
            ? { "--button-bg": "var(--accent)", "--button-hover": "var(--accent-hover)", "--button-color": "var(--on-accent)", "--button-hover-color": "var(--on-accent)", "--button-bd": "1px solid transparent" }
            : { "--button-bg": "transparent", "--button-hover": "var(--raised)", "--button-color": "var(--ink)", "--button-hover-color": "var(--ink)", "--button-bd": "1px solid var(--rule-input)" }),
        },
      }),
    }),
    Input: Input.extend({
      vars: () => ({ wrapper: { "--input-height": "var(--control)", "--input-fz": "var(--t-input)", "--input-radius": sharp } }),
    }),
    InputWrapper: InputWrapper.extend({
      // GOV.UK's order. Mantine's default puts the error under the field.
      defaultProps: { inputWrapperOrder: ["label", "description", "error", "input"] },
    }),
    Checkbox: Checkbox.extend({
      defaultProps: { iconColor: "var(--on-accent)" },
      vars: () => ({ root: { "--checkbox-size": "var(--target)" } }),
    }),
    Modal: Modal.extend({
      defaultProps: { shadow: "md", centered: true },
    }),
    // The calendar's parts look themselves up under the input that holds them, not under their own names.
    DateInput: DateInput.extend({
      vars: () => ({
        day: { "--day-size": calendarControl },
        calendarHeader: { "--dch-control-size": calendarControl, "--dch-fz": "var(--t-body)" },
        pickerControl: pickerControlVars,
        weekdaysRow: { "--wr-fz": "var(--t-small)", "--wr-spacing": "var(--space-2)" },
      }),
    }),
    // Except the year buttons: Mantine's YearsList doesn't pass the input's name down.
    PickerControl: PickerControl.extend({
      vars: () => ({ pickerControl: pickerControlVars }),
    }),
  },
});

/** Everything Mantine paints with, by either scheme, resolves to a token. */
const shared = {
  "--mantine-color-text": "var(--ink)",
  "--mantine-color-body": "var(--paper)",
  "--mantine-color-bright": "var(--ink)",
  "--mantine-color-error": "var(--late)",
  "--mantine-color-success": "var(--ink)",
  "--mantine-color-placeholder": "var(--muted)",
  "--mantine-color-anchor": "var(--accent)",
  "--mantine-color-default": "var(--surface)",
  "--mantine-color-default-hover": "var(--raised)",
  "--mantine-color-default-color": "var(--ink)",
  "--mantine-color-default-border": "var(--rule-input)",
  "--mantine-color-dimmed": "var(--muted)",
  "--mantine-color-disabled": "var(--fill)",
  "--mantine-color-disabled-color": "var(--muted)",
  "--mantine-color-disabled-border": "var(--rule)",
  "--mantine-primary-color-contrast": "var(--on-accent)",
  "--mantine-color-ink-filled": "var(--accent)",
  "--mantine-color-ink-filled-hover": "var(--accent-hover)",
  "--mantine-color-ink-text": "var(--accent)",
  "--mantine-color-ink-outline": "var(--accent)",
  "--mantine-color-ink-light": "var(--raised)",
  "--mantine-color-ink-light-hover": "var(--fill)",
  "--mantine-color-ink-light-color": "var(--accent)",
};

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    "--mantine-primary-color-filled": "var(--accent)",
    "--mantine-primary-color-filled-hover": "var(--accent-hover)",
    "--mantine-primary-color-light": "var(--raised)",
    "--mantine-primary-color-light-hover": "var(--fill)",
    "--mantine-primary-color-light-color": "var(--accent)",
  },
  light: shared,
  dark: shared,
});
