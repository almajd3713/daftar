import { readFileSync } from "node:fs";

import type { DaftarSpec } from "@daftar/spec/types";
import { formatErrors, validateSpec } from "@daftar/spec";

import { checkReferences } from "./checks.js";

export class SpecLoadError extends Error {}

export function parseSpec(data: unknown): DaftarSpec {
  const result = validateSpec(data);
  if (!result.valid) throw new SpecLoadError(`Invalid spec:\n${formatErrors(result.errors)}`);
  const problems = checkReferences(result.spec);
  if (problems.length) throw new SpecLoadError(`Invalid spec:\n${problems.join("\n")}`);
  return result.spec;
}

export function loadSpec(path: string): DaftarSpec {
  return parseSpec(JSON.parse(readFileSync(path, "utf8")));
}
