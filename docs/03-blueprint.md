# Build Daftar: turn a small firm's real Excel workbook into a working app

Created 2026-11-03 · no git repo yet (WP-1 creates it) · work branch `main` until the repo exists, then one branch per work package

## Executor guide

This plan gives you the goal, the required behaviour, the contracts and the checks. How to build it is up to you.

1. Read this whole plan, `docs/01-refined-idea.md` (intent and decisions) and the sections of `docs/02-research.md` that your package names. Before you write code for a package, read the files and the precedent it points to.
2. Follow the repository's conventions once WP-1 sets them, and the precedent each package names.
3. Within a work package, make your own implementation decisions: structure, names, helpers and tests. Record any decision a reviewer might question, and any surprise, as one line in **Log**.
4. Stop and ask before you change anything under **Contracts**, any behaviour under **Requirements**, or the scope. Also stop if the code contradicts this plan.
5. A package is done when its **Done when** checks and the project checks under **Validation** pass. Then tick it in **Progress** and commit with a short imperative message.

## Goal

**Daftar** turns a small firm's own messy Excel workbook into a shared app: lists, forms, dashboards, roles and change history, in French and Arabic. It runs on the firm's machine or in Algeria, and the data can always go back to Excel.

- **v1 operator:** the developer, during pilots and freelance delivery. The review screen is built so an owner could later use it alone.
- **What sets it apart, per the research:**
  - it understands messy workbooks instead of demanding clean ones;
  - formulas give the same results as Excel;
  - each finding is reviewed against the cells it came from;
  - it deploys locally;
  - it round-trips to .xlsx.
- **Portfolio proof:** a published, measured understanding accuracy on a labelled workbook set, plus one pilot case study.

## Requirements

**Reading**
- **R-1**: Daftar accepts .xlsx, .xlsm, .xls, .ods and .csv files up to 25 MB and 1,000,000 non-empty cells. .xls and .ods files are converted with LibreOffice **without recalculating**, so Excel's stored formula results survive the conversion. Password-protected, corrupt or oversized files are rejected with a clear French/Arabic message and leave nothing behind.
- **R-2**: Reading captures, per sheet:
  - values, Excel's stored formula results, formulas, number formats
  - fill and font colour, bold, merged cells
  - validation lists, conditional-format rules, comments
  - defined names, Excel Tables, hidden and protection state

  Nothing is dropped silently. Pivots, charts, images, shapes, macros and external links each become an `unsupported` finding. Macros never run.

**Understanding**
- **R-3**: Every sheet gets exactly one outcome:
  - `register`
  - `ledger`
  - `formulaModel`
  - `tracker`
  - `referenceList` (a lookup tab that feeds a relation)
  - `notConverted`, with a reason (form, report, chart or pivot only, empty, out of scope)
- **R-4**: Table detection:
  - It finds several tables on one sheet, and headers that aren't on row 1.
  - Notes and titles above a header are excluded from the data.
  - Multi-row headers are flattened into one label per field.
  - Totals and subtotal rows are excluded from the data and proposed as aggregates.
- **R-5**: Field types come from the C-3 set. Daftar recognises:
  - DZD amounts
  - Algerian phone numbers (`+213…` or `0[5-7]…`)
  - dd/mm/yyyy and Excel serial dates
  - validation lists, which become choices

  Low-cardinality text columns are proposed as choices.
- **R-6**: When one name is retyped across rows or sheets with spelling variants, Daftar proposes one entity and lists the variants. It never merges on its own.
- **R-7**: Relations are proposed from lookup formulas (VLOOKUP, XLOOKUP, INDEX/MATCH; high confidence) and from value inclusion between key columns (medium confidence at most).
- **R-8**: Tabs with the same columns whose names give a period (French, Arabic or English month names, or dates) are proposed as one entity with a period field.
- **R-9**: Formulas and formatting become proposals:
  - A formula copied down a column becomes a computed field.
  - A sheet whose input cells feed formula chains to output cells becomes a calculator.
  - Conditional formats or fills on a status-like column become choices with colours.
- **R-10**: Every finding carries its evidence ranges, a confidence level (high, medium or low) and an explanation in French and Arabic. Code builds the explanation from facts: counts, sheet names, cells. The language model may reword it but never adds facts.
- **R-11**: Analysis also works with no language model at all, using rules only. Names then fall back to the cleaned header text. The same input with the same model gives the same analysis, thanks to caching, temperature 0, and fixed seeds for vote sampling.

**Review (Studio)**
- **R-12**: The review screen shows the sheet grid with each finding's evidence highlighted, next to the findings list (low confidence first). Each finding can be accepted, edited or rejected.
  - Nothing reaches the spec unless it was accepted.
  - High-confidence findings start pre-selected, but still need an explicit accept; bulk accept is allowed.
- **R-13**: The Studio switches between French and Arabic with full right-to-left layout. The wording is written for a shop owner, not a developer.
- **R-14**: Before export, the operator can preview the generated app running on the workbook's own data.
- **R-15**: When an analysis is rerun on the same workbook, or on an updated version, earlier decisions are re-applied by matching their provenance. Decisions that no longer match are shown as conflicts.

**Runtime (the client app)**
- **R-16**: The runtime renders any valid spec:
  - per entity: a list (sort, filter, search, column totals), a form (validation, French/Arabic labels) and a detail page with history;
  - a board view for entities with a workflow;
  - dashboards with KPI tiles and simple charts;
  - calculators.
- **R-17**: Four default roles:
  - owner: everything;
  - staff: create and edit;
  - accountant: read and export;
  - viewer: read only.

  The spec can limit an entity to a role's own records, and can hide sensitive fields (cost, margin) from staff and viewers. Hidden fields are masked in exports and history too.
- **R-18**: Every create, update, delete, import and transition is recorded with:
  - who did it and when;
  - its source (UI, import, workflow or system);
  - the per-field old and new values.

  Each record has a history timeline. The owner can revert one change or undo a whole import batch. Computed fields aren't recorded.
- **R-19**: Computed fields recompute on every write, and calculators evaluate on demand.
  - On the imported data, results must match Excel's stored results within a relative tolerance of 1e-9.
  - A formula outside the translatable set runs in the engine.
  - A formula the engine can't evaluate is flagged as unsupported during review; it is never silently wrong.
- **R-20**: Workflow entities allow only the transitions the spec defines. Dragging a card on the board attempts that transition and shows why when it's refused. Reminders come from date rules that are checked daily, and appear in the app.
- **R-21**: Locale handling:
  - `fr-DZ` and `ar-DZ` locales, with Western digits by default;
  - DZD formatted as "1 234 567,89 DA" or "1.234.567,89 د.ج.";
  - Algerian month names in Arabic (جانفي…);
  - the week starts on Saturday;
  - the time zone is Africa/Algiers.

**Round trip and handover**
- **R-22**: The owner or the accountant can export to .xlsx at any time. The file follows the original layout: one sheet per entity, the original header text and column order, and monthly tabs again where they came from monthly tabs. Computed columns keep their formulas, with results filled in, and Arabic exports use right-to-left sheets.
- **R-23**: Re-importing an edited workbook:
  - Rows are matched on their key columns.
  - A diff shows each entity's added, changed and missing rows.
  - The chosen changes are applied as one batch that can be undone.
  - Rows missing from the workbook are never deleted automatically.
- **R-24**: The runtime exports a processing register built from the spec: personal-data entities and fields, roles, the retention declared per entity, and the processor. Change history serves as the automated log that Law 25-11 requires, for writes: art. 41 bis 3 also names consultation and extraction, which R-28 adds.
- **R-28** (added 2026-11-07, on the user's word to use judgement here): The register's periods are kept, not only printed, because keeping personal data past the declared period is an offence (Law 18-07 art. 65):
  - A daily check finds records of a `personalData` entity past their `retention`, and history values past `history.retentionMonths`. History values are removed automatically. Records wait on an owner's page and a reminder, and go when the owner confirms.
  - An owner can erase one record for good, to answer a request under art. 35 within its 10 days.
  - Erasing removes the values everywhere the app holds them and keeps the log line: what was done, by whom and when. That line is what art. 41 bis 3 asks for, and it doesn't ask for the values.
  - Reads and exports of personal data are logged, without values.
- **R-25**: `daftar bundle` builds a deployable folder (C-8) with no default credentials. On first start, the owner creates their account and the accepted import data is loaded. Backup and restore are single commands, and a restore test is part of the handover.

**Measuring**
- **R-26**: `daftar census` counts workbook features over folders of files. The feature list is in research notes §(b) and §(c).
- **R-27**: `daftar eval` scores the analysis against labels (C-6).
  - Metrics: the research measure table in `02-research.md`, each with a workbook-level bootstrap 95% CI, broken down by stratum.
  - The report records the git SHA, the model and the quantisation.
  - The test split is frozen and never used for tuning.

## Out of scope

- Running VBA, live two-way sync with Excel, keeping pivots or charts as they are, several firms on one server, printable documents: `01-refined-idea.md` "Not in v1".
- Owners converting their own workbooks without the operator: v2. The review UX must not block it.
- Dynamic-array functions (XLOOKUP spill, FILTER, UNIQUE, SORT), LET and LAMBDA: v1.1, unless OQ-3 says otherwise.
- Accounting entries or a general ledger: Decree 09-110. Ledgers are operational registers (D-16).
- Email, SMS and push notifications: v1 notifications are in-app only.
- Google Sheets input, fine-tuned models, clinics or other health data (D-14).
- Publishing packages to npm or PyPI: the names are likely taken, so v1 ships as repo and container images only.

## Decisions

| ID | Decision | Why | Source |
|---|---|---|---|
| D-1 | Product name **Daftar**, CLI `daftar`, GitHub repo `daftar` | Chosen name | User |
| D-2 | Public repo under **AGPL-3.0** | Portfolio signal; deters closed SaaS copies; every dependency chosen is MIT/Apache | User |
| D-3 | TypeScript Studio and runtime (NestJS API, React UI) on Postgres, using **Kysely**, not Prisma; a **Python worker** reads, analyses, exports and diffs | Python has the best .xlsx fidelity; Prisma's fixed schema clashes with tables from a spec | User |
| D-4 | **Build our own thin runtime**, borrowing Frappe's semantics; fall back to Frappe, then NocoBase | No platform fits on licence, Arabic and provenance together | User |
| D-5 | **Formualizer** behind our own interface, with exact versions pinned and the Python and Node bindings on the same version; **IronCalc** cross-checks in CI; no HyperFormula | Permissive, modern functions, dependency graph, SheetPort calculators | User |
| D-6 | Understanding (the analyser) lives in the Python worker | It sits next to openpyxl, Splink and Formualizer's Python binding | Planner |
| D-7 | The spec is canonical JSON validated by one JSON Schema that both TypeScript and Python use | One contract, two languages | Planner |
| D-8 | The language model is reached through an OpenAI-compatible endpoint. Default: Ollama with `qwen3.5:9b`, thinking off. It's optional | Ollama and the 8 GB RTX 4070 are already on the operator's machine; llama-server is a drop-in later | Planner |
| D-9 | The Studio embeds the runtime renderer for previews. Client bundles never contain the Studio, the analyser or a model | The model runs only on the operator's machine; client installs stay light | Planner |
| D-10 | One deployment per firm, local accounts, the four roles of R-17 | A small firm doesn't need SSO or multi-tenancy | Planner |
| D-11 | The review never applies anything on its own (R-12) | Users prefer to keep the initiative (Proactive Wrangling) | Planner |
| D-12 | UI library **Mantine** | DirectionProvider for right-to-left, plus forms, dates and charts | Planner |
| D-13 | Test set: 100 frozen workbooks, growing to 150, plus a tuning pool of 50 or more | ±6–8 points before the first public claim | User |
| D-14 | Pilots in low-risk verticals: shops, distributors, workshops, tutoring centres, cash-on-delivery order trackers | Health data needs ANPDP authorisation | User |
| D-15 | Competitor bake-off on synthetic or public workbooks only | Uploading client data to foreign SaaS is a transfer abroad (Law 18-07 art. 44) | User |
| D-16 | Ledgers become operational registers (unpaid, overdue), not accounting | Stays outside Decree 09-110 | User |
| D-17 | No dates in this plan; packages are ordered by dependency | You schedule them against your other work | User |
| D-18 | Confidence levels: high ≥ 0.85 and low < 0.6 by default; WP-8 tunes them on the dev pool | Needs a starting point before evaluation | Planner |

## Context

- **Where things live:**
  - The repo root is `~/_hsproject/spread_monitor/`. It's greenfield: only `docs/` and the research folders exist.
  - `docs/01-refined-idea.md`, `docs/02-research.md` and `research_notes/` are git-ignored and exist only on the operator's machine. A fresh clone doesn't have them.
  - Research evidence: `research_notes/Spreadsheet to app generator/*.md`.
  - A standard-library feature-count script: `research_notes/Spreadsheet to app generator/xlsx_census.py`. It was written during research and hasn't been reviewed; treat it as prior art for R-26.
- **Precedent:**
  - `~/_hsproject/exai` for the NestJS module layout, Dockerfiles and the pnpm CI workflow (`.github/workflows/ci.yml`).
  - `~/_hsproject/parakeet_test` (speechloom) for Python packaging with ruff, mypy and pytest, and its release workflows.
  - Differences from both: Daftar is one monorepo, a pnpm workspace plus a uv project, licensed AGPL rather than MIT.
- **Constraints:**
  - Local machine: Node 26, pnpm 11, Python 3.12 with uv, Docker 29, Ollama 0.21, RTX 4070 laptop GPU with 8 GB, GitHub user `almajd3713`.
  - LibreOffice is **not** installed locally, so it lives in the worker image.
  - The repo is public from the first push.
- **Traps:**
  - **Data:** client workbooks and Studio projects contain personal data and must never enter the public repo; git-ignore them from WP-1. Test fixtures are synthetic or carry a clear licence. The Enron files contain SSNs and birth dates, so scan before reusing any.
  - **openpyxl:**
    - Formulas and their stored results need two loads.
    - Saving drops stored results, so `formualizer recalc` must be the very last export step.
    - It expands shared formulas per cell and returns array formulas as objects.
  - **Formula details:**
    - Newer functions carry `_xlfn.` prefixes in the file.
    - XlsxWriter writes 0 as a formula's result unless given a value.
    - Mind the 1900 leap-year bug.
    - TODAY, NOW, OFFSET and INDIRECT need a frozen clock (Formualizer has an injectable clock) for parity checks.
  - **Never force LibreOffice to recalculate when converting, and don't trust the results it converts.** Its "never recalculate" setting covers .xlsx only: WP-2 tests show it recalculates .xls and .ods on load regardless. So it converts their structure, and the worker restores the stored results from the original file (`reader/stored.py`). Otherwise the formula parity score would measure "same as LibreOffice", not "same as Excel". This matters because about a third of the test set and all of Enron are .xls. Recalculating LibreOffice is allowed only as a separate cross-check engine, never in the conversion path.
  - **Not every stored result is Excel's.** Files last saved by LibreOffice or another app, all .ods files, and workbooks saved in manual-calculation mode carry results that can't serve as the reference. C-1 `resultsFrom` marks them.
  - **Never build SQL strings from formulas or spec labels.** NocoDB's 2026 SQL-injection CVE came from exactly that. Database identifiers come only from spec keys (C-3 pattern), and values are always parameters.
  - **Ollama and llama.cpp JSON schemas:**
    - They silently ignore some schema features (`$ref`, `prefixItems`), so keep schemas flat with enums, describe the schema in the prompt as well, and re-validate in code.
    - Qwen3.5 has thinking on by default; turn it off.
  - Use `ar-DZ`, not `ar`, which gives the Eastern month names (يناير). Put `dir="auto"` on user text.
  - Formualizer is pre-1.0 and its API changes between releases. Only our interface may call it.
  - **Licences:**
    - DECO has no licence file: internal evaluation only until its authors confirm.
    - Sheetpedia and SpreadsheetBench are CC BY-SA, so including them makes the published set CC BY-SA.
    - Vertex42 and Microsoft templates can't be redistributed.
  - Installable web apps need HTTPS. On a LAN that means a private CA whose root goes on every phone (see OQ-1).

## Contracts

**C-1 Workbook snapshot** (worker → analyser, Studio grid). JSON, `snapshotVersion: 1`:
- `source`: `{fileName, sha256, format: xlsx|xlsm|xls|ods|csv, convertedFrom?, application?, resultsFrom: excel|other|none}`
  - `resultsFrom` says who produced the stored formula results in the original file. It is `excel` only when Excel last saved the file in automatic-calculation mode; `none` means the file has no formulas.
- `sheets[]`: `{name, index, state: visible|hidden|veryHidden, protected, rtl, dimension, hiddenRows[], hiddenColumns[], cells[], merges[], validations[], conditionalFormats[], tables[]}`
  - `hiddenRows` and `hiddenColumns` are compact ranges, such as `"5:9"` and `"A:C"`. Hidden cells stay in `cells[]`.
  - Cells are sparse: `{ref, v, t: n|s|b|d|e, f?, fmt?, style?: {fill?, color?, bold?}, comment?}`. Here `v` is the stored or typed value and `f` is the A1 formula with English function names. When the file used structured references, `f` holds the A1 form and `fStructured` what the file said.
- `definedNames[]`: `{name, scope?, ref}`
- `unsupported[]`: `{kind: pivot|chart|image|shape|macro|externalLink|other, sheet?, ref?}`

**C-2 Analysis** (analyser → Studio → spec generator). JSON, `analysisVersion: 1`:
- `{snapshotSha256, engine: {rulesVersion, model?, quant?}, sheets[]: {name, outcome, reason?, findingIds[]}, findings[]}`
- Each finding: `{id, kind, sheet, evidence: [A1 ranges], proposal, alternatives[], confidence: {level, score, source: rules|votes}, explanation: {fr, ar}, decision: {status: pending|accepted|edited|rejected, value?, by?, at?}}`
  - `id` is stable: a hash of the kind and the normalised evidence. That is what makes R-15 possible.
  - `kind` is one of: sheetKind, table, header, totalRow, groupColumn, fieldType, choiceList, statusColours, entityMerge, relation, periodUnion, computedField, calculator, anomaly, unsupported.
  - `proposal` has a per-kind JSON shape, defined in the schema.

**C-3 App spec**, `daftar.spec.json`. The schema lives at `packages/spec/schema/daftar.spec.schema.json`, with `specVersion` (semver).
- **Keys:** `^[a-z][a-z0-9_]{0,62}$`, stable, and the only source of database identifiers. Every label is `{fr, ar}`.
- **Top level:** `app` (name, locales, currency DZD, timezone), `entities[]`, `calculators[]`, `views[]`, `forms[]`, `dashboards[]`, `roles[]`, `workflows[]`, `reminders[]`, `history`, `mapping[]`. The research's spec-concept table describes each part.
- **`entity`:**
  - `kind`: register, ledger, tracker or reference
  - a naming rule, a title field, a `period` (for merged monthly tabs), `retention` and `personalData` flags
  - `fields[]`, each with a `type` from: text, longtext, integer, decimal, money, percent, date, datetime, boolean, choice, multichoice, phone, email, link, child, computed
- **`computed`:** `{expr (typed AST), excel (original formula text), deps[], store, eval: translated|engine}`
- **`mapping`:** for each entity, its source sheet or sheets, header row, column order and key columns. Export (R-22) and re-import (R-23) both use it.
- **`provenance`:** optional on every element: `{workbookSha256, sheet, range, detector, confidence, decision, decidedBy, decidedAt}`

**C-4 Worker API.** Internal HTTP with JSON bodies, reachable only on the Compose network:
- `POST /v1/read` (multipart) → C-1
- `POST /v1/analyze {snapshotSha256, llm: on|off}` → `{jobId}`
- `GET /v1/jobs/{id}` → `{status, progress, result?, error?}`
- `POST /v1/export {spec, rows by entity}` → .xlsx
- `POST /v1/reimport/diff {spec, file, keys by entity}` → `{entities: {added[], changed[{key, fields}], missing[]}}`
- Errors: `{code, message: {fr, ar}}`, with codes `unreadable|protected|too_large|unsupported_format|invalid_spec`.

**C-5 CLI `daftar`** (Python, run with `uv run`; exit codes 0 = ok, 2 = unreadable input, 3 = validation error):
- `read FILE -o snapshot.json`
- `analyze FILE [--no-llm] -o analysis.json`
- `census PATH... -o census.json` (also writes `census.md`)
- `eval --labels DIR --split dev|test -o DIR [--analyses DIR] [--manifest FILE] [--prelabel] [--freeze]`
- `bundle PROJECT -o DIR`
- `studio` (starts the Studio stack)

**C-6 Evaluation set:**
- `eval/manifest.csv`: id, source, licence, language, stratum, split (dev|test), consent, sha256.
- `eval/labels/<id>.json`: the label set in research notes `corpora_and_mess.md` §4, plus each formula cell's stored Excel result. Those results are read from the original file before any conversion. Workbooks whose `resultsFrom` isn't `excel` are left out of the parity metric and listed in the report.
- Publishable workbooks go in `eval/workbooks/`. Everything else goes in the git-ignored `eval/private/`.
- Once frozen, the test split changes only by adding files.
- `eval/labels/<id>.json` has `status: draft|reviewed`, and scoring refuses drafts. Its schema is `apps/worker/src/daftar_worker/evaluation/label.schema.json`. `eval/test-frozen.json` records the frozen test split.

**C-7 Runtime HTTP API** (behind session-cookie auth):
- Auth and metadata: `/api/auth/{setup,login,logout,me}`, `/api/meta` (the spec, filtered by role)
- Records:
  - `GET|POST /api/e/{entity}`: filter, sort, search, page, totals
  - `GET|PATCH|DELETE /api/e/{entity}/{id}`
  - `GET /api/e/{entity}/{id}/history`
  - `POST /api/e/{entity}/{id}/transition {action}`
- History: `POST /api/changes/{id}/revert`, `POST /api/batches/{id}/undo`
- Calculators: `POST /api/calc/{calculator}`
- Round trip: `GET /api/export.xlsx`, `POST /api/import` → diff, `POST /api/import/{diffId}/apply {selected}`
- Compliance and notifications: `GET /api/register`, `GET /api/notifications`
- Accounts (added 2026-11-05, user approved): `GET /api/auth/users`, `DELETE /api/auth/users/{id}`, `POST /api/auth/users/{id}/password`, `POST /api/auth/password`
- Charts (added 2026-11-05, user approved; `order` added 2026-11-06, user approved): `GET /api/e/{entity}/aggregate`
- Deleted records (added 2026-11-07, user approved): `GET /api/e/{entity}/deleted`, `page` and `pageSize`, for those with `read` and `revert`, returning `{rows: [{changeId, recordId, name, at, actor}], total, page, pageSize}`, newest first. A `delete` line in a record's history also carries `name`.
- Errors:
  - 400 `{fields: {key: {fr, ar}}}`
  - 401, 403, 404
  - 409 for a stale write or a refused transition

**C-8 Bundle layout** (the output of `daftar bundle --target local|lan|vps`; the targets differ only in the proxy, ports and owner notes):
- `compose.yaml`: reverse proxy, runtime, worker (no analyser, no model), Postgres, backup job
- `.env` with secrets generated at bundle time; `daftar.spec.json`; `seed/<entity>.jsonl`
- `start`, `backup`, `restore` and `offsite` commands, plus `export-ca` on `lan`
- owner notes in `README.fr.md` and `README.ar.md`

**C-9 Audit record** (persisted; exported as CSV for compliance): `{id, at, actor, source: ui|import|workflow|system, batchId?, entity, recordId, op: create|update|delete|transition|revert, changes: {field: [old, new]}}`

**C-10 Config keys:**
- `DAFTAR_DATABASE_URL`, `DAFTAR_WORKER_URL`, `DAFTAR_SPEC_PATH`
- `DAFTAR_SECRET` (no default)
- `DAFTAR_DEFAULT_LOCALE` (`fr-DZ` or `ar-DZ`), `DAFTAR_TZ`
- `DAFTAR_LLM_BASE_URL` (empty means rules only), `DAFTAR_LLM_MODEL`

## Work packages

**Phase 0: Foundation** (repo, CI and the spec contract that every later package uses)

### WP-1: Repository, CI and the spec schema
- **Outcome**: a public AGPL monorepo with working checks in both languages, plus a validated C-3 schema with example specs.
- **Covers**: C-3, C-10, D-1, D-2, D-7.
- **Depends on**: none. **Parallel with**: none.
- **Start from**: the exai CI workflow; speechloom's `pyproject.toml` (ruff, mypy, pytest).
- **Build**:
  - `git init`, `.gitignore` (projects, `eval/private`, workbooks, `.env`), LICENSE (AGPL-3.0), README with the demo-project label.
  - A pnpm workspace for `apps/` and `packages/`, a uv project for the worker, and one CI workflow running both checks.
  - `packages/spec`: the JSON Schema, TypeScript types and a Python validator from the same file.
  - Hand-written example specs, one per kind: tutoring-centre register, payments ledger, fee calculator, repair tracker. Later packages use them as fixtures.
  - A Compose dev stack: Postgres plus the worker image, with LibreOffice installed.
- **Done when**: CI is green; every example spec validates in both languages; an invalid spec fails with a readable path to the error.
- **Watch out**: creating the GitHub repo makes it public. Stop and confirm with the user before the first push.

**Phase 1: Read and measure** (measuring comes before understanding, because no benchmark exists)

### WP-2: Reader and census
- **Outcome**: any supported file becomes a C-1 snapshot, and `daftar census` reports feature counts.
- **Covers**: R-1, R-2, R-26, C-1, C-4 (`/v1/read`), C-5 (`read`, `census`).
- **Depends on**: WP-1. **Parallel with**: WP-9.
- **Start from**: research `engines_and_io.md` Q3 and Q5; `xlsx_census.py`.
- **Build**:
  - Read in two passes (formulas, then stored results), plus raw XML for whatever openpyxl drops.
  - Convert .xls and .ods through LibreOffice without recalculation, and set `resultsFrom` from the original file's application metadata and calculation mode. Read .csv with delimiter and encoding detection, including Arabic and French text.
  - Turn every unsupported part into a C-1 `unsupported` entry.
  - The census reports per workbook and in aggregate: the feature list plus function-occurrence coverage (80/90/95/99%).
- **Done when**:
  - Synthetic fixtures for each feature round-trip through `daftar read`.
  - A corrupt file, a protected file and an oversized file each fail with their C-4 code.
  - The census over the fixtures matches hand counts.
  - A converted .xls fixture whose stored results were deliberately left out of date keeps those exact results. They match a direct read of the original .xls and differ from a fresh recalculation, which proves no recalculation happened.

### WP-3: Labels and the evaluation harness
- **Outcome**: `daftar eval` scores any analysis against C-6 labels with workbook-level bootstrap CIs.
- **Covers**: R-27, C-6, C-5 (`eval`).
- **Depends on**: WP-2. **Parallel with**: WP-5 to WP-7.
- **Start from**: research `corpora_and_mess.md` §4–§5 and §(d).
- **Build**:
  - A label validator, the manifest, and enforcement of the dev/test split.
  - Metrics:
    - tables at exact and ±2-cell boundaries
    - header F1, macro type accuracy, relation P/R/F1
    - sheet-kind confusion
    - formula parity against stored results, by function category and stratum, counting only workbooks with `resultsFrom: excel`
  - A report written as JSON and Markdown, stamped with the git SHA, model and quantisation.
  - A pre-labelling mode: it writes analyser output as draft labels for a human to correct.
- **Done when**: on synthetic labelled fixtures with known errors, the reported metrics and CIs match hand-computed values.

### WP-4: First labelled workbooks (needs the user)
- **Outcome**: a dev pool of at least 20 and the first 30 test workbooks, labelled and in the manifest.
- **Covers**: D-13 (first part).
- **Depends on**: WP-3. **Parallel with**: WP-5 to WP-10.
- **Build**:
  - Run the census over Sheetpedia and the Enron/DECO candidates to set quotas.
  - Author French and Arabic replicas of common SME template patterns.
  - Label them, with 25% double-labelled.
  - Write a bilingual labelling guide.
- **Done when**: `daftar eval --split dev` runs on real labels; the guide exists in `eval/`.
- **Watch out**: this is mostly the user's time (30–90 min per workbook). Stop and hand over the batches; don't invent labels.

**Phase 2: Understand** (the analyser; WP-5, WP-6 and WP-7 can run in parallel after WP-2)

### WP-5: Structure: tables, headers, totals, types, sheet kind
- **Outcome**: `daftar analyze --no-llm` emits C-2 with sheet outcomes, tables, headers, totals and field types.
- **Covers**: R-3, R-4, R-5, R-10 (templates), C-2, C-4 (analyze and jobs).
- **Depends on**: WP-2. **Parallel with**: WP-6, WP-7, WP-9.
- **Start from**: research `research_methods.md` §1, §4, §7, §9.
- **Build**:
  - A feature-based cell-role classifier with region growing; totals found from SUM-style formulas, and from arithmetic when only values are stored.
  - Sheet-kind scoring, including `referenceList` and `notConverted`.
  - Type inference for every C-3 type, including DZD, Algerian phones and French dates.
  - Explanation templates in French and Arabic, filled from facts.
- **Done when**: dev-pool metrics are reported. No accuracy target yet; the baseline goes into Log.

### WP-6: Formulas: computed fields and calculators
- **Outcome**: copied formula columns become `computedField` findings with a translated expression or an engine fallback; formula models become `calculator` findings; every formula gets a parity check.
- **Covers**: R-9 (formulas), R-19 (parity), D-5.
- **Depends on**: WP-2. **Parallel with**: WP-5, WP-7.
- **Start from**: research `engines_and_io.md` Q1, Q2, Q5; `corpora_and_mess.md` §(c) for the ~55-function list.
- **Build**:
  - Our engine interface over Formualizer, plus an IronCalc cross-check job in CI.
  - Grouping of copied formulas.
  - A translator from a formula tree to the C-3 expression AST for the function list, with lookups into another sheet turned into relation evidence.
  - Calculator input/output detection.
  - A parity report against stored results, with the clock frozen.
- **Done when**:
  - Parity on the dev pool is reported by function category.
  - Translated and engine results agree on every fixture.
  - Any function outside the list falls back to the engine and is reported.

### WP-7: Entities, relations, monthly tabs, choices and colour statuses
- **Outcome**: findings for R-6, R-7, R-8 and the colour and choice parts of R-9.
- **Covers**: R-6, R-7, R-8, R-9 (statuses and choices).
- **Depends on**: WP-2. **Parallel with**: WP-5, WP-6.
- **Start from**: research `research_methods.md` §3 and §7; `local_llm.md` §8 (division of labour).
- **Build**:
  - Name normalisation (accents, Arabic orthography, Arabizi digits), blocking and similarity scoring (Splink or equivalent).
  - Relation candidates from lookups and from key inclusion, under a snowflake-shape constraint.
  - Period-tab union by sheet-name period and column-set similarity.
  - A conditional-format and fill → status mapping.
- **Done when**: the dev-pool metrics for relations and monthly tabs are reported.
- **Watch out**: no published method covers these three steps. Expect to iterate, and log every rule you add.

### WP-8: Language model: ties, names and wording
- **Outcome**: with a model configured, close candidates are decided by votes, entities and fields get French and Arabic names, and explanations are reworded. Without one, R-11 holds.
- **Covers**: R-10, R-11, D-8, D-18, OQ-4.
- **Depends on**: WP-5. **Parallel with**: WP-6, WP-7.
- **Start from**: research `local_llm.md` §2, §4, §6, §8.
- **Build**:
  - An OpenAI-compatible client with flat JSON schemas, re-validated in code; one retry, then the rules' answer marked `needs review`.
  - Prompts built from profiles plus samples, never whole sheets.
  - 3–5 vote self-consistency for confidence; a cache keyed on the profile hash, prompt version, model and quantisation.
  - Darja and Arabizi normalisation through a glossary before the model sees a label.
- **Done when**:
  - The dev pool scores the same or better with the model than with rules only, on every metric.
  - A 5-sheet, 10k-row workbook finishes in under 5 minutes on the RTX 4070.
  - The confidence thresholds are tuned and logged.

**Phase 3: Runtime** (built against WP-1's example specs, so it runs in parallel with Phases 1–2)

### WP-9: Runtime core: schema, API, roles, history, computed fields
- **Outcome**: a NestJS service that loads a spec, migrates Postgres to it and serves C-7.
- **Covers**: R-17, R-18, R-19 (runtime), R-21 (server side), R-24, C-7, C-9, D-3, D-10.
- **Depends on**: WP-1. **Parallel with**: Phases 1–2.
- **Start from**: the exai backend module layout; research `spec_and_runtime.md` §3–§5 and §10(c).
- **Build**:
  - Spec → schema diff, a plan and an apply step. Additive changes apply automatically; destructive ones need a backup and an explicit confirmation.
  - The generic record API with role, row-scope and field-level enforcement.
  - Session auth with first-run owner setup.
  - An audit log written by the app, with revert and batch undo.
  - Computed fields evaluated on write and stored; calculators through the Node binding of the engine interface.
  - The processing-register export.
- **Done when**: each example spec boots; API tests prove R-17 (including masking), R-18 (revert, batch undo) and R-19 against the fixture formulas.

### WP-10: Runtime UI: lists, forms, board, dashboards, calculators
- **Outcome**: a React UI that renders any spec in French and Arabic, both directions, on phone and PC.
- **Covers**: R-16, R-20, R-21, D-12, and the screens for R-17 and R-24.
- **Depends on**: WP-9. **Parallel with**: Phase 2.
- **Build**:
  - Lists with filters and totals, forms, a detail page with a history timeline, a board for workflows, dashboards and calculators.
  - A language switch that changes the direction.
  - In-app reminders.
  - An owner's page: staff accounts, changing a password, the processing register and the audit download.
- **Done when**: each example spec is usable end to end in both languages at phone width. A refused transition explains itself. The dates, digits and DZD amounts follow R-21.

**Phase 4: Studio** (the operator's tool)

### WP-11: Studio: projects and the review screen
- **Outcome**: the operator uploads a workbook, watches the analysis progress, and reviews the findings on the grid.
- **Covers**: R-12, R-13, R-15, C-5 (`studio`).
- **Depends on**: WP-5 and WP-10; WP-6 to WP-8 are needed for the full set of findings. **Parallel with**: none.
- **Build**:
  - Projects on disk (source, C-1, C-2, spec, seed); projects are never placed in the repo.
  - The grid with evidence highlights, and the findings list with accept, edit, reject and bulk accept of high-confidence findings.
  - A French/Arabic switch with owner-friendly wording.
  - Re-analysis that re-applies decisions by finding ID and shows conflicts.
- **Done when**: on a fixture, every finding kind can be accepted, edited and rejected. A rerun keeps the decisions. An edited workbook shows the conflicts.

### WP-12: Spec generation, data load and preview
- **Outcome**: accepted findings become a valid C-3 spec with provenance, plus seed data, previewed in the embedded runtime.
- **Covers**: R-14, C-3 (generation), D-9.
- **Depends on**: WP-11. **Parallel with**: none.
- **Build**:
  - Spec generation, in which only accepted or edited findings count.
  - Data load: monthly tabs unioned, retyped names merged into entities, totals rows dropped.
  - A preview that runs on the seed data.
  - A parity check: computed values in the preview match Excel's stored results (R-19).
- **Done when**: each example workbook kind goes from upload to a working preview with parity passing.

**Phase 5: Round trip and handover**

### WP-13: Export and re-import
- **Outcome**: R-22 and R-23 work from the runtime UI.
- **Covers**: R-22, R-23, C-4 (export, diff).
- **Depends on**: WP-9, WP-12. **Parallel with**: WP-14.
- **Build**:
  - An export that follows `mapping`; formula results filled by `formualizer recalc` as the last step; right-to-left for Arabic.
  - A re-import diff on the key columns; an apply screen with per-row selection; application as one batch that can be undone.
- **Done when**:
  - An exported fixture opens in LibreOffice with the same totals as the app.
  - Editing it and re-importing shows exactly the edits; undoing the batch restores the previous state.

### WP-14: Bundle, deploy and backup
- **Outcome**: `daftar bundle` produces C-8, and a fresh machine reaches the owner's first login with the data loaded.
- **Covers**: R-25, C-8, OQ-1, OQ-2.
- **Depends on**: WP-12. **Parallel with**: WP-13.
- **Build**:
  - The bundle with generated secrets and pinned image tags.
  - A first-start flow; `backup` and `restore`; the French/Arabic README files; the deploy recipe chosen in OQ-1.
- **Done when**: on a clean VM, bundling a fixture and bringing it up leads to owner setup with data present; backup, wipe and restore gives the same data.
- **Watch out**: OQ-1 must be answered by the user before the TLS and recipe work. Stop and ask.

### WP-18: Retention, erasure and the full log
- **Outcome**: R-28: a firm's app does what its register says, and a person's data can be erased while the log still shows what was done.
- **Covers**: R-24, R-28, C-9.
- **Depends on**: WP-9, WP-10. WP-17 depends on this. **Parallel with**: WP-13, WP-14.
- **Build**:
  - The daily check, on the same timer as R-20's reminders, and an owner's page of what's past its period. Each period runs from the record's last change, unless OQ-6 says otherwise.
  - Erasing one record, or a deleted one, for good. It asks first, can't be undone, and adds an `erase` line to C-9.
  - Removing values from `_audit.changes` and `_audit.snapshot` while keeping field names, operation, actor and time. An erased record leaves the deleted list and can no longer be restored.
  - An access log beside `_audit`, for reads and exports of `personalData` entities: who, when, entity, record or list, and no values. It's separate because `_audit` backs undo, and a line per read has no place there.
  - Saying plainly what the app can't reach, in the owner's notes: a backup keeps a record until it rotates out, so `backup` needs a stated period, and a downloaded export is out of reach. `seed/*.jsonl` in the bundle holds the first import's data, so it's deleted after loading.
- **Done when**: a record past its period is listed and goes when confirmed; an erased record's values are nowhere in the database, checked by searching every table for a known value; its log lines remain; a read and an export of personal data each leave a line; and `GET /api/register` still states the same periods.
- **Watch out**: this reading of the law is the planner's, from the Journal officiel text and not from a lawyer. OQ-6 goes to the lawyer WP-17 already stops for. Other laws may require keeping accounting records longer than a spec's `retention` says, which is why records wait for an owner to confirm.

**Phase 6: Proof** (each of these needs the user)

### WP-15: Competitor bake-off
- **Outcome**: a published comparison of 3 to 5 synthetic or public messy workbooks in GlideOS, Airtable Omni, Power Apps Copilot, Quickbase and SpreadsheetWeb, set beside Daftar.
- **Covers**: D-15.
- **Depends on**: WP-12. **Parallel with**: WP-13, WP-14, WP-16.
- **Done when**: `docs/bake-off.md` records, per tool and workbook, what was kept, lost and wrong, with dates and screenshots.
- **Watch out**: the accounts and uploads are the user's. Never upload pilot or Enron files with personal data.

### WP-16: Freeze 100 test workbooks and publish accuracy
- **Outcome**: 100 frozen test workbooks, and a published eval report that the README result line can quote.
- **Covers**: R-27, D-13, OQ-3, OQ-5.
- **Depends on**: WP-4, WP-8. **Parallel with**: WP-15.
- **Done when**: `daftar eval --split test` runs on the 100, and the report, with its CIs and the licence notes for the published set, is in `docs/`.

### WP-17: First pilot
- **Outcome**: one real firm in a low-risk vertical runs on Daftar, and the case study measures upload-to-accepted time and the number of review corrections.
- **Covers**: D-14, R-24.
- **Depends on**: WP-13, WP-14, WP-18. **Parallel with**: none.
- **Build**: French/Arabic consent for anonymised reuse of the workbook; templates for the processor agreement and the ANPDP declaration checklist (the research compliance checklist); the conversion; the handover pack; the case study draft.
- **Watch out**: the legal templates come from secondary sources. Stop for a lawyer's review before anyone signs.

## Open questions

- **OQ-1 Where client apps run** (answered 2026-11-04: both, one per firm; see Log):
  - **The options:** a LAN box at the firm (works offline; a private CA root on every phone; backups to a second disk) or an Algerian VPS (1,900–9,500 DA/month; a domain and easy TLS; needs internet; a sub-processor), or both.
  - **What depends on it:** C-8's proxy and TLS setup, and the backup target.
- **OQ-2 Offline writes** (after OQ-1 and the first pilot feedback, in WP-14 or WP-17): a queue of pending changes in the installable web app (v1 option) or PowerSync (v2). It matters only if staff work away from the server.
- **OQ-3 Dynamic arrays in v1** (WP-16 census): add them if the pilot and Sheetpedia counts show them in more than 5% of formula-using workbooks.
- **OQ-4 Default model** (WP-8): Qwen3.5-9B vs Gemma 4 E4B at Q4, compared on the dev pool. Keep whichever wins on naming and ties.
- **OQ-5 DECO labels** (before WP-16 publishes): ask the DECO authors about licensing. Without permission, DECO-derived labels stay in `eval/private/`.
- **OQ-6 What a lawyer has to confirm about retention** (before WP-17; WP-18 goes ahead on the readings below):
  - **Art. 41 bis 3's reach:** does "consultation" mean every list a person opens? WP-18 logs them to be safe. And what should "les motifs" hold, when a firm's staff give no reason for each operation?
  - **Its limit:** the log is used "exclusivement" for checking legality, internal control, integrity and security, and criminal proceedings. Does showing a record's history to staff and using it to undo fall inside internal control and integrity?
  - **Art. 35:** it covers erasing data whose processing isn't compliant, which reads narrower than a general right to erasure. Does a firm owe more than that?
  - **Other laws:** how long must accounting records be kept, whatever a spec's `retention` says? And from when does a period run?

## Validation

- **Project checks:** WP-1 defines them, and CI runs them:
  - `pnpm -r lint`, `pnpm -r typecheck`, `pnpm -r test`
  - `uv run ruff check`, `uv run mypy`, `uv run pytest`
  - the spec schema validation of the example specs

  No failures exist yet; this is a greenfield repo.
- **End to end:**
  1. Take a synthetic tutoring-centre workbook containing:
     - a student register with parent names retyped with variants;
     - monthly payment tabs with totals rows;
     - a fee calculator;
     - a status column coloured by conditional formatting.
  2. In the Studio, upload it and review it in Arabic, then accept the findings.
  3. Preview the app, with parity passing. Then bundle it and start it on a clean machine.
  4. As owner, set up the account and record a payment; the payment appears in the history.
  5. As staff, check that the margin field is not visible.
  6. Export to .xlsx: the totals match. Edit the file and re-import it: the diff shows exactly the edits. Undo the batch.
  7. `GET /api/register` lists the personal-data fields.

## Progress

- [x] WP-1: Repository, CI and the spec schema
- [x] WP-2: Reader and census
- [x] WP-3: Labels and the evaluation harness
- [ ] WP-4: First labelled workbooks
- [ ] WP-5: Structure: tables, headers, totals, types, sheet kind
- [x] WP-6: Formulas: computed fields and calculators
- [ ] WP-7: Entities, relations, monthly tabs, choices and colour statuses
- [ ] WP-8: Language model: ties, names and wording
- [x] WP-9: Runtime core
- [ ] WP-10: Runtime UI
- [ ] WP-11: Studio: projects and the review screen
- [ ] WP-12: Spec generation, data load and preview
- [ ] WP-13: Export and re-import
- [ ] WP-14: Bundle, deploy and backup
- [ ] WP-18: Retention, erasure and the full log
- [ ] WP-15: Competitor bake-off
- [ ] WP-16: Freeze 100 test workbooks and publish accuracy
- [ ] WP-17: First pilot

## Log

- 2026-11-06 (WP-11, WP-12, R-13): The UI agent's remaining points, with the user's approval. **C-7:** aggregate takes `order=asc|desc`; with `desc` the 500 groups kept are the highest keys, and a null key comes last. Explanations now count properly in French and Arabic (Arabic has forms for one, two, three to ten, eleven to ninety-nine and hundreds, and the dual changes after a preposition or as an object). Where agreeing a verb or adjective with an Arabic count would need more rules, the sentence says "count: N" instead. Every inserted fact is wrapped in FSI and PDI, and bidi controls in a cell's text are removed from it. A language model gets the sentence without isolates, because it can't be trusted to keep invisible characters, and they're put back afterwards. The Studio's unexpected job failures and failed previews now have the code `internal` rather than `unreadable` or `invalid_spec`; C-4's worker routes don't use it. `/preview/open?lang=` passes `fr` or `ar` on. The Arabic and French wording still hasn't had a native speaker's review. The UI agent adds serving the Studio's UI in WP-11 and formats the grid's cells itself.
- 2026-11-06 (WP-11, WP-12): From the UI agent's check of the Studio contract on PR #19: the generation report can be read again at `GET /api/projects/{id}/generation`, with `labels` from the spec and only the questions still open; `GET /api/projects` adds `jobId`, `generated`, `generationStale` and `previewRunning`; `badValues` items now name their entity; the report is written last and whole, since reads are allowed during a job. **A preview's session cookie is named after its database, and its `GET /api/auth/status` adds `preview: true`.** That route is outside C-7's list, per the 2026-11-04 note, and a delivered app's responses and `daftar_session` are unchanged, so this isn't a change to C-7. Not fixed: a project's first analysis still isn't listed until it finishes, so the UI keeps that job's id in `sessionStorage`.
- 2026-11-03: Plan written from `01-refined-idea.md` and `02-research.md`. Client deployment target left open by the user (OQ-1).
- 2026-11-05 (WP-10): **Not ticked: this is the design system only, and the screens come next.** The user compared three directions on real screens and chose Registre: a register kept in ballpoint, with rules instead of boxes. It's now `packages/ui`, on Mantine (D-12), and `packages/ui/README.md` holds its rules. The reference app in `preview/` draws ten screens from the components alone, and the browser audit runs on it in CI. The Runtime's and Studio's real screens still have to be built on it.
- 2026-11-05 (WP-10): Choices a reviewer might question. **Charts are drawn by hand, not with `@mantine/charts`,** though D-12 names charts: Recharts costs far more than these phones should download for one line and one bar list, and the axis has to follow the reading direction. Revisit if a spec needs other chart types. **Numbers, dates and months are formatted by hand**, because `Intl` depends on the browser's ICU and `fr-DZ` inserts U+202F, which the font lacks; tests compare the result with Node's `Intl`. **Arabic carries `size-adjust: 110%`,** chosen by eye and accepted by the user, so both languages share one type scale; browsers before Safari 17 just show plain sizes. **A zero in a column shows as a dash,** as in Excel's Accounting format; that's display only, and totals and exports stay numbers. **A frame measures its own width rather than the viewport,** so the Studio's embedded preview (D-9) gets the phone layout. **Phone navigation is text only,** because a spec has no icons and guessed ones would be wrong. Fonts are copied into the package (OFL), because a firm's box must work with no internet.
- 2026-11-07 (WP-10): **User's decision: WP-10 gets a list of what's been deleted, and it works.** After leaving a deleted record's page nothing led back to it, so an owner couldn't restore it later. C-7 gains `GET /api/e/{entity}/deleted`, because `audit.csv` has no name and doesn't say what's been restored. WP-10 stays unticked. Choices a reviewer might question. **One list per entity, reached by a quiet link under its list,** rather than one for the whole app, because restoring is rare and a person knows what they lost. **Only for those who can restore,** since nobody else could act on it. **A row opens the record's page,** which already restores it, rather than a button in the row, because a phone's whole row is one button. That page now names the record, so a person can check they've opened the right one. **It lists only what someone deleted,** so undoing an import or a creation doesn't flood it. **It has no time limit of its own;** WP-18's removal of old history values will take rows off it, since nothing is left to restore from. Restoring a parent doesn't bring back records a cascade deleted, and each of those is listed on its own, as restoring already worked. Found on the way and fixed: restoring a record whose unique value had since been taken answered 500, which reads as the server being down; undoing an edit in the same position answered 400 `{fields}`, which the record's page has no field to show, so nothing happened on screen. Both now answer 409 `{reason}`, naming the field.
- 2026-11-07 (R-24, R-28, WP-18): **Added a package for retention, erasure and the full log, on the user's word to use judgement.** A deletion keeps every old value in `_audit`, and nothing in the Runtime or `deploy` removes anything from it or acts on `retention` and `retentionMonths`, which the register only prints. Read in the Journal officiel text ([Law 18-07](https://droit.mjustice.gov.dz/sites/default/files/loi_18-07_fr.pdf), [Law 25-11](https://www.africadataprotection.org/Algerie-modification-loi-18-07.pdf)), not by a lawyer. **What it says.** Law 18-07 art. 9(e): data stays identifiable no longer than its purposes need, and going past that for historical, statistical or scientific purposes takes the authority's permission. Art. 14: a declaration states the period. Art. 65: keeping data past the period in the law, the declaration or the authorisation carries a fine of 200,000 to 500,000 DA. Art. 35: free of charge, within 10 days, a person can have data updated, corrected, erased or blocked when its processing isn't compliant, and third parties told. Law 25-11 art. 41 bis 2: the register states erasure deadlines where possible. Art. 41 bis 3: an automated log covering at least collection, modification, extraction, consultation, communication, erasure and destruction, identifying the reasons, date and time and, where possible, who and to whom. **What that changes.** Printing a period is a promise to the authority with a fine behind it, so it has to be kept. The log doesn't ask for values, so erasing can remove them and keep the line, which settles how erasure and R-18 fit together. R-24 called change history the automated log, and it holds only writes. **Corrections to the research notes:** they say art. 41 bis 3's conditions await a regulation, following the UpGrowth digest, but the text's only such sentence is under art. 27 bis, so the duty applies now. And art. 35 is narrower than a general right to erasure. **Choices a reviewer might question.** It doesn't hold up WP-10, and it does hold up WP-17, because no real person's data should be in the app first. **History values go automatically, and records wait for an owner,** because losing an old undo costs little, and deleting a firm's ledger on a wrong default costs a lot; other laws may require keeping accounts longer. That means the owner can still run past a period, so the page and reminder have to be hard to miss. OQ-6 lists what a lawyer has to confirm.
- 2026-11-07 (WP-10): **Calculators work, and WP-10 isn't ticked:** the board, dashboards, reminders, sort and filter controls, the searching link picker and the owner's page are still to come. A spec with nothing but a calculator, like the fee calculator, now opens on it. Choices a reviewer might question. **A button, not live results:** R-19 says on demand, and a request per keystroke is wasted on a slow connection. **The figure goes as soon as a value changes,** because a total beside values it didn't come from is how a wrong fee gets quoted; an answer that arrives after a change is dropped. **It runs once on opening, if every input has a value,** since that's what the workbook shows; otherwise it waits, rather than opening on what a formula makes of a blank. **A cleared input is sent as null,** because the server gives an input it isn't sent its default. **The last output closes the statement with the double rule if it's a figure,** because a spec doesn't say which output is the total and generated ones are never `money`; at worst it's a rule under a figure that isn't a sum. **A formula's result is shown as it came when it doesn't fit its type,** so `=IF(A1>0,A1,"-")` shows the dash in a money line. **A `decimal` doesn't invent decimals,** because the analyser calls every number a decimal and a count of 2 mustn't read "2,00": an input's default shows the decimals it has, up to six, and a result shows none if it's whole and two otherwise. A browser flow runs the spec the worker really generated, since the hand-written examples have `money` and `integer` and a client's calculator doesn't yet. **An entity and a calculator can share a key,** which the spec doesn't forbid, so navigation keys say which is which. **On a phone the result takes focus when it arrives,** which closes the keyboard that would cover it; on a PC it's beside the form, so focus stays in the field. Found on the way and fixed in the Runtime, by running a calculator with every input type: a date input reached the formula as text, so `=MONTH(A1)` gave `#VALUE!`; a date output came back as a serial number, though the API gives every date as `YYYY-MM-DD`; a choice not on its list was accepted. Found in the design system, whose audit had never met a checkbox: 20 px against a 24 px minimum, and a border below 3:1. The reference form now has one, so the audit covers it, and a checkbox is a full target: 44 px on a phone. Not fixed, and on PR #19: the analyser writes a date input's default as `2026-11-01T00:00:00`, which the Runtime refuses as a date, so a generated calculator with a date input opens on an error. A generated total has no DA, because `_kind_of` doesn't use the money rules columns have; the UI session asked for that on #19, and asked to leave `wholeNumbers` out, since one cell holding 2 is no evidence that 2.5 is wrong.
- 2026-11-06 (WP-10): **A record's own page works, and WP-10 isn't ticked:** the board, dashboards, calculators, reminders, sort and filter controls, the searching link picker and the owner's page are still to come. A row now opens the record rather than its form, for anyone who can read it. Choices a reviewer might question. **A refused step names where to look.** The server's sentence only says the conditions aren't met, and a spec has no words for them, so the UI reads the condition in `/api/meta` and names the fields it uses, leaving out any this person can't see. It still doesn't check a condition in advance. **The step furthest along the workflow is the primary button,** since a spec gives no order of importance. **Undo isn't offered on a creation,** because that would delete the record under a label that doesn't say so. **Deleting asks first, then stays on the page,** which says it's deleted and offers to restore it. Nothing lists deleted records, so after leaving that page only its address leads back; a list would need a server route. **History asks for each link's name,** because it holds ids and the contract has no labels there; a target since deleted shows a dash. **A hidden field only says that it changed.** History names it, but `/api/meta` leaves it out, so there's no label to show, and its key is never displayed. **A value standing alone shows its zero,** and only a ledger column dashes it. **Back returns to the page a person left,** with its search and page number, by using the browser's history for entries the app made. Found on the way: `TextLink` and `PhoneLink` had no minimum width, so a short code such as MATH was a 41 px target on a phone. `PhoneLink` now groups an Algerian number, in every form the server accepts.
- 2026-11-06 (WP-10): **User's decision on scope.** An owner's page joins WP-10, because the server has the routes and no package covered the screens: staff accounts, without which R-17's roles can't be used, changing a password, the processing register and the audit download. Export and import stay in WP-13, which already says so, and don't hold up WP-10's tick. This corrects the note below, which listed them under WP-10.
- 2026-11-06 (WP-10): **First thin path works, and WP-10 isn't ticked:** detail page and history, board, dashboards, calculators, reminders, export and import are still to come. `apps/runtime-ui` is the UI. The Runtime serves it from its own origin, and `Dockerfile.dockerignore` lets in only what building it needs, so a client's image holds the built page and not its sources or tools. A spec's first start, login, list views and forms work with nothing mocked: 19 browser flows run on a real Runtime and Postgres in CI, and the real image was driven by a browser once by hand. Choices a reviewer might question. **No router library,** for a handful of paths on slow phones. **A link is a select of its target's first 500** for now; the searching picker comes with the rest. **A list is ordered and filtered by the server, and the UI only sends what the view says.** **A content security policy and `X-Frame-Options: DENY` on the page,** except in a preview, which the Studio frames. Found on the way: the runtime image still held TypeScript sources, including `preview.ts`, which D-9 keeps out, so `src` is now removed from it. A frame that changed layout rebuilt its whole screen, which would lose what someone had typed when a phone turned, and sent every page's first request twice; the shell and `Page` now keep their children in place. Chromium's Local Network Access check blocks a page it counts as public from framing a loopback address, so the Studio's preview works because the Studio is on loopback itself.
- 2026-11-06 (WP-10): Merged `main`, then read `docs/studio-api.md` against the code. Twelve points that don't fit are on PR #19, and the review and report screens wait on the answers. Still not ticked. The audit now opens the calendar, which it had never measured: Mantine's defaults gave a phone 36 px targets and day numbers under 13 px, faded other months below readable contrast, and left the arrows unnamed. All fixed. Added `Notice`, `Waiting`, `FileField` and two Studio reference screens, for what the contract says a person has to see. `LineChart` now takes what `/aggregate` returns: uneven dates, nulls, sums below zero and up to 500 points. `pnpm test:browser` builds first, because a preview server left running made the old setup skip the build and test stale code.
- 2026-11-05 (WP-11): Found while drawing the review screen: `analyser/explain.py` prints counts that aren't Arabic ("4 عمود", "6 صف") or are awkward French ("1 cellule(s)"), and R-13 asks for wording a shop owner would use. The reference screen shows the corrected wording, but the templates still need plural rules. The strings also need Latin runs, ranges and formulas wrapped at render so they keep their order in Arabic.
- 2026-11-03: Conversion no longer forces LibreOffice to recalculate; doing so would overwrite Excel's stored results, which the parity metric uses as its reference. Added `resultsFrom` to C-1, and the parity metric now counts only Excel-produced results.
- 2026-11-03 (WP-1): C-3 details filled in beyond the contract's wording, all additive: `expr` is required only for `eval: translated`, since an engine formula has no tree; computed fields carry `resultType`; every expression node carries `valueType` (our reading of "typed AST"); fields carry `personalData` (R-24 lists fields) and `level` 0/1 (R-17). `personalData: true` on an entity requires `retention`. `provenance.decision` allows only accepted or edited, since rejected findings never reach a spec. `specVersion` accepts major 1 only.
- 2026-11-03 (WP-1): The schema can't check cross-references (a view's `entity` exists, field keys are unique). Only the example specs are checked, in pytest. **WP-9's spec loader must enforce these.**
- 2026-11-03 (WP-1): Note for WP-9: spec keys must start with a letter, so system columns named with a leading `_` (`_id`, `_created_by`) can never collide with a spec field.
- 2026-11-03 (WP-1): The spec has no calculator permissions, so every signed-in role can run a calculator. Calculator outputs can be `level: 1`.
- 2026-11-03 (WP-1): Tagged unions use `oneOf` plus Ajv's `discriminator` keyword, which standard JSON Schema ignores. The Python validator implements it too, so errors name the one branch that applies and both languages report the same paths; `fixtures/invalid-cases.json` runs in both. Messages may differ, paths may not.
- 2026-11-03 (WP-1): Surprise: Python's `$` matches before a trailing newline, so `"abc\n"` passed as a key under stock `jsonschema` while Ajv refused it. The Python validator now anchors patterns strictly, and schema patterns use `[0-9]`, not `\d`, which matches Arabic digits in Python.
- 2026-11-03 (WP-1): Pinned TypeScript 6.0.3, not 7, because typescript-eslint supports `<6.1`. Licence field is `AGPL-3.0-only`. The worker has a `/healthz` endpoint outside C-4, for the Compose healthcheck, and FastAPI arrives now rather than in WP-2. Dev Compose adds `POSTGRES_PASSWORD` and `DAFTAR_DEV_DB_PORT`, outside C-10 and dev-only. `reports/` is git-ignored as a duplicate of `docs/02-research.md`.
- 2026-11-03 (WP-1): User decision before the first push: only the code and this blueprint go public. `docs/01-refined-idea.md`, `docs/02-research.md`, `research_notes/` and `reports/` stay local and git-ignored, because they hold pricing and pilot plans.
- 2026-11-03 (WP-2): Surprise, and a correction to the plan's trap: LibreOffice recalculates .xls and .ods on load whatever the setting, so stale results came back fresh (999 became 6). Its "never recalculate" only binds .xlsx. LibreOffice now converts structure only; stored results come from the original through `xlrd` (.xls) and `content.xml` (.ods). If a formula cell's result can't be restored, `resultsFrom` becomes `other`. R-1's outcome and the WP-2 check still hold; only the method changed. `xlrd` is now a runtime dependency.
- 2026-11-03 (WP-2): `resultsFrom` rules beyond the contract's wording. `fullCalcOnLoad` counts as not-Excel, because openpyxl and XlsxWriter also write "Microsoft Excel" as the application. A real Excel 2010 .xls had no application name, so .xls also counts as Excel when its BOF `verLastXLSaved` is above 0. Excel 97 files with no name stay `other`, on purpose. **Checked on one real file only; WP-4 should check `applications` in the census output against the real corpus.**
- 2026-11-03 (WP-2): C-1 details: `format` is the original's format and `convertedFrom` repeats it when converted. A formula with no stored result has `v: null, t: "s"`. Array formulas use Excel's display form, `{=...}`, on every cell of the range; data tables are `{=TABLE(r1,r2)}`. Blank cells are kept only if they have a fill or comment. `_xlfn.` prefixes are removed. CSV values all stay `t: "s"`, so leading zeros survive; WP-5 infers types. `validations[]`, `conditionalFormats[]` and `tables[]` had no shape in C-1, so the reader defines them, and `dimension` is null on an empty sheet.
- 2026-11-03 (WP-2): Serial 60 reads as `1900-02-29`, the day only Excel has.
- 2026-11-05 (WP-12): The preview's server side works, run for real through the Studio, Node and Postgres: upload, accept, generate with no parity failures, then a signed-in owner sees the seed data; stopping drops the database. Package still unticked: the screen is UI, and today the Runtime serves only its API, so the preview's page is a 404 until WP-10. `apps/runtime/src/preview.ts` makes a throwaway database per project, from `DAFTAR_PREVIEW_ADMIN_URL` (outside C-10; without it, preview answers 503), and works from a copy of the spec and seed. A throwaway owner signs in with a password nobody ever sees. `/preview/open` sets that session's cookie and redirects, since a cookie on 127.0.0.1 reaches every port, so other local apps on that host are sent it too; it's only worth anything for this preview, which holds data the operator already has. The session never reaches the page's scripts. The preview ends when the Studio stops, or when its stdin closes if the Studio dies. If it's killed outright, its database stays until that project's next preview. No worker is attached, so export and re-import answer 503 in a preview. Client images remove the preview files (D-9), and `deploy/e2e.py` checks that.
- 2026-11-05 (WP-11): `daftar studio --projects DIR --who NAME` serves the API in `docs/studio-api.md`, from Python, on the user's decision in place of D-3's TypeScript. Package still unticked: no screen, and the preview comes separately. With no login, it answers on 127.0.0.1 only and refuses a wrong Host or Origin and any write that isn't JSON or a file, including an empty POST, which a form on another site could send. Answers to the generator's questions live in `answers.json`, apart from the analysis, because a rerun replaces every proposal; retention is matched by entity key, so renaming an entity asks again. Decisions, generating and rerunning get 409 while a job runs on that project, or a rerun would silently overwrite them. A project is listed only once its first analysis finished, so a rejected file leaves nothing (R-1). Project files are now written whole or not at all. A new upload replaces a project's workbook only after it has been read, which also fixes `project_reanalyze` losing the good workbook to a bad one.
- 2026-11-05 (WP-16, OQ-3): First census on the public pool that isn't Enron: 853 workbooks from data.gouv.fr and SpreadsheetBench, 456 with formulas. Dynamic-array functions appear in 4.8% of those, and LET or LAMBDA in 0.7%, right against OQ-3's 5% line, but **this doesn't answer OQ-3**, which asks for pilot and Sheetpedia counts: SpreadsheetBench counts each task's before and after copies separately, and its answers lean modern. 95% of function calls need 36 functions, and 99% need 64, the number the translator covers, though not necessarily the same 64. 4.6% use Excel Tables, 17.7% array formulas. 10 `.xls` files weren't read, because LibreOffice isn't installed locally.
- 2026-11-04 (WP-11, WP-12): **Non-UI parts only, on the user's instruction to leave out UI, so neither is ticked.** Done: projects on disk, decisions with R-15's carry-over, spec generation from accepted findings, seed data, and R-19's check. Not done: the review screen, the French/Arabic switch and the embedded preview. `daftar project init|decide|reanalyze|generate` stands in for the Studio; it's outside C-5. `packages/spec/fixtures/generated` is the blueprint's workbook as generated by the worker: pytest confirms it's current, and the runtime's tests boot it, load it, and match its total rows.
- 2026-11-04 (WP-12): C-3 additions, both optional: `mapping.columns[].column`, each column's real letter, since a rejected column mustn't shift what a formula reads; and `mapping.totals`, for the total row R-22's export writes again. Seed rows name a link's target as `{"$ref": {"field", "value"}}`. Generation choices a reviewer might question: an accepted lookup formula runs in the engine, because `related` needs a relation's real keys and the generator can't promise one; a column the engine gets wrong, or can't run, stays as Excel's stored values and goes in `generation-report.json` under `parityFailures`, which is R-19's flag; a value that doesn't fit its type is blanked and listed under `badValues`; a key that a relation points at doesn't become its own list, even if an entity was accepted for it. Heuristics to confirm with a real workbook: cost and margin titles are level 1, name and phone titles are personal data, and retention defaults to 36 months with a question in the report. A tracker's status becomes a one-step-either-way workflow. A period with no year raises a `periodYear` question and its tab is left out until answered, and answering it isn't built yet: the edit carries `year` on the tab. An `excel` must be written for the first data row, and the generator assumes the first matching formula is on it.
- 2026-11-04 (WP-12): R-15 follows a finding by id, then by kind, sheet and column, since one more row changes every id; a changed proposal or a vanished finding becomes a conflict, listed in `conflicts.json`, and the new finding stays pending. The runtime loads `seed/` from beside the spec once, on first start, in one batch the owner can undo, recording in `_seed_state` any link whose target wasn't found.
- 2026-11-05 (WP-9): **User approved five C-7 additions the UI needs, and D-3's Studio API moves to Python.** The project and analyser code the Studio calls is all Python, so the worker serves those routes; the UI sees only HTTP. Additions: `/api/auth/status` also gives `app {name, locales, defaultLocale}`, so a firm's name is public to anyone who can reach the login page. Records carry `_labels {field: name}` beside a link, only where the user may read that row of the target. `GET /api/e/{entity}/aggregate?groupBy=&aggregate=&field=` honours the list's filters and row scope, refuses hidden fields, returns `{groups: [{key, value, label?}], truncated}` with at most 500 groups, and has no date buckets, since no widget in C-3 asks for them. Like list totals, it skips a row whose formula gave an Excel error, because its value isn't a number. `/api/meta` gives `roles` to the owner only. Accounts: nobody removes their own account, so a firm always keeps an owner, and a lock stops two owners removing each other; removing keeps the person's history and records. Changing your own password needs the current one, is throttled, and signs out your other devices. The owner can reset someone else's, which signs them out. There's no change of role, because nobody asked. A calculator's bad input now gets 400 `{fields}`, every bad input at once.
- 2026-11-04 (WP-9): Additions outside C-7, each needed by a requirement: `GET /api/auth/status` (does it need setup), `POST /api/auth/users` (owner only: without it there's no way to get a staff account, so R-17 can't be used), and `GET /api/audit.csv` (C-9's compliance export; a leading `=`, `+`, `-` or `@` is neutralised so a spreadsheet won't run it). `DAFTAR_PROCESSOR_NAME` is outside C-10, for R-24's processor. Audit records also have `revertOf` and `revertedBy`, and records have `_errors`.
- 2026-11-04 (WP-9): Choices a reviewer might question. Filters use `filter.<field>.<op>=value`. An Excel error goes beside the value in `_errors`, never as a zero or a blank (R-19). Hidden fields are refused for sort, filter and totals, since those would reveal values; hidden fields' audit values read `*`, and a formula's text isn't sent to any client, since it could give away a sensitive one. Calculators have no permissions in the spec (see WP-1), so every signed-in role runs them. Own-row scope means records the user created. Reminders are checked when asked for, against today in `DAFTAR_TZ`, not by a daily job: the result is the same and nothing can miss a run. Transitions set the state with `source: workflow`, and a role not listed gets a 409 with a reason so the board can show it. Links are resolved in the app, not by cascades, so every effect lands in history. An import or seed row may set a workflow state; a form can't.
- 2026-11-04 (WP-9): Engine formulas recompute by laying out the whole table per the mapping and copying `excel` down from the first data row, so `excel` must be written for row `headerRow + 1`. That made a WP-1 mistake visible: the payments example's formulas didn't match its own columns, now fixed. It costs a full table per write, which is fine for a small firm's data; revisit if it isn't. Merged monthly tabs lay out on the first source only. **WP-12 must keep `excel` in that form, and tell apart tabs when a formula reads a specific tab.** The Node binding has no clock override, unlike Python's: a live app wants the real date anyway.
- 2026-11-04 (WP-9): The TypeScript evaluator and the Python one share `packages/spec/fixtures/expression-cases.json` (124 cases), and the Node engine binding must agree too. Loose ends: login throttling is per process and per username, enough for one firm's one server. Kysely can't type tables that come from a spec, so `no-unsafe-*` is off for `apps/runtime/src`.
- 2026-11-04 (WP-8): **Not ticked. Its checks can't all run yet:** "same or better than rules on every metric" and tuning the thresholds need the labelled dev pool, and OQ-4 is decided there too. The RTX 4070 timing couldn't be run: the GPU reports free but refuses even 14 layers, possibly because `nanoscope-worker-gpu` holds it (WSL hides per-process use), and that isn't this project's to stop. Measured instead, CPU only, `qwen3.5:9b` Q4_K_M: a 5-sheet, 10,000-row workbook took 286 s against the 300 s limit, and rules alone 2.8 s. Rerun on the GPU when it's free.
- 2026-11-05 (WP-8): **RTX 4070 timing measured on a quiet machine: 49 s for a 5-sheet, 10,000-row workbook, against the 300 s limit**, `qwen3.5:9b` Q4_K_M, 88% on the GPU, about 26 tokens a second, 33 s to load. The result names the model, so the run counts. It's one synthetic workbook with no close ties, so only 5 answers were asked for; one with many ties asks for more, at 3 to 5 votes each. WP-8 stays unticked: its other two checks need the labelled dev pool.
- 2026-11-05 (WP-8): **An earlier attempt the same day gave no figure.** The GPU was free and the model loaded 79% on it, but other work on the machine kept the load average at 37 to 51, and with 21% of the model on the CPU, those threads set the pace: about 0.5 tokens a second, GPU mostly idle, and the second call passed the 180 s limit. That 675 s run ended rules only, so it isn't a figure. Rerun on a quiet machine. Other jobs weren't stopped, as they aren't this project's. `daftar-ollama` is stopped again, and needs its 150 s warm-up.
- 2026-11-05 (WP-8): A cold model took over 3 minutes to load, passed the client's 180 s limit, and the analysis fell back to rules only with nothing said. The first call now allows 600 s. A model lost at any point now gives a wholly rules-only result, not one with some of its answers, marked `engine.modelUnavailable` (additive to C-2), and `daftar analyze` warns. Answers already received stay cached, so a rerun carries on.
- 2026-11-04 (WP-8): The default model needs Ollama 0.30+, and the installed one is 0.21, so `ollama pull` fails with a 412. Tested through a separate container, `daftar-ollama`, on port 11435 with its own volume, now stopped: `docker start daftar-ollama`, with `DAFTAR_LLM_BASE_URL=http://localhost:11435/v1` and `DAFTAR_LLM_MODEL=qwen3.5:9b`. A `-cpu` variant sets `num_gpu 0`. **Context is limited to 8192 there, because the model's default of 262,144 inflates memory.** A deployment needs the same.
- 2026-11-04 (WP-8): **Deviation from the plan's outcome: rewording is off by default**, behind `DAFTAR_LLM_REWORD=1`, outside C-10. In a real run the model turned "revient dans" into "redevient", which keeps every fact and says the wrong thing, and it turned an Arabic sentence into English. The fact guard and a new language guard catch only some of this, and the templates are already clear. R-10 says the model *may* reword, so this stays within it. Real-model findings fixed: names like Ligne are refused; tabs of a series share one name; the title above a table reaches the prompt; refused answers are cached, so a rerun takes 0 s and is identical. Answers on a tutoring workbook were good in both languages (`ولي الأمر`, `هاتف ولي الأمر`, `Paiements / مدفوعات`), but that's one workbook, judged by eye.
- 2026-11-04 (WP-8): Scope of model use: naming entities and fields; votes on a sheet-kind tie within 0.15, a low-confidence header, and `possible` name clusters, where it can only remove a proposal. `needsReview` marks what it couldn't settle. An unreachable model leaves a valid rules-only analysis. The Darja glossary is a hand-written start and hasn't been reviewed by a speaker. Cache lives in `~/.cache/daftar/llm`; it holds samples of cell values, and it's on the operator's machine only.
- 2026-11-04 (WP-7): **Not ticked, for the same reason as WP-5: its done-when needs dev-pool metrics, which need human labels.** The code is complete, and the scorer now reports monthly-tab F1 as pairs of sheets. Open risk: on 455 unlabelled public workbooks it proposes 263 entities, 133 colour statuses and 51 relations, and some are visibly wrong. Precision is unknown until labels exist. They're proposals needing a person's accept, so a wrong one costs review time, not data.
- 2026-11-04 (WP-7): Rules, as WP-7 asks. **Names:** fingerprint removes case, accents, Arabic letter variants, tashkeel, titles (M., Mme, السيد, Sarl), punctuation and word order; digits inside a Latin word read as Arabizi, and a trailing number stays a number. Names cluster on equal fingerprints (`normalised`, score 0.86), token-sort similarity of 93+ (`close`, 0.75), or 88+ or an initial (`possible`, 0.65); numbers must match, under 5 letters never fuzzy-matches, and over 2,000 distinct names skips fuzzy matching. No Latin-to-Arabic matching; that's left for WP-8. rapidfuzz stands in for Splink. **Entities:** a proposal needs spelling variants or the same column on several sheets (50% shared, at least 3); what a name determines (95% consistent) is listed but isn't enough alone. Validation-list columns, status-named columns and email columns are skipped. **Relations:** lookups and validation lists from another sheet are high (0.9). Inclusion needs 95% of at least 3 values in a unique column on another sheet, capped at 0.84, and needs the target to be its table's first column, ID-named or similarly named (80%); at least 5 values unless names match. Bare counters, copies of a table (80% same columns), tabs of one series and links into other files are refused. Each column gets one target, and links can't loop. Fuzzy name matching can mislead: "Marque" and "Remarque" count as similar. **Periods:** two or more tabs, 80% same columns, names giving a French, Arabic or English month, a numeric month, a quarter or a year. High needs identical columns and known years. A school year such as `2011-2012` reads as 2011. A period with no year is written `--MM`, so **WP-12 must ask for the year.** **Statuses:** conditional formats with `equal`, `containsText` or `="x"` rules (0.9); fills with two or more colours and 90% consistent with the text (0.8 with a status title, otherwise 0.65); colours on blank cells only (0.5). White and black don't count, and a single coloured value needs a status title. A coloured choice column makes a sheet score as a tracker.
- 2026-11-04 (WP-6): Parity on the unlabelled public pool, with `daftar parity`: 372,552 formula cells compared, 99.01% equal to Excel's stored results; 289 of 347 workbooks match on every cell; 10 workbooks hold 88% of the differences. data.gouv.fr 100.00% (7 workbooks), Enron .xls 99.85% (43), Enron .xlsx 99.81% (155), SpreadsheetBench 88.91% (142). By category: date 99.9, operators 99.7, math 99.2, logical 98.5, statistical 98.5, text 98.1, information 97.2, other 95.2, lookup 93.0. **Not a published figure:** it's cell-weighted with no confidence interval, the set isn't frozen, and the pool isn't WP-4's dev pool, so WP-16 must measure it properly. The Enron .xlsx results may date from a batch conversion, so that figure may flatter. Rerun when the dev pool exists. Ticked because parity needs no human labels.
- 2026-11-04 (WP-6): Real gaps in Formualizer 0.13 found by that run, left visible on purpose: structured references such as `Table[#This Row]` and `Table[]` give #NAME?; `WEEKNUM(x,21)` gives #VALUE!; `ROWS($B$7:$B23)` inside B23 raises a false circular reference; some array formulas with SUMPRODUCT, SEARCH or SMALL give wrong numbers; `INDEX(#REF!,...)` gives #N/A, not #REF!. 4 workbooks failed to load with OSError, not yet diagnosed. These are worth reporting upstream. **WP-12 must flag any computed column whose engine results differ from Excel's stored ones, because R-19 forbids silently wrong results and the analyser has no engine results to go on.**
- 2026-11-05 (WP-2, WP-6): Structured references such as `Table1[[#This Row],[Qty]]` gave #NAME? in the engine, and left a formula that can't run after export. The reader now expands them, as C-1 already promised A1 formulas, and keeps the file's text in `fStructured` (additive). Only 17 of about 17,000 pool workbooks use them, but that pool is mostly old Enron files, and Excel inserts them by default in any Table. A reference to a whole column becomes a fixed range, so like a range typed by hand, it doesn't grow with rows added in the app. Anything unresolved stays as written and shows #NAME?, which R-19's check flags.
- 2026-11-05 (WP-6): The unexplained load failures were the engine's ZIP reader, stricter than Excel's: it refuses ZIP64 entries and mismatched local and central headers. 5 of 855 public files hit this. The engine wrapper now repacks such a file into a temporary plain ZIP and retries. Formualizer 0.13's other reported gaps were probed again: `WEEKNUM(x,21)` and `INDEX(#REF!,1)` now give the right results on simple cases, so that part of the older note may be stale. Measured on the 17 pool workbooks with structured references: formula cells equal to Excel went from 15% to 61%, and workbooks fully equal from 0 to 8. What's left: 278 cells read the table holding them, which looks like a real circular reference; 216 #NAME?, in array formulas, references outside a Table's rows, and Tables in other files, which are flagged rather than wrong; 92 are `TEXT(date,"mmmm")` saved by a Spanish Excel, a locale difference.
- 2026-11-04 (WP-6): Translation covers 64 functions, on one record at a time. Each translated column is run against Excel's stored results where they exist, and any disagreement sends it to the engine with the reason on the finding. Columns using TODAY or NOW, and files not saved by Excel, stay unverified. Absolute cells such as `$F$1`, whole columns, other rows and non-exact lookups stay with the engine. Keys in `expr` are provisional, `col_<letter>`; WP-12 maps them to spec keys. `evaluate.py` is the reference for WP-9's evaluator, and `test_formulas.py`'s table of cases should be reused there. The rule on near-zero results stays as written: 1e-16 against 0 is a mismatch.
- 2026-11-04 (WP-6): Additions outside the contracts: `daftar parity PATH... -o DIR`, because the oracle needs no labels; a `calculator` finding's `testCases` come from stored results. Parity freezes the clock at the file's last-saved time, and leaves out RAND and NOW, which can't match by design (448 cells). `list_functions()` only lists custom functions in this Formualizer, so support is probed by evaluating the name. A stored result of only spaces reads back empty, so spaces compare equal to empty. IronCalc 0.9.1 is a dev dependency only; it agrees on every fixture.
- 2026-11-04 (WP-5): **Not ticked: its done-when needs dev-pool metrics, and the dev pool is WP-4, which needs the user's labels.** The code is complete and tested on a synthetic corpus (`tests/structure_corpus.py`) plus 150 random grids. That corpus was written alongside the rules, so its perfect score is a regression floor, not an accuracy figure; it must not be quoted as one. Run `daftar eval --labels eval/labels --split dev` when labels exist and record the baseline here.
- 2026-11-04 (WP-5): Ran the reader and analyser over 913 real public workbooks, unlabelled, so this tests robustness and not accuracy: data.gouv.fr 60, SpreadsheetBench Verified 395, Enron 58 .xls and 400 sampled .xlsx. The files sit in the git-ignored `eval/private/pool/` and the Enron ones hold personal data. Result on the final code: no crashes, none unreadable. Bugs this found: Mac Excel wasn't recognised as Excel while "Microsoft Excel Compatible / Openpyxl" was, so `resultsFrom` now uses an exact list; a gradient conditional format crashed the read; openpyxl refused some real charts, so drawings are now skipped on load like pivots; LibreOffice wrote malformed XML for some .xls, so converted files are now repaired; headers made of a label plus a rising series, built by formulas, or with repeated names were missed; `multichoice` fired on slashes.
- 2026-11-04 (WP-5): Measured on the 58 real Enron .xls: restoring stored results changed 13,414 of 153,909 formula cells (8.7%), 2,773 of them numeric, in 6 workbooks. So LibreOffice's recalculation does differ from Excel's stored results on real files, and the restore is needed. Part of this is volatile functions; the rest isn't broken down yet. Correction to the plan: the figshare Enron archive holds 15,871 .xlsx and only 58 .xls, so "all of Enron is .xls" is false for this source. Its .xlsx files all claim Excel and look batch-converted (an inference), so their results may date from that conversion. WP-4 should check this before relying on them as the parity reference, and should get its .xls quota elsewhere.
- 2026-11-04 (WP-5): Open signal from that scan: 77% of tables in the Enron .xlsx sample and 24% in SpreadsheetBench have no header, against 10% in data.gouv. 10 of 120 workbooks in a spot check held half the tables. Without labels it's unknown how many of these are right, so no rule was tuned to this number. It's the first thing to check on the dev pool.
- 2026-11-04 (WP-5): The cell-role classifier is hand-weighted rules over the research's features, not the GBDT it suggests, because a trained model needs labels that don't exist yet. Revisit once the dev pool shows where rules fail. Known weak spots, seen on untuned test layouts and left for real data to judge: a crosstab with months across its columns reads as `register` (R-8 only covers tabs); an invoice with a line table reads as `formulaModel`; a client list with a date and a balance reads as `ledger`; plain text over plain text can't be told from a header, so it's flagged low confidence.
- 2026-11-04 (WP-5): C-2 schema is `analyser/analysis.schema.json`, with `proposal` shapes for the kinds WP-5 emits; WP-6 and WP-7 add theirs. `table.evidence` covers header, data and total rows, and `proposal.dataRange` the records only. `sheet` is null on workbook-level findings. A `totalRow` can have source `afterTotal`, for tax lines under a total, with no aggregates. Sheets marked `notConverted` get no table findings. `link` is emitted only for a validation list drawn from another sheet until WP-7 adds relations; `child` is never emitted, because it's the reverse of a `link`.
- 2026-11-04 (WP-5): `/v1/read` now keeps each snapshot for `/v1/analyze`, which addresses it by hash: on disk in a private temporary folder, newest 16, gone when the process stops. C-4 has no store, so this is the implementation's choice. Rejected files still leave nothing. Analyses run one at a time. An unknown snapshot or job is a 404 with code `unreadable`, as C-4 has no better code. Until WP-8, `llm: on` gives the rules-only result. A 1,000,000-cell sheet analysed in 17 s, after 81 s to read.
- 2026-11-04 (WP-5): `daftar eval` now runs the analyser when given no `--analyses`. A workbook with no formula-engine results at all is listed as `parityNotRun` and left out of parity, not scored as 0%, because the engine doesn't exist until WP-6. A results file missing one formula still counts it as wrong.
- 2026-11-04 (WP-13): C-4 additions, all optional: `/v1/export` also takes `locale`, `formulas` and `timezone`; `/v1/reimport/diff` also takes `timezone`, returns `problems`, and each changed row carries `id` and `version`. C-4's "keys by entity" is sent as each entity's rows, because reporting changed fields needs the current values as well as the keys. Formualizer's recalculation is called through `formulas/engine.py`, and if it fails the file still goes out with the app's stored values.
- 2026-11-04 (WP-13): Export choices: every row lands in exactly one tab, a period the workbook never had gets its own tab (`2026-04`, or `Sans période`), and re-import reads those tabs back. Rows above the header row, such as a title, aren't in the spec, so they aren't written. An entity the generator derived, such as `Parent`, exports as a sheet of its own. A role that can't see everything gets values rather than formulas, since a formula could rebuild what's masked, and no total over a masked column. A link shows its target's first key column, or is masked if the role can't read it.
- 2026-11-04 (WP-13): Re-import choices: rows match on the period (not the exact date) plus the key columns. Spacing alone isn't an edit, since the reader tidies it. Nothing is guessed: a value that doesn't fit, a missing or repeated key, or typing over a mask goes in `problems` and that value is left alone. Rows whose key the role can't see therefore can't be matched. A sheet absent from the file says nothing about its rows. A row edited after the comparison is skipped and listed as `stale`. A refused value rejects the whole batch and names the row. A link naming nothing is reported and the old link stays. A diff belongs to its creator, is removed when applied, and an unapplied one is purged after 7 days because it holds the firm's data. Import needs `read` as well as `import`, since the diff shows current values. Package left unticked: the apply screen is UI, excluded for now.
- 2026-11-04 (WP-13): Fixed in the generator: a year-less tab's `--01` period failed C-3's own pattern, so the mapping now stores the year the owner gave. The reader's datetime still assumes `+01:00`, which is right for Algiers, the only configured zone; re-import ignores that offset and uses the configured zone.
- 2026-11-04 (WP-4): Added `daftar label`, a local labelling screen the blueprint didn't list, at the user's request: hand-editing JSON would be slow and error-prone. It binds to 127.0.0.1 and refuses other hosts. It keeps formula results out of a person's reach and records active time, so the 30–90 minute estimate gets measured. Field names aren't scored, so drafts fill them from the headers. Stricter than C-6: test labels always start blank, in the screen and in `--prelabel`, because correcting guesses anchors the person and that split is what's published. Everything in `eval/private/pool` tuned the analyser in WP-5 and WP-7, so it can only go in dev. Package not ticked: nobody has labelled yet, and the census quotas, the first 30 test workbooks and the double-labelled 25% are still to do.
- 2026-11-04 (WP-4): The user doesn't read French, so the first batch includes three English workbooks and the guide gained an English section. French workbooks wait for a French-speaking labeller. Replicas stay out of the published number, because the analyser's author wrote them, even though WP-4 lists them beside the test workbooks. So the test split needs fresh real workbooks, which is an open sourcing question for the user. The `sb_*` workbooks have an unverified licence, so they and their labels stay out of the repository; only their ids and hashes are in the manifest.
- 2026-11-04 (WP-4): User's decision, changing how WP-4 is met: a blind agent (`eval/blind/run.py`) is the main labeller on dev, including French, and the user resolves disagreements. This replaces human labels and the human second labeller, so any number scored against these labels must say that the agent labelled and the user reviewed. The agent can't see the analyser, its guesses or anyone's labels, but the same person wrote its guide and the analyser. Guide rules on `choice`, `referenceList`, `formulaModel`, `date` and relations were tightened from the disagreements on `sb_2768`, `sb_82_38` and `sb_52216`, so agreement on those three is not independent evidence. Test split not decided.
- 2026-11-04 (WP-4): Outside check against DECO's human labels (`eval/blind/deco.py`, private under OQ-5), on 30 workbooks sampled with a fixed seed after skipping 72 that looked personal and 16 too long, so it leans to small workbooks. Within 2 cells: Opus 0.96 tables, 0.97 headers; Sonnet 0.88, 0.95; Daftar 0.63, 0.73. DECO has no types, sheet kinds or relations, so it says nothing about those. Opus is the main labeller and Sonnet the second opinion; a person rules where they differ.
- 2026-11-05 (WP-7, WP-12, WP-13): Bug fixed: tabs of a series were compared with a fuzzy score that ignores order, then read by the first tab's letters, so a tab with reordered columns loaded values into the wrong fields, with no report if the types fitted. Columns now match by name: same name, then same name without its dates, then close (80+), each used once. Tabs join when 60% of the narrower tab's columns and 50% of the wider's match, and a tab joins every group it fits any tab of, so order doesn't matter. A tab that gained a column joins too, which also answers `dg050`: monthly tabs against the unreviewed Opus labels on 9 dev workbooks went from 18 of 31 pairs to 31 of 31 with none extra, though those rules were written with `dg050` in view, so it isn't independent. Over the 570 pool workbooks with at least two period-named tabs, 93 groupings changed: 5,457 pairs newly joined, 1,798 of them sharing only 50-80% of their columns, and 226 split, mostly with under half shared. No labels exist for these, so precision is unknown. It's lenient on purpose: values go to fields by name, so a wrong join costs a sparse column and a look, not misplaced data, and it's a medium-confidence proposal. C-2 additions: each tab in `periodUnion` lists its `columns`, and the series' `columns` are the union. C-3 additions, both optional: `mapping.sources[].columns` and `headerRow`, set only when tabs differ. The first tab's letters stay, as formulas are written for them, and later columns go after its table. Export keeps each tab's layout; a value for a column its tab never had adds that column to the tab; a tab whose letters moved gets values, not formulas. **One formula runs for a whole series, so a tab with a different formula, typed numbers, a failing parity check or no such column turns that field into plain data for every tab, listed under `seriesFormulas` in the generation report.** That costs calculation on new rows rather than risking wrong results (R-19), so the review screen must show it. Key columns must exist in every tab. A second table on a series tab is now its own list; before, it was dropped.
- 2026-11-04 (WP-14): User's decision on OQ-1: support both, and each firm runs one. No sync between a box and a server; a firm moves between them by backup and restore. `--target lan` uses Caddy's private CA with `./export-ca` for phones; `--target vps` needs a domain and an email and gets a public certificate; `local` stays as a plain-HTTP preview on 127.0.0.1. `./offsite` rsyncs dumps to `DAFTAR_OFFSITE`, a second disk or a server, from the host's cron; dumps aren't encrypted, so the destination must be protected, and the README says so. `deploy/e2e.py` proves HTTPS with a trusted root, a warning without it, HTTPS-only cookies, the HTTP redirect, and recovery of data and accounts on a new bundle with new secrets. Correction to the note below: `DAFTAR_SECRET` only hashes session tokens, so losing `.env` means logging in again, not losing accounts. **Still open for the tick: a real certificate on a real domain and server; a clean VM rather than a CI runner; the owner page from WP-10.** A root CA on a phone trusts whoever controls that box for any site, so the README limits it to firm devices and says to protect the machine.
- 2026-11-04 (WP-7): **Still not ticked: its metrics need reviewed labels.** Against the unreviewed Opus labels on 9 dev workbooks, relations went from 8 of 15 found to 11 of 15, with none extra; monthly tabs stayed at 18 of 31, because Opus also counts tabs with an extra column. These rules were written from those workbooks, so that isn't an independent figure. Added: `aggregateFormula` evidence in C-2, additive, for a `SUMIFS`-style match on another sheet, at confidence 0.75. It stays a finding and never becomes a link, because neither column identifies one row. A "Client" column whose name matches a sheet called "Clients" may now link to any unique text column there, with retyped names counting. Seed links now use the target's own spelling, which also fixes keys that differed only by case or accents: they matched during analysis, then failed to load. Against the user's saved labels relations fell from 0.67 to 0.56, because `sb_2768`'s saved label predates the user's ruling that those two relations are real.
- 2026-11-04 (WP-14): **Hosting-neutral part done, not ticked: TLS, the deploy recipe and the backup target wait for OQ-1, and the first-login page for WP-10.** `daftar bundle` writes C-8 with generated secrets (`.env` mode 600), images pinned by digest or tag, and refuses an existing folder, so a rebuild can't replace a client's secrets. `deploy/e2e.py` proves in CI, on Docker rather than a clean VM: first start, owner setup through the API with the seed loaded, then backup, wipe and restore with identical data and working logins. Until OQ-1 the proxy serves plain HTTP on 127.0.0.1 only, so the bundle isn't reachable from other devices yet. The README files already describe the owner page WP-10 will add; the French and Arabic haven't been natively reviewed. Choices a reviewer might question: images travel as a `docker save` file (`--images`), because no registry has been chosen; backups stay in `backups/` until OQ-1 picks a target, and the README tells the owner to copy them elsewhere. `.env` isn't in a backup, so losing it locks out every session and the database password: the README says to keep it safe.
- 2026-11-04 (WP-14): D-9 needed a real split: the worker imported the analyser for everything. `sheet/` now holds the grid, name matching and value conversion that re-import needs; `client_app` serves only health, export and re-import; the image's `client` target deletes the analyser, LLM, evaluation and project code, and a test plus `deploy/e2e.py` check they're gone. That image still holds LibreOffice for re-importing .xls, at 883 MB.
- 2026-11-04 (WP-5): **Baseline on DECO, not the dev pool, so WP-5 stays unticked until labelling runs.** Rules were tuned only on a fixed 668-workbook split, and measured on 338 kept back, which include the agents' 30. Holdout, old to new, on 167 table sheets: tables within 2 cells F1 0.309 to 0.495, exact 0.161 to 0.350, headers 0.578 to 0.711, set-aside sheets with no table 12/80 to 16/80. The holdout was measured to report only and no rule was chosen from it. The agents' 30: tables 0.63 to 0.78, headers 0.73 to 0.81. On the user's 4 reviewed workbooks nothing changed overall: tables 0.78, headers 0.75; a stacked-invoice regression seen there was fixed before this commit. Opus gets 0.96 and 0.97 there, on a sample that leans small and clean; it wasn't run on the full holdout. DECO's own labels are noisy: some sheets mark only one of several tables, so a perfect score isn't reachable. Header scoring now ignores DECO's tall label columns, which aren't header rows; this raised every header figure, the agents' stayed at 0.97 and 0.95.
- 2026-11-05 (WP-5, WP-12): Group labels are no longer lost. Two or more lone labels inside a table become a `groupColumn` finding, a new C-2 kind (additive), at medium confidence (0.7). Accepting it gives the entity a text field `Groupe`, each record taking the label above it; records before the first label stay blank. Rejecting it keeps today's behaviour. If nothing else identifies a row, the group joins the key columns. **An export writes it as an ordinary column after the table, not as heading rows, so this one thing departs from R-22's original layout: a heading row can't be told apart from a record on the way back in.** One lone label stays a note, because it could as well be a remark.
- 2026-11-04 (WP-5): Rules added: blocks under one clear header stay one table across up to 3 blank rows and group labels, until a new header; an empty column doesn't split thin spaced columns or figures with no labels of their own; a full row of labels under sparse rows sets those rows aside as a title; a row of rising dates is a header; thin plain-text scraps beside a wide table aren't tables; a sheet mostly outside short tables is `notConverted`, form or report, at confidence 0.6. Cost seen on the tune split: sheets with DECO tables and none found rose from 13 to 18, so 5 more sheets now rely on review to be converted. **Known limit: a group label is left out of the records, as `noteRows`, and not yet kept as a column value, so that information reaches the app only if a person adds it.** DECO's labels only informed these hand-written rules; no model was trained on them, so OQ-5 doesn't block shipping them.
- 2026-11-05 (WP-4): Added `daftar agreement FIRST SECOND -o FILE`, outside C-5, for the double-labelled share: F1 on boundaries, headers, relations and monthly tabs, Cohen's kappa on sheet kinds and field types, each with a workbook-level interval. Drafts count, since disagreement between drafts is what a person rules on. Reports hold counts only. **Opus and Sonnet on the 9 dev workbooks score high (kinds 0.97, types 0.91), but the guide was tightened from disagreements on three of them, so that isn't independent evidence; only monthly tabs are low, at 0.45.**
- 2026-11-04 (WP-4): User's decision: when labelling runs, Opus labels every workbook and Sonnet double-labels 25%, about $70 per pass over 200 workbooks. Labelling is deferred, so WP-4 stays open; the user's labels stay in `eval/labels/` and the agent's in `eval/private/agent/`.
- 2026-11-03 (WP-3): Additions to C-5 and C-6, all additive: `eval` gains `--analyses`, `--manifest`, `--prelabel` and `--freeze`, and labels gain `status`. **`--analyses` is required until WP-5 exists; WP-5 should make it optional by running the analyser.** Formula values arrive beside each analysis as `<id>.parity.json`, because C-2 has no place for them; WP-6 writes that file.
- 2026-11-03 (WP-3): Interface for WP-5 to WP-7. `evaluation/predictions.py` is the only code that reads C-2 findings, and it expects: `table` and `header` findings carry their ranges in `evidence`; `fieldType` has the column range in `evidence[0]` and `proposal.type`; `relation` has `proposal.from` and `proposal.to`, each `{sheet, column}`; `snapshotSha256` equals C-1 `source.sha256`. If WP-5 defines other shapes, change this one file.
- 2026-11-03 (WP-3): Scoring choices a reviewer might question. Stress workbooks stay out of the headline, as the research says, and appear under their stratum. A workbook with no analysis, and a formula with no value, score as wrong and are listed; nothing is skipped. Metrics pool across workbooks, then the bootstrap resamples workbooks (2,000 draws, fixed seed, percentile interval). Header F1 compares (sheet, row), so two side-by-side tables on one row count once. Types use the C-3 set from R-5, not the research's 14 types. R-19's tolerance is relative only, so 1e-16 against an exact 0 is a mismatch; **WP-6 may want the user's view if Excel's near-zero rounding makes this bite.** The test split's report holds no per-workbook detail.
- 2026-11-03 (WP-3): Sheet kind labels use R-3's six outcomes, with `reason` for `notConverted`, not the research's ten kinds. The cell-role layer is stored but not scored. Inter-annotator agreement isn't in the harness: WP-3's metrics don't list it, but **WP-4's 25% double labelling will need kappa and boundary agreement.**
- 2026-11-03: User-delegated decision: C-1 gains `hiddenRows` and `hiddenColumns`, an additive change. Hidden rows can hold old data or helper columns, and R-2's "hidden state" covers them. Rows hidden by an AutoFilter look the same as manually hidden ones.
- 2026-11-03 (WP-2): openpyxl loads through a copy with its pivot links removed, because it parses pivots on load and raises on any it dislikes; pivots are reported from the raw XML. The largest allowed file (1,000,000 cells) took 51 s and 1.1 GB peak on the dev machine. Macros are never run: openpyxl doesn't execute them, and LibreOffice's profile disables them.
- 2026-11-03 (WP-2): Census counts each byte-identical file once and holds only counts and function names, no cell values. It runs the full reader per file, which is slower than the prior art's regex scan but counts .xls and .ods the same way. File paths are in the output, so treat it as private if paths name clients.
