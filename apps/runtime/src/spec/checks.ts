/** What the JSON Schema can't see: that every reference in a spec points at something real. */
import type { DaftarSpec, Entity, Expr, Field } from "@daftar/spec/types";

function duplicates(items: { key: string }[], where: string, problems: string[]): void {
  const seen = new Set<string>();
  for (const { key } of items) {
    if (seen.has(key)) problems.push(`${where}: duplicate key ${key}`);
    seen.add(key);
  }
}

function fieldsOfExpr(expr: Expr, found: { own: Set<string>; via: Set<string> }): void {
  if (expr.kind === "field") found.own.add(expr.field);
  if (expr.kind === "related" || expr.kind === "rollup") found.via.add(expr.via);
  if (expr.kind === "op" || expr.kind === "call") expr.args.forEach((arg) => fieldsOfExpr(arg, found));
}

function checkEntity(entity: Entity, entities: Map<string, Entity>, problems: string[]): void {
  const where = `entity ${entity.key}`;
  duplicates(entity.fields, where, problems);
  const fields = new Map(entity.fields.map((field) => [field.key, field]));
  const need = (key: string | undefined, what: string): void => {
    if (key !== undefined && !fields.has(key)) problems.push(`${where}: ${what} ${key} isn't a field`);
  };
  need(entity.titleField, "titleField");
  if (entity.naming.type === "field") need(entity.naming.field, "naming field");
  entity.searchFields?.forEach((key) => need(key, "search field"));
  need(entity.period?.field, "period field");
  for (const field of entity.fields) checkField(entity, field, fields, entities, problems);
}

function checkField(entity: Entity, field: Field, fields: Map<string, Field>, entities: Map<string, Entity>, problems: string[]): void {
  const where = `entity ${entity.key}, field ${field.key}`;
  if (field.type === "link" && !entities.has(field.target)) problems.push(`${where}: target ${field.target} isn't an entity`);
  if (field.type === "child") {
    const target = entities.get(field.target);
    const via = target?.fields.find((item) => item.key === field.via);
    if (!target) problems.push(`${where}: target ${field.target} isn't an entity`);
    else if (via?.type !== "link" || via.target !== entity.key) problems.push(`${where}: ${field.via} isn't a link back to ${entity.key}`);
  }
  if (field.type === "choice" || field.type === "multichoice") {
    duplicates(field.choices, where, problems);
  }
  if (field.type !== "computed") return;
  for (const dep of field.computed.deps) {
    const [first] = dep.split(".");
    if (!fields.has(first as string)) problems.push(`${where}: dep ${dep} isn't a field`);
  }
  if (field.computed.eval === "translated") {
    const found = { own: new Set<string>(), via: new Set<string>() };
    fieldsOfExpr(field.computed.expr, found);
    for (const key of [...found.own, ...found.via]) {
      if (!fields.has(key)) problems.push(`${where}: expression reads ${key}, which isn't a field`);
    }
  }
}

export function checkReferences(spec: DaftarSpec): string[] {
  const problems: string[] = [];
  duplicates(spec.entities, "entities", problems);
  duplicates(spec.views, "views", problems);
  duplicates(spec.forms, "forms", problems);
  duplicates(spec.dashboards, "dashboards", problems);
  duplicates(spec.roles, "roles", problems);
  duplicates(spec.calculators, "calculators", problems);
  duplicates(spec.workflows, "workflows", problems);
  duplicates(spec.reminders, "reminders", problems);
  const entities = new Map(spec.entities.map((entity) => [entity.key, entity]));
  spec.entities.forEach((entity) => checkEntity(entity, entities, problems));

  const fieldsOf = (key: string, where: string): Set<string> => {
    const entity = entities.get(key);
    if (!entity) {
      problems.push(`${where}: ${key} isn't an entity`);
      return new Set();
    }
    return new Set(entity.fields.map((field) => field.key));
  };
  const needAll = (keys: (string | undefined)[], known: Set<string>, where: string): void => {
    if (!known.size) return;
    for (const key of keys) {
      if (key !== undefined && !known.has(key)) problems.push(`${where}: ${key} isn't a field`);
    }
  };

  const workflows = new Map(spec.workflows.map((workflow) => [workflow.key, workflow]));
  for (const view of spec.views) {
    const where = `view ${view.key}`;
    const known = fieldsOf(view.entity, where);
    needAll((view.filters ?? []).map((item) => item.field), known, where);
    if (view.type === "list") {
      needAll(view.columns, known, where);
      needAll((view.sort ?? []).map((item) => item.field), known, where);
      needAll(view.totals ?? [], known, where);
    } else {
      needAll(view.cardFields, known, where);
      if (workflows.get(view.workflow)?.entity !== view.entity) problems.push(`${where}: workflow ${view.workflow} isn't on ${view.entity}`);
    }
  }
  for (const form of spec.forms) {
    const known = fieldsOf(form.entity, `form ${form.key}`);
    form.sections.forEach((section) => needAll(section.fields, known, `form ${form.key}`));
  }
  for (const dashboard of spec.dashboards) {
    for (const widget of dashboard.widgets) {
      const where = `dashboard ${dashboard.key}, widget ${widget.key}`;
      const known = fieldsOf(widget.entity, where);
      needAll([widget.field, widget.type === "kpi" ? undefined : widget.groupBy], known, where);
      needAll((widget.filters ?? []).map((item) => item.field), known, where);
    }
  }
  for (const role of spec.roles) role.permissions.forEach((item) => fieldsOf(item.entity, `role ${role.key}`));
  for (const workflow of spec.workflows) {
    const where = `workflow ${workflow.key}`;
    duplicates(workflow.states, where, problems);
    duplicates(workflow.transitions, where, problems);
    const known = fieldsOf(workflow.entity, where);
    needAll([workflow.stateField], known, where);
    const states = new Set(workflow.states.map((state) => state.key));
    const field = entities.get(workflow.entity)?.fields.find((item) => item.key === workflow.stateField);
    if (field && field.type !== "choice") problems.push(`${where}: state field isn't a choice`);
    if (field?.type === "choice") {
      const choices = new Set(field.choices.map((choice) => choice.key));
      for (const state of states) if (!choices.has(state)) problems.push(`${where}: state ${state} isn't a choice of the field`);
    }
    if (!states.has(workflow.initialState)) problems.push(`${where}: initial state isn't a state`);
    for (const transition of workflow.transitions) {
      for (const state of [...transition.from, transition.to]) {
        if (!states.has(state)) problems.push(`${where}, transition ${transition.key}: ${state} isn't a state`);
      }
    }
  }
  for (const reminder of spec.reminders) {
    needAll([reminder.dateField, ...(reminder.filters ?? []).map((item) => item.field)], fieldsOf(reminder.entity, `reminder ${reminder.key}`), `reminder ${reminder.key}`);
  }
  for (const mapping of spec.mapping) {
    const where = `mapping of ${mapping.entity}`;
    const known = fieldsOf(mapping.entity, where);
    const columns = mapping.columns.map((column) => column.field);
    needAll(columns, known, where);
    for (const key of mapping.keyColumns) {
      if (!columns.includes(key)) problems.push(`${where}: key column ${key} isn't in its columns`);
    }
  }
  for (const calculator of spec.calculators) {
    const where = `calculator ${calculator.key}`;
    duplicates(calculator.inputs, where, problems);
    duplicates(calculator.outputs, where, problems);
    const cells = new Set(calculator.cells.map((cell) => `${cell.sheet}!${cell.ref}`));
    for (const port of [...calculator.inputs, ...calculator.outputs]) {
      if (!cells.has(`${port.sheet}!${port.cell}`)) problems.push(`${where}: ${port.key} points at a cell the model doesn't have`);
    }
  }
  return problems;
}
