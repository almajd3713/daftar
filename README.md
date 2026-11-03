# Daftar

> **Demo project.** Daftar is a portfolio project and is still being built. It isn't ready for production use yet. No accuracy figure is published yet; one will appear here only once it has been measured on a frozen test set.

Daftar turns a small firm's own messy Excel workbook into a shared app: lists, forms, dashboards, roles and change history, in French and Arabic. It runs on the firm's machine or in Algeria, and the data can always go back to Excel.

The plan is in [`docs/03-blueprint.md`](docs/03-blueprint.md). The research notes it cites are kept private.

## Layout

| Path | What it holds |
|---|---|
| `packages/spec` | The app spec: one JSON Schema, TypeScript types and validators in both languages, and example specs |
| `apps/worker` | The Python worker: reads, analyses, exports and diffs workbooks |
| `compose.dev.yaml` | Dev stack: Postgres and the worker image, with LibreOffice installed |

## Development

You need Node 26, pnpm 11, Python 3.12 with uv, and Docker.

```sh
pnpm install
uv sync

# TypeScript checks
pnpm -r lint
pnpm -r typecheck
pnpm -r test

# Python checks
uv run ruff check
uv run mypy
uv run pytest

# Validate a spec. Exit codes: 0 valid, 2 unreadable, 3 invalid.
uv run python -m daftar_spec packages/spec/examples/*.spec.json

# Dev stack: fill in the blanks in .env first
cp .env.example .env
docker compose -f compose.dev.yaml up --build
```

After editing the spec schema, run `pnpm --filter @daftar/spec generate` to refresh the TypeScript types.

## Rules for contributors

- **No client data in this repo.** Workbooks are git-ignored. Test fixtures must be synthetic or carry a clear licence, and they go in `eval/workbooks/` or a `tests/fixtures/workbooks/` folder.
- **No SQL built from formulas or labels.** Database identifiers come only from spec keys, and values are always parameters.
- **Dependencies stay permissive** (MIT, Apache or BSD).
- **One branch per work package**, with short imperative commit messages.

## Licence

[AGPL-3.0](LICENSE).
