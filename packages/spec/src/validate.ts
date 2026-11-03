import { readFileSync } from "node:fs";

import { Ajv2020 } from "ajv/dist/2020.js";
import type { ErrorObject, ValidateFunction } from "ajv";

import type { DaftarSpec } from "./generated/spec.js";

/** One problem in a spec. `path` reads like `entities[0].fields[2].key`. */
export interface SpecError {
  path: string;
  message: string;
}

export type SpecValidation = { valid: true; spec: DaftarSpec } | { valid: false; errors: SpecError[] };

// src/ and dist/ sit at the same depth, so this holds before and after the build.
const schemaUrl = new URL("../schema/daftar.spec.schema.json", import.meta.url);

let compiled: ValidateFunction | undefined;

export function loadSchema(): Record<string, unknown> {
  return JSON.parse(readFileSync(schemaUrl, "utf8")) as Record<string, unknown>;
}

function validator(): ValidateFunction {
  // strictRequired is off because `then: {required: [...]}` names properties defined on the parent.
  compiled ??= new Ajv2020({
    allErrors: true,
    allowUnionTypes: true,
    discriminator: true,
    strict: true,
    strictRequired: false,
  }).compile(loadSchema());
  return compiled;
}

function formatPath(pointer: string, extra?: string): string {
  const parts = pointer
    .split("/")
    .slice(1)
    .map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"));
  if (extra !== undefined) parts.push(extra);
  let out = "";
  for (const part of parts) {
    if (/^[0-9]+$/.test(part)) out += `[${part}]`;
    else out += out ? `.${part}` : part;
  }
  return out || "(root)";
}

function toSpecError(error: ErrorObject): SpecError | undefined {
  const params = error.params as Record<string, unknown>;
  switch (error.keyword) {
    case "if":
      return undefined; // The errors from `then` are the real ones.
    case "required":
      return { path: formatPath(error.instancePath, String(params.missingProperty)), message: "required property is missing" };
    case "additionalProperties":
      return { path: formatPath(error.instancePath, String(params.additionalProperty)), message: "unknown property" };
    case "discriminator": {
      const path = formatPath(error.instancePath, String(params.tag));
      return params.error === "tag"
        ? { path, message: "required property is missing" }
        : { path, message: "has a value this schema doesn't allow" };
    }
    default:
      return { path: formatPath(error.instancePath), message: error.message ?? error.keyword };
  }
}

/** Check a spec against the schema. Errors are sorted by path. */
export function validateSpec(spec: unknown): SpecValidation {
  const validate = validator();
  if (validate(spec)) return { valid: true, spec: spec as DaftarSpec };
  const errors = (validate.errors ?? []).map(toSpecError).filter((error) => error !== undefined);
  errors.sort((a, b) => (a.path === b.path ? 0 : a.path < b.path ? -1 : 1));
  return { valid: false, errors };
}

export function formatErrors(errors: SpecError[]): string {
  return errors.map((error) => `${error.path}: ${error.message}`).join("\n");
}
