# Daftar app spec

`schema/daftar.spec.schema.json` is the one contract for `daftar.spec.json`. Everything here derives from it:

- `src/generated/spec.ts`: TypeScript types. Run `pnpm generate` after editing the schema; a test fails if they drift.
- `src/validate.ts` and `python/daftar_spec/`: validators that report the same error paths.
- `examples/`: hand-written specs, one per workbook kind. Later packages use them as fixtures.
- `fixtures/invalid-cases.json`: invalid specs with their expected error paths, run in both languages.

The schema uses `discriminator` on tagged unions, which is why errors point at the one branch that applies. Both validators honour it.

JSON Schema can't check cross-references, such as whether a view's `entity` exists. The spec loader must check those.
