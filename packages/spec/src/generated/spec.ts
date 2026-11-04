// Generated from schema/daftar.spec.schema.json by `pnpm generate`. Do not edit.

export type Locale = "fr-DZ" | "ar-DZ";
export type A1Range = string;
export type Key = string;
export type Naming = NamingAutonumber | NamingField | NamingUuid;
export type Field = FieldScalar | FieldChoice | FieldLink | FieldChild | FieldComputed;
/**
 * This interface was referenced by `KeyedScalars`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9_]{0,62}$".
 */
export type Scalar = string | number | boolean | null;
/**
 * 0 is visible to every role; 1 is sensitive, for roles with fieldLevel 1 only (R-17).
 */
export type FieldLevel = 0 | 1;
export type Colour = string;
export type Computed = ComputedTranslated | ComputedEngine;
/**
 * Typed expression tree. Never built into SQL strings.
 */
export type Expr = ExprLiteral | ExprField | ExprRelated | ExprOp | ExprCall | ExprRollup;
export type ValueType = "number" | "text" | "boolean" | "date" | "any";
export type Aggregate = "sum" | "count" | "avg" | "min" | "max";
/**
 * A field key, or link_field.field for a field on a linked record.
 */
export type FieldPath = string;
export type View = ViewList | ViewBoard;
export type Widget = WidgetKpi | WidgetChart;

/**
 * C-3: the app spec. Keys are the only source of database identifiers; every label is {fr, ar}. Rejected findings never reach a spec.
 */
export interface DaftarSpec {
  /**
   * Semver. This schema reads major version 1.
   */
  specVersion: string;
  app: App;
  entities: Entity[];
  calculators: Calculator[];
  views: View[];
  forms: Form[];
  dashboards: Dashboard[];
  /**
   * @minItems 1
   * @maxItems 4
   */
  roles: [Role] | [Role, Role] | [Role, Role, Role] | [Role, Role, Role, Role];
  workflows: Workflow[];
  reminders: Reminder[];
  history: History;
  mapping: EntityMapping[];
}
export interface App {
  name: Label;
  /**
   * @minItems 1
   */
  locales: [Locale, ...Locale[]];
  defaultLocale: Locale;
  currency: "DZD";
  timezone: string;
  provenance?: Provenance;
}
export interface Label {
  fr: string;
  ar: string;
}
/**
 * Where an element came from. Only accepted or edited findings reach a spec.
 */
export interface Provenance {
  workbookSha256: string;
  sheet: string;
  range: A1Range;
  detector: string;
  confidence: {
    level: "high" | "medium" | "low";
    score: number;
  };
  decision: "accepted" | "edited";
  decidedBy: string;
  decidedAt: string;
}
export interface Entity {
  key: Key;
  label: Label;
  kind: "register" | "ledger" | "tracker" | "reference";
  naming: Naming;
  titleField: Key;
  searchFields?: Key[];
  period?: Period;
  /**
   * True if records in this entity hold personal data (R-24). Requires retention.
   */
  personalData: boolean;
  retention?: Retention;
  /**
   * @minItems 1
   */
  fields: [Field, ...Field[]];
  provenance?: Provenance;
}
export interface NamingAutonumber {
  type: "autonumber";
  prefix: string;
}
export interface NamingField {
  type: "field";
  field: Key;
}
export interface NamingUuid {
  type: "uuid";
}
/**
 * Period field of an entity merged from period tabs (R-8).
 */
export interface Period {
  field: Key;
  granularity: "month" | "quarter" | "year";
}
export interface Retention {
  months: number;
  basis: Label;
}
export interface FieldScalar {
  key: Key;
  label: Label;
  type:
    | "text"
    | "longtext"
    | "integer"
    | "decimal"
    | "money"
    | "percent"
    | "date"
    | "datetime"
    | "boolean"
    | "phone"
    | "email";
  required?: boolean;
  unique?: boolean;
  default?: Scalar;
  precision?: number;
  level?: FieldLevel;
  personalData?: boolean;
  provenance?: Provenance;
}
export interface FieldChoice {
  key: Key;
  label: Label;
  type: "choice" | "multichoice";
  /**
   * @minItems 1
   */
  choices: [Choice, ...Choice[]];
  required?: boolean;
  default?: Scalar;
  level?: FieldLevel;
  personalData?: boolean;
  provenance?: Provenance;
}
/**
 * Stable key, separate from its labels. `source` keeps the original cell text for round trips.
 */
export interface Choice {
  key: Key;
  label: Label;
  colour?: Colour;
  source?: string;
  provenance?: Provenance;
}
/**
 * Many-to-one relation to another entity.
 */
export interface FieldLink {
  key: Key;
  label: Label;
  type: "link";
  target: Key;
  onDelete: "restrict" | "setNull" | "cascade";
  required?: boolean;
  level?: FieldLevel;
  personalData?: boolean;
  provenance?: Provenance;
}
/**
 * One-to-many relation: records of `target` whose link field `via` points here.
 */
export interface FieldChild {
  key: Key;
  label: Label;
  type: "child";
  target: Key;
  via: Key;
  level?: FieldLevel;
  provenance?: Provenance;
}
export interface FieldComputed {
  key: Key;
  label: Label;
  type: "computed";
  /**
   * How the result is typed and displayed.
   */
  resultType: "text" | "integer" | "decimal" | "money" | "percent" | "date" | "datetime" | "boolean";
  precision?: number;
  computed: Computed;
  level?: FieldLevel;
  personalData?: boolean;
  provenance?: Provenance;
}
export interface ComputedTranslated {
  eval: "translated";
  expr: Expr;
  /**
   * The original formula text.
   */
  excel: string;
  deps: FieldPath[];
  store: boolean;
}
export interface ExprLiteral {
  kind: "literal";
  valueType: ValueType;
  value: Scalar;
}
export interface ExprField {
  kind: "field";
  valueType: ValueType;
  field: Key;
}
/**
 * A field on the record that the link field `via` points to.
 */
export interface ExprRelated {
  kind: "related";
  valueType: ValueType;
  via: Key;
  field: Key;
}
export interface ExprOp {
  kind: "op";
  valueType: ValueType;
  op: "add" | "sub" | "mul" | "div" | "pow" | "neg" | "pct" | "concat" | "eq" | "ne" | "lt" | "le" | "gt" | "ge";
  /**
   * @minItems 1
   * @maxItems 2
   */
  args: [Expr] | [Expr, Expr];
}
/**
 * An Excel function, English name. WP-6 owns the list of translatable functions.
 */
export interface ExprCall {
  kind: "call";
  valueType: ValueType;
  fn: string;
  args: Expr[];
}
/**
 * An aggregate over the records of the child field `via`.
 */
export interface ExprRollup {
  kind: "rollup";
  valueType: ValueType;
  via: Key;
  fn: Aggregate;
  field?: Key;
}
/**
 * A formula outside the translatable set: no expression tree, the engine runs `excel` (R-19).
 */
export interface ComputedEngine {
  eval: "engine";
  /**
   * The original formula text.
   */
  excel: string;
  deps: FieldPath[];
  store: boolean;
}
/**
 * A formula model evaluated in the engine on demand. `cells` holds the cell graph; `testCases` are checked against Excel's stored results.
 */
export interface Calculator {
  key: Key;
  label: Label;
  /**
   * @minItems 1
   */
  inputs: [CalculatorInput, ...CalculatorInput[]];
  /**
   * @minItems 1
   */
  outputs: [CalculatorOutput, ...CalculatorOutput[]];
  /**
   * @minItems 1
   */
  cells: [CalculatorCell, ...CalculatorCell[]];
  testCases: CalculatorTestCase[];
  provenance?: Provenance;
}
export interface CalculatorInput {
  key: Key;
  label: Label;
  type: "text" | "integer" | "decimal" | "money" | "percent" | "date" | "boolean" | "choice";
  sheet: string;
  cell: A1Range;
  default?: Scalar;
  /**
   * @minItems 1
   */
  choices?: [Choice, ...Choice[]];
  provenance?: Provenance;
}
export interface CalculatorOutput {
  key: Key;
  label: Label;
  type: "text" | "integer" | "decimal" | "money" | "percent" | "date" | "boolean";
  sheet: string;
  cell: A1Range;
  level?: FieldLevel;
  provenance?: Provenance;
}
/**
 * One cell of the model: a constant in `v`, or a formula in `f`.
 */
export interface CalculatorCell {
  sheet: string;
  ref: A1Range;
  v?: Scalar;
  f?: string;
}
export interface CalculatorTestCase {
  inputs: KeyedScalars;
  outputs: KeyedScalars;
}
export interface KeyedScalars {
  [k: string]: Scalar;
}
export interface ViewList {
  key: Key;
  label: Label;
  entity: Key;
  type: "list";
  /**
   * @minItems 1
   */
  columns: [Key, ...Key[]];
  sort?: Sort[];
  filters?: Filter[];
  totals?: Key[];
  provenance?: Provenance;
}
export interface Sort {
  field: Key;
  direction: "asc" | "desc";
}
/**
 * `value` compares with a constant. `relativeDays` compares a date with today plus that many days.
 */
export interface Filter {
  field: Key;
  op: "eq" | "ne" | "lt" | "le" | "gt" | "ge" | "in" | "contains" | "isEmpty" | "isNotEmpty";
  value?: string | number | boolean | null | Scalar[];
  relativeDays?: number;
}
/**
 * Columns are the workflow's states; dragging a card attempts a transition (R-20).
 */
export interface ViewBoard {
  key: Key;
  label: Label;
  entity: Key;
  type: "board";
  workflow: Key;
  /**
   * @minItems 1
   */
  cardFields: [Key, ...Key[]];
  filters?: Filter[];
  provenance?: Provenance;
}
export interface Form {
  key: Key;
  label: Label;
  entity: Key;
  /**
   * @minItems 1
   */
  sections: [FormSection, ...FormSection[]];
  provenance?: Provenance;
}
export interface FormSection {
  key: Key;
  label: Label;
  /**
   * @minItems 1
   */
  fields: [Key, ...Key[]];
}
export interface Dashboard {
  key: Key;
  label: Label;
  /**
   * @minItems 1
   */
  widgets: [Widget, ...Widget[]];
  provenance?: Provenance;
}
/**
 * `field` is required by every aggregate but count.
 */
export interface WidgetKpi {
  key: Key;
  label: Label;
  type: "kpi";
  entity: Key;
  aggregate: Aggregate;
  field?: Key;
  filters?: Filter[];
  provenance?: Provenance;
}
/**
 * `field` is required by every aggregate but count.
 */
export interface WidgetChart {
  key: Key;
  label: Label;
  type: "bar" | "line";
  entity: Key;
  aggregate: Aggregate;
  field?: Key;
  groupBy: Key;
  filters?: Filter[];
  provenance?: Provenance;
}
/**
 * One of the four roles of R-17. `fieldLevel` 1 lets the role see sensitive fields.
 */
export interface Role {
  key: "owner" | "staff" | "accountant" | "viewer";
  label: Label;
  fieldLevel: FieldLevel;
  permissions: Permission[];
  provenance?: Provenance;
}
export interface Permission {
  entity: Key;
  actions: ("read" | "create" | "update" | "delete" | "export" | "import" | "revert")[];
  /**
   * `own` limits the role to records it created (R-17).
   */
  rowScope: "all" | "own";
}
export interface Workflow {
  key: Key;
  label: Label;
  entity: Key;
  stateField: Key;
  initialState: Key;
  /**
   * @minItems 1
   */
  states: [WorkflowState, ...WorkflowState[]];
  transitions: WorkflowTransition[];
  provenance?: Provenance;
}
export interface WorkflowState {
  key: Key;
  label: Label;
  colour?: Colour;
  provenance?: Provenance;
}
/**
 * `key` is the action named in POST /api/e/{entity}/{id}/transition. `condition`, if present, must be true for the transition to go through.
 */
export interface WorkflowTransition {
  key: Key;
  label: Label;
  /**
   * @minItems 1
   */
  from: [Key, ...Key[]];
  to: Key;
  /**
   * @minItems 1
   */
  roles: ["owner" | "staff" | "accountant" | "viewer", ...("owner" | "staff" | "accountant" | "viewer")[]];
  condition?: Expr;
  provenance?: Provenance;
}
/**
 * A date rule checked daily. It fires `offsetDays` after `dateField` (negative means before).
 */
export interface Reminder {
  key: Key;
  label: Label;
  entity: Key;
  dateField: Key;
  offsetDays: number;
  filters?: Filter[];
  /**
   * @minItems 1
   */
  roles: ["owner" | "staff" | "accountant" | "viewer", ...("owner" | "staff" | "accountant" | "viewer")[]];
  message: Label;
  provenance?: Provenance;
}
/**
 * Every change except computed fields is recorded (R-18). Omit retentionMonths to keep history indefinitely.
 */
export interface History {
  retentionMonths?: number;
  provenance?: Provenance;
}
/**
 * An entity's source layout. Export (R-22) and re-import (R-23) both use it. The order of `columns` is the column order.
 */
export interface EntityMapping {
  entity: Key;
  /**
   * @minItems 1
   */
  sources: [MappingSource, ...MappingSource[]];
  headerRow: number;
  /**
   * @minItems 1
   */
  columns: [MappingColumn, ...MappingColumn[]];
  /**
   * @minItems 1
   */
  keyColumns: [Key, ...Key[]];
  /**
   * The total row the sheet had, so an export can write it again (R-22).
   */
  totals?: MappingTotal[];
  provenance?: Provenance;
}
/**
 * `period` is set when the sheet is one tab of a merged series (R-8), as YYYY-MM, YYYY-Qn or YYYY.
 */
export interface MappingSource {
  sheet: string;
  range?: A1Range;
  period?: string;
}
/**
 * `header` is the original header text, kept as it was for export.
 */
export interface MappingColumn {
  header: string;
  field: Key;
  /**
   * Its letter in the sheet. Without it, columns run on from the source's first column.
   */
  column?: string;
}
export interface MappingTotal {
  field: Key;
  function: "sum" | "average" | "count" | "counta" | "max" | "min" | "product";
}
