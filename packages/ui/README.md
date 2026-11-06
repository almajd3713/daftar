# @daftar/ui

Registre, Daftar's design system, on Mantine (D-12). The idea is a register kept in ballpoint: blue ink for what you act on, red pen only for what is late, ruled lines instead of boxes, and totals closed with the accountant's double rule.

The Runtime and the Studio both build from this package, so an app and its preview look the same.

## Using it

```tsx
import "@daftar/ui/styles.css";
import { DaftarProvider, useStoredLocale, AppFrame, Page } from "@daftar/ui";

function Root({ app }) {
  // `app` is what GET /api/auth/status returns. Leave out LanguageSwitch if it offers one language.
  const [locale, setLocale] = useStoredLocale(app.defaultLocale, app.locales);
  return (
    <DaftarProvider locale={locale}>
      <AppFrame firm="…" nav={[[{ key: "payments", label: "…" }]]} current="payments">
        <Page title="…">…</Page>
      </AppFrame>
    </DaftarProvider>
  );
}
```

`pnpm --filter @daftar/ui dev` serves the reference app in `preview/`. It draws all twelve screens from these components, side by side at phone and PC width, with switches for language, theme and awkward data. A screen there that needed its own CSS would mean the system has a gap, and it has none.

## Tokens

`src/tokens.ts` is the only source. `pnpm generate` writes `src/generated/`, and a test fails if that's stale. Components use the CSS variables, and `theme.ts` points Mantine at the same ones. Never write a colour, size or space anywhere else.

| Colour | Use |
|---|---|
| `paper` | The page. Everything sits directly on it: no cards |
| `surface` | Inside inputs |
| `raised`, `fill` | Hover and the active finding; grid headings and progress tracks |
| `ink`, `muted` | Body text; labels, hints and table headings |
| `rule`, `rule-input`, `rule-strong` | The hairline between rows; borders of inputs and quiet buttons (3:1); the ink rule and the double rule |
| `accent`, `on-accent` | Ballpoint blue: the primary action, links, the current tab; text on it |
| `late`, `late-soft` | Red pen: only what is overdue or wrong, always beside a word |
| `focus` | The 2px focus ring |
| `chart`, `evidence` | Chart marks; a finding's cells on the grid |

Spacing is `space-1`, `2`, `3`, `4`, `6`, `8`, `12`: multiples of 4 px, in rem. Gaps inside a group are smaller than gaps between groups, so closeness carries the structure. Type is `small` 13/20, `body` 14/24 (15 on a phone), `h2` 16/24, `h1` 24/32 (20/28), `hero` 40/48 (32/40). Nothing goes below 13 px.

## Rules a screen must keep

**Language and direction**
- One type scale for both languages. The Arabic face carries `size-adjust: 110%`, so never add a per-language size.
- No letter-spacing, capitals or italics, in either language.
- Text someone typed goes in `UserText`, because it can arrive in either script. Receipt numbers, cell references and formulas go in `CodeText`. A phone number uses `PhoneLink` or `PhoneField`, and stays left to right.
- Words go through `say()`, from the spec or the server. French sets a no-break space before `:`, `?` and `»`, and uses `’`.

**Numbers**
- Use `format.ts` and never call `Intl` for a number or a month: it depends on the browser's ICU, and `fr-DZ` inserts U+202F, which the font lacks.
- In a column, use `Amount`: tabular, right-aligned by place value in both directions, with the currency once, in the heading. A zero is a dash, and a total stays a number (`showZero`).
- Alone, use `Money`, which carries its currency.

**Colour**
- Red means late or wrong, and never appears without a word: `LateTag`, or a message.
- A workbook's colours can be anything, so only `StatusChip`'s swatch wears them. The word beside it is always in `ink`.
- Status colours never colour text or fill a tag.

**Structure**
- Rules, not boxes. A table has one hairline per row, an ink rule under its heading, and a double rule under its total. No vertical rules, zebra stripes or shadows on the page.
- The radius is 2 px, on inputs and buttons only.
- At most one primary button on a page.
- Below 768 px of its own width a frame goes to its phone layout. Use `useFrame()` rather than a media query, so the Studio's embedded preview behaves like a phone.

**Touch and keyboard**
- A finger gets 44 px, and a mouse 24 px. `--target` and `--control` already do this.
- Every board card has a button for its next step, so moving a card never depends on dragging.
- Every chart has its numbers one tap away, in `LineChart`'s details. A tooltip never holds the only copy of a value.
- Past 31 points a `LineChart` gives no tab stop per point, because the details table is the better way through them.

**Charts**
- `LineChart` takes what `/aggregate` returns. Give every point `at` when dates aren't evenly spaced, or a gap in the data won't show. A null `value` breaks the line rather than reading as zero.
- Set `money` only for money, so a count doesn't get a currency.

**Forms**
- One column. `FieldPair` only for two short, related fields.
- The order is label, hint, error, field. `ErrorSummary` goes at the top, even for one error, with the same words as the field, and takes focus.
- Pick the field by the value, because each sets its own direction and keyboard: `TextField`, `LongTextField`, `NumberField`, `MoneyField`, `DateField`, `PhoneField`, `EmailField`, `ChoiceField`, `PasswordField`, `FileField`.

**Empty, waiting and messages**
- `EmptyState` says what's true and offers the way to start. Only show it once loading has really finished.
- `Waiting` is for server work of unknown length. It never shows a percentage it can't back.
- `Notice` is a message that stays until it stops being true. `tone="wrong"` is red pen, for what failed or needs fixing. The default is ink, for what's worth reading when nothing is wrong. A form's errors use `ErrorSummary` instead.

**Floating parts**
- Anything Mantine floats renders outside the frame, so it can't see `data-layout`. `DateField` passes it on. On a real phone `pointer: coarse` sets the same targets for `Modal` and `Select`, but a narrow frame with a mouse doesn't get them unless you pass it too.

## Components

| Group | Components |
|---|---|
| Root | `DaftarProvider`, `useDaftar`, `useStoredLocale`, `Frame`, `useFrame` |
| Text | `UserText`, `CodeText`, `Amount`, `Money`, `Percent`, `DateText`, `DateTimeText`, `PhoneLink`, `LateTag`, `TextLink`, `StatusChip`, `Confidence` |
| Layout | `AppFrame`, `BareFrame`, `AuthLayout`, `Page`, `ViewTabs`, `FootRow`, `LanguageSwitch`, `Button` |
| Records | `LedgerTable`, `RecordList`, `RecordRow`, `EmptyState`, `Notice`, `Waiting`, `FactList`, `Fact`, `TwoColumns`, `Gutter`, `SectionHeading`, `HistoryList`, `Change`, `StateLine` |
| Statements and dashboards | `Statement`, `StatementLine`, `HeroFigure`, `LeadRow`, `Panels`, `Panel`, `LineChart`, `BarList` |
| Board | `BoardColumns`, `BoardColumn`, `BoardCard` |
| Forms | The fields above, `SearchField`, `FormBody`, `FormSection`, `FieldPair`, `FormActions`, `ErrorSummary` |
| Phone menu | `MenuList`, `MenuHeading`, `MenuItem` |
| Studio | `ReviewLayout`, `SheetTabs`, `SheetGrid`, `SheetLegend`, `FindingList`, `Finding` |

Mantine's own `Modal`, `Select`, `MultiSelect` and `Checkbox` already follow the theme, so use them directly when a screen needs them. Their CSS must be listed in `src/styles/index.css`, which imports only what's in use: Mantine's whole sheet is 295 KB.

## Checks

```sh
pnpm --filter @daftar/ui test            # formats against Node's Intl, every contrast pair in both themes, the scales
pnpm --filter @daftar/ui test:browser    # builds, then runs the reference app in Chromium
```

The browser audit covers every screen, in both languages and themes, with normal and awkward data, at phone and PC size. It measures overflow, target sizes, contrast, type size, Arabic line height and tabular digits, and runs axe. The open calendar gets the same checks on its days, months and years, because a closed one shows none of them. It also tries 320 px and 150% text, a 240-point series, and checks each promise above: fonts really embedded, the calendar starting on Saturday, the error's position, the double rule, and six full rows on a 360 by 680 phone.

It doesn't replace looking at the screens. Safari hasn't been tested, nor has a real phone with its keyboard open over the calendar, and no native speaker has reviewed the French or Arabic.

## Fonts

IBM Plex Sans Arabic in three weights, self-hosted under `src/fonts/` (OFL), because a firm's box has to work with no internet. Of the 11 families measured it's one of four with both the Algerian letter ڨ and tabular digits. The three weights come to 187 KB, and a browser downloads only the script a page needs.
