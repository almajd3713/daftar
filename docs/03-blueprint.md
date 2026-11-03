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
- **R-24**: The runtime exports a processing register built from the spec: personal-data entities and fields, roles, the retention declared per entity, and the processor. Change history serves as the automated log that Law 25-11 requires.
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
  - **Never force LibreOffice to recalculate when converting.** Its default, "never recalculate" on load, keeps Excel's stored results. Forcing recalculation replaces them with LibreOffice's own, and the formula parity score would then measure "same as LibreOffice", not "same as Excel". This matters because about a third of the test set and all of Enron are .xls. Recalculating LibreOffice is allowed only as a separate cross-check engine, never in the conversion path.
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
- `sheets[]`: `{name, index, state: visible|hidden|veryHidden, protected, rtl, dimension, cells[], merges[], validations[], conditionalFormats[], tables[]}`
  - Cells are sparse: `{ref, v, t: n|s|b|d|e, f?, fmt?, style?: {fill?, color?, bold?}, comment?}`. Here `v` is the stored or typed value and `f` is the A1 formula with English function names.
- `definedNames[]`: `{name, scope?, ref}`
- `unsupported[]`: `{kind: pivot|chart|image|shape|macro|externalLink|other, sheet?, ref?}`

**C-2 Analysis** (analyser → Studio → spec generator). JSON, `analysisVersion: 1`:
- `{snapshotSha256, engine: {rulesVersion, model?, quant?}, sheets[]: {name, outcome, reason?, findingIds[]}, findings[]}`
- Each finding: `{id, kind, sheet, evidence: [A1 ranges], proposal, alternatives[], confidence: {level, score, source: rules|votes}, explanation: {fr, ar}, decision: {status: pending|accepted|edited|rejected, value?, by?, at?}}`
  - `id` is stable: a hash of the kind and the normalised evidence. That is what makes R-15 possible.
  - `kind` is one of: sheetKind, table, header, totalRow, fieldType, choiceList, statusColours, entityMerge, relation, periodUnion, computedField, calculator, anomaly, unsupported.
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
- `eval --labels DIR --split dev|test -o DIR`
- `bundle PROJECT -o DIR`
- `studio` (starts the Studio stack)

**C-6 Evaluation set:**
- `eval/manifest.csv`: id, source, licence, language, stratum, split (dev|test), consent, sha256.
- `eval/labels/<id>.json`: the label set in research notes `corpora_and_mess.md` §4, plus each formula cell's stored Excel result. Those results are read from the original file before any conversion. Workbooks whose `resultsFrom` isn't `excel` are left out of the parity metric and listed in the report.
- Publishable workbooks go in `eval/workbooks/`. Everything else goes in the git-ignored `eval/private/`.
- Once frozen, the test split changes only by adding files.

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
- Errors:
  - 400 `{fields: {key: {fr, ar}}}`
  - 401, 403, 404
  - 409 for a stale write or a refused transition

**C-8 Bundle layout** (the output of `daftar bundle`; target-neutral until OQ-1):
- `compose.yaml`: reverse proxy, runtime, worker (no analyser, no model), Postgres, backup job
- `.env` with secrets generated at bundle time; `daftar.spec.json`; `seed/<entity>.jsonl`
- `backup` and `restore` commands
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
- **Covers**: R-16, R-20, R-21, D-12.
- **Depends on**: WP-9. **Parallel with**: Phase 2.
- **Build**:
  - Lists with filters and totals, forms, a detail page with a history timeline, a board for workflows, dashboards and calculators.
  - A language switch that changes the direction.
  - In-app reminders.
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
- **Depends on**: WP-13, WP-14. **Parallel with**: none.
- **Build**: French/Arabic consent for anonymised reuse of the workbook; templates for the processor agreement and the ANPDP declaration checklist (the research compliance checklist); the conversion; the handover pack; the case study draft.
- **Watch out**: the legal templates come from secondary sources. Stop for a lawyer's review before anyone signs.

## Open questions

- **OQ-1 Where client apps run** (user, before WP-14):
  - **The options:** a LAN box at the firm (works offline; a private CA root on every phone; backups to a second disk) or an Algerian VPS (1,900–9,500 DA/month; a domain and easy TLS; needs internet; a sub-processor), or both.
  - **What depends on it:** C-8's proxy and TLS setup, and the backup target.
- **OQ-2 Offline writes** (after OQ-1 and the first pilot feedback, in WP-14 or WP-17): a queue of pending changes in the installable web app (v1 option) or PowerSync (v2). It matters only if staff work away from the server.
- **OQ-3 Dynamic arrays in v1** (WP-16 census): add them if the pilot and Sheetpedia counts show them in more than 5% of formula-using workbooks.
- **OQ-4 Default model** (WP-8): Qwen3.5-9B vs Gemma 4 E4B at Q4, compared on the dev pool. Keep whichever wins on naming and ties.
- **OQ-5 DECO labels** (before WP-16 publishes): ask the DECO authors about licensing. Without permission, DECO-derived labels stay in `eval/private/`.

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

- [ ] WP-1: Repository, CI and the spec schema
- [ ] WP-2: Reader and census
- [ ] WP-3: Labels and the evaluation harness
- [ ] WP-4: First labelled workbooks
- [ ] WP-5: Structure: tables, headers, totals, types, sheet kind
- [ ] WP-6: Formulas: computed fields and calculators
- [ ] WP-7: Entities, relations, monthly tabs, choices and colour statuses
- [ ] WP-8: Language model: ties, names and wording
- [ ] WP-9: Runtime core
- [ ] WP-10: Runtime UI
- [ ] WP-11: Studio: projects and the review screen
- [ ] WP-12: Spec generation, data load and preview
- [ ] WP-13: Export and re-import
- [ ] WP-14: Bundle, deploy and backup
- [ ] WP-15: Competitor bake-off
- [ ] WP-16: Freeze 100 test workbooks and publish accuracy
- [ ] WP-17: First pilot

## Log

- 2026-11-03: Plan written from `01-refined-idea.md` and `02-research.md`. Client deployment target left open by the user (OQ-1).
- 2026-11-03: Conversion no longer forces LibreOffice to recalculate; doing so would overwrite Excel's stored results, which the parity metric uses as its reference. Added `resultsFrom` to C-1, and the parity metric now counts only Excel-produced results.
- 2026-11-03 (WP-1): C-3 details filled in beyond the contract's wording, all additive: `expr` is required only for `eval: translated`, since an engine formula has no tree; computed fields carry `resultType`; every expression node carries `valueType` (our reading of "typed AST"); fields carry `personalData` (R-24 lists fields) and `level` 0/1 (R-17). `personalData: true` on an entity requires `retention`. `provenance.decision` allows only accepted or edited, since rejected findings never reach a spec. `specVersion` accepts major 1 only.
- 2026-11-03 (WP-1): The schema can't check cross-references (a view's `entity` exists, field keys are unique). Only the example specs are checked, in pytest. **WP-9's spec loader must enforce these.**
- 2026-11-03 (WP-1): Note for WP-9: spec keys must start with a letter, so system columns named with a leading `_` (`_id`, `_created_by`) can never collide with a spec field.
- 2026-11-03 (WP-1): The spec has no calculator permissions, so every signed-in role can run a calculator. Calculator outputs can be `level: 1`.
- 2026-11-03 (WP-1): Tagged unions use `oneOf` plus Ajv's `discriminator` keyword, which standard JSON Schema ignores. The Python validator implements it too, so errors name the one branch that applies and both languages report the same paths; `fixtures/invalid-cases.json` runs in both. Messages may differ, paths may not.
- 2026-11-03 (WP-1): Surprise: Python's `$` matches before a trailing newline, so `"abc\n"` passed as a key under stock `jsonschema` while Ajv refused it. The Python validator now anchors patterns strictly, and schema patterns use `[0-9]`, not `\d`, which matches Arabic digits in Python.
- 2026-11-03 (WP-1): Pinned TypeScript 6.0.3, not 7, because typescript-eslint supports `<6.1`. Licence field is `AGPL-3.0-only`. The worker has a `/healthz` endpoint outside C-4, for the Compose healthcheck, and FastAPI arrives now rather than in WP-2. Dev Compose adds `POSTGRES_PASSWORD` and `DAFTAR_DEV_DB_PORT`, outside C-10 and dev-only. `reports/` is git-ignored as a duplicate of `docs/02-research.md`.
- 2026-11-03 (WP-1): User decision before the first push: only the code and this blueprint go public. `docs/01-refined-idea.md`, `docs/02-research.md`, `research_notes/` and `reports/` stay local and git-ignored, because they hold pricing and pilot plans.
