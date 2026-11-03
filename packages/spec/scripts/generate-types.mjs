// Generates src/generated/spec.ts from the schema. A test fails if the file is out of date.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";

const here = (path) => fileURLToPath(new URL(path, import.meta.url));

export async function generateTypes() {
  const schema = JSON.parse(readFileSync(here("../schema/daftar.spec.schema.json"), "utf8"));
  return compile(schema, "DaftarSpec", {
    additionalProperties: false,
    bannerComment: "// Generated from schema/daftar.spec.schema.json by `pnpm generate`. Do not edit.",
    style: { printWidth: 120 },
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(here("../src/generated/spec.ts"), await generateTypes());
}
