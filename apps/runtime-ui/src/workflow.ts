/** What a workflow offers a person on a record, and what a refused step can point them at. */
import type { Entity, Expr, Field, Workflow, WorkflowTransition } from "@daftar/spec/types";

export function workflowOf(workflows: readonly Workflow[], entity: string): Workflow | undefined {
  return workflows.find((workflow) => workflow.entity === entity);
}

/**
 * The steps a record offers, by `from` and `roles` as the contract says. A condition isn't checked here: the server
 * judges it, and explains a refusal. They come furthest along first, so the first is the one to make primary: a
 * person is more often moving a job on than sending it back.
 */
export function offeredSteps(workflow: Workflow, state: unknown, role: string): WorkflowTransition[] {
  const place = (key: string): number => workflow.states.findIndex((item) => item.key === key);
  return workflow.transitions
    .filter((step) => (step.from as readonly string[]).includes(String(state)) && (step.roles as readonly string[]).includes(role))
    .sort((a, b) => place(b.to) - place(a.to));
}

/**
 * What moving a card to another state attempts. A step this role may not take still counts, so the server can say why
 * not, rather than the card just refusing to move.
 */
export function stepBetween(workflow: Workflow, from: string, to: string, role: string): WorkflowTransition | undefined {
  const steps = workflow.transitions.filter((step) => (step.from as readonly string[]).includes(from) && step.to === to);
  return steps.find((step) => (step.roles as readonly string[]).includes(role)) ?? steps[0];
}

/** A state no step leaves, such as delivered. It only ever grows. */
export function isEndState(workflow: Workflow, state: string): boolean {
  return !workflow.transitions.some((step) => (step.from as readonly string[]).includes(state));
}

function keysIn(expr: Expr): string[] {
  switch (expr.kind) {
    case "field":
      return [expr.field];
    case "related":
    case "rollup":
      return [expr.via];
    case "op":
    case "call":
      return expr.args.flatMap(keysIn);
    default:
      return [];
  }
}

/**
 * What a condition reads, so a refusal can say where to look. The server's sentence only says that the conditions
 * aren't met, and a spec has no words of its own for them. A field this person can't see isn't named.
 */
export function fieldsToCheck(entity: Entity, step: WorkflowTransition): Field[] {
  if (!step.condition) return [];
  const keys = new Set(keysIn(step.condition));
  return entity.fields.filter((field) => keys.has(field.key));
}
