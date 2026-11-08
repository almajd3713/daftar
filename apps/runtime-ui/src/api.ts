/** The Runtime's API (C-7, docs/studio-api.md), and the few shapes of failure a screen has to tell apart. */
import type { App, Calculator, CalculatorOutput, Dashboard, Entity, Form, Label, Permission, ViewBoard, ViewList, Workflow } from "@daftar/spec/types";
import { useCallback, useEffect, useState } from "react";

export interface Status {
  needsSetup: boolean;
  app: Pick<App, "name" | "locales" | "defaultLocale">;
  /** Only in the Studio's preview, where nobody knows the password. */
  preview?: true;
}

/** A calculator as a role sees it: never its formulas, and only the outputs this role may read, which can be none. */
export type MetaCalculator = Omit<Calculator, "cells" | "testCases" | "outputs"> & { outputs: CalculatorOutput[] };

export interface Meta {
  specVersion: string;
  app: App;
  user: { username: string; role: string };
  permissions: Permission[];
  entities: Entity[];
  views: (ViewList | ViewBoard)[];
  forms: Form[];
  workflows: Workflow[];
  /** Only what this role can see of each, and none left with no widgets. */
  dashboards: Dashboard[];
  calculators: MetaCalculator[];
}

/** One group of a chart. `key` is null for rows with no value, and `value` for a sum over only blanks. */
export interface AggregateGroup {
  key: string | number | boolean | null;
  value: number | null;
  /** A link's name, when this person may read it. */
  label?: string;
}

export interface AggregateResult {
  groups: AggregateGroup[];
  /** There were more than the server returns. */
  truncated: boolean;
}

/** Each output is its value, or `{error}` with the Excel error its formula gave. */
export interface CalcResult {
  outputs: Record<string, unknown>;
}

export const canDo = (meta: Meta, entity: string, action: string): boolean => meta.permissions.some((item) => item.entity === entity && item.actions.includes(action as never));

/** A record, as every route returns it: its fields, plus these. */
export interface Row {
  _id: string;
  _name: string;
  _version: number;
  _labels?: Record<string, string>;
  _errors?: Record<string, string>;
  [field: string]: unknown;
}

export interface ListResult {
  rows: Row[];
  total: number;
  page: number;
  pageSize: number;
  totals: Record<string, number | null>;
}

/** One line of a record's history, newest first. A field this person can't see has `*` for both its values. */
export interface AuditChange {
  id: string;
  at: string;
  actor: string;
  source: string;
  op: string;
  changes: Record<string, [unknown, unknown]>;
  batchId?: string;
  revertOf?: string;
  revertedBy?: string;
  /** On a deletion: what the record was called, since it has gone. */
  name?: string | null;
}

/** A deletion nobody has undone. `changeId` is what restoring it reverts. */
export interface DeletedRecord {
  changeId: string;
  recordId: string;
  name: string | null;
  at: string;
  actor: string;
}

export interface DeletedList {
  rows: DeletedRecord[];
  total: number;
  page: number;
  pageSize: number;
}

export type Problem =
  /** The server's words for each field, to show under it. */
  | { kind: "fields"; fields: Record<string, Label> }
  /** The server's own sentence: a stale write, a refused action, a wrong login, a service that's down. */
  | { kind: "reason"; status: number; reason: Label }
  | { kind: "signedOut" }
  | { kind: "missing" }
  | { kind: "refused" }
  /** The server couldn't be reached, or answered in a way a person can't act on. */
  | { kind: "failed" };

export class ApiProblem extends Error {
  constructor(readonly problem: Problem) {
    super(problem.kind);
  }
}

export function problemOf(error: unknown): Problem {
  return error instanceof ApiProblem ? error.problem : { kind: "failed" };
}

/** What each failure means, from the table in the contract. */
export function classify(status: number, body: unknown): Problem {
  const data = (body ?? {}) as { fields?: Record<string, Label>; reason?: Label };
  if (status === 400 && data.fields) return { kind: "fields", fields: data.fields };
  if (data.reason) return { kind: "reason", status, reason: data.reason };
  if (status === 401) return { kind: "signedOut" };
  if (status === 403) return { kind: "refused" };
  if (status === 404) return { kind: "missing" };
  return { kind: "failed" };
}

let signedOut: () => void = () => undefined;

/** Any call that finds the session gone sends the person to login, and the address keeps their page. */
export function whenSignedOut(handler: () => void): void {
  signedOut = handler;
}

export async function call<Result>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<Result> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiProblem({ kind: "failed" });
  }
  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }
  if (response.ok) return data as Result;
  const problem = classify(response.status, data);
  if (problem.kind === "signedOut") signedOut();
  throw new ApiProblem(problem);
}

export interface Fetched<Result> {
  data: Result | undefined;
  problem: Problem | undefined;
  loading: boolean;
  reload: () => void;
}

/** Reads a path, and again when it changes. What it last had stays on screen until the new answer comes. */
export function useFetch<Result>(path: string | null): Fetched<Result> {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{ data?: Result; problem?: Problem; loading: boolean }>({ loading: path !== null });
  useEffect(() => {
    if (path === null) return undefined;
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true }));
    call<Result>("GET", path, undefined, controller.signal).then(
      (data) => setState({ data, loading: false }),
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ problem: problemOf(error), loading: false });
      },
    );
    return () => controller.abort();
  }, [path, version]);
  const reload = useCallback(() => setVersion((current) => current + 1), []);
  return { data: state.data, problem: state.problem, loading: state.loading, reload };
}

/** Reads several paths as one answer, for a page made of them. As above, what it last had stays until all have answered. */
export function useFetchAll<Result>(paths: readonly string[]): Fetched<Result[]> {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{ data?: Result[]; problem?: Problem; loading: boolean }>({ loading: true });
  // Paths are built afresh on each render, so it's what they say that decides whether to read again.
  const joined = paths.join("\n");
  useEffect(() => {
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true }));
    Promise.all(joined.split("\n").map((path) => call<Result>("GET", path, undefined, controller.signal))).then(
      (data) => setState({ data, loading: false }),
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ problem: problemOf(error), loading: false });
      },
    );
    return () => controller.abort();
  }, [joined, version]);
  const reload = useCallback(() => setVersion((current) => current + 1), []);
  return { data: state.data, problem: state.problem, loading: state.loading, reload };
}
