/** Reading a record's history: what each line was, what can still be undone, and which names it needs. */
import type { Entity, Field } from "@daftar/spec/types";

import type { AuditChange } from "./api.js";

/**
 * An edit or a step can be undone, unless it already has been. Undoing a creation would delete the record under a
 * label that doesn't say so, and deleting has its own button. Undoing an undo is something the server refuses.
 */
export const canUndo = (change: AuditChange): boolean => !change.revertedBy && (change.op === "update" || change.op === "transition");

/** The newest deletion that hasn't been undone: what restoring a deleted record would reverse. */
export function deletionOf(changes: readonly AuditChange[]): AuditChange | undefined {
  return changes.find((change) => change.op === "delete" && !change.revertedBy);
}

/** An undone deletion lists every field going from nothing to its value. What happened is simpler than that. */
export function isRestoration(change: AuditChange, changes: readonly AuditChange[]): boolean {
  return change.op === "revert" && changes.find((item) => item.id === change.revertOf)?.op === "delete";
}

export interface SplitChanges {
  /** Each field this person can see, with its old and new value. */
  shown: { field: Field; from: unknown; to: unknown }[];
  /** A field left out of `/api/meta` has no label to show. That it changed is still true, and worth saying. */
  hidden: boolean;
}

export function splitChanges(entity: Entity, change: AuditChange): SplitChanges {
  const shown: SplitChanges["shown"] = [];
  let hidden = false;
  for (const [key, [from, to]] of Object.entries(change.changes)) {
    const field = entity.fields.find((item) => item.key === key);
    if (field) shown.push({ field, from, to });
    else hidden = true;
  }
  return { shown, hidden };
}

export const linkPath = (target: string, id: string): string => `${encodeURIComponent(target)}/${encodeURIComponent(id)}`;

/**
 * History holds a link's id, and a person needs its name. These are the records to ask for it. A creation or a
 * deletion is shown as one word, with no values, so those need none.
 */
export function linksIn(entity: Entity, changes: readonly AuditChange[]): string[] {
  const found = new Set<string>();
  for (const change of changes) {
    if (change.op === "create" || change.op === "delete" || isRestoration(change, changes)) continue;
    for (const { field, from, to } of splitChanges(entity, change).shown) {
      if (field.type !== "link") continue;
      for (const id of [from, to]) {
        if (typeof id === "string" && id) found.add(linkPath(field.target, id));
      }
    }
  }
  return [...found];
}
