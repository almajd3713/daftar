# Daftar UI and server contract

**Status: a proposal.** Nothing here is built on the Studio side yet. The UI and the server each change this file before changing code that depends on it.

It starts from what the UI agent said it will assume (2026-11-05, `main` at `0d43875`). Marks:

- **C-7**: the path is in the blueprint's C-7. C-7 gives almost no JSON, so the shapes were read from `apps/runtime/src`.
- **Log**: not in C-7. It exists in the code and the blueprint Log records it.
- **Mine**: the UI agent's assumption. Nothing promises it.

The Runtime tables were written by the UI agent. On the server side only the login routes, the gaps and the Studio's source functions have been checked against the code so far, not every row.

## Versions this assumes

| Change | Where | What the UI reads |
|---|---|---|
| Per-tab layouts | PR #16 | C-2 `periodUnion.tabs[].columns`, a union in `columns`, new `period_union` wording; C-3 `mapping.sources[].columns` and `headerRow`; `seriesFormulas` in the generation report |
| Lost model | PR #17 | C-2 `engine.modelUnavailable` |

Both are open. Build against `main` once they're merged.

## Runtime

### Login

Mark: C-7 for the routes, code for the details.

- Session cookie `daftar_session`: HttpOnly, SameSite=Lax, Secure over HTTPS, 14 days. The UI never sees the token.
- Writes with a body must be `application/json`, or they get 415. The one exception is the import upload.
- Startup: `GET /api/auth/status`. If `needsSetup`, show owner setup. Otherwise `GET /api/auth/me`; a 401 shows login.
- Any later 401 goes back to login and keeps the page the user was on.
- **Mine:** the UI is served from the same origin as the API. `app.ts` serves no static files today, so this needs adding.

### Calls

Values in JSON: money and numbers are numbers, `date` is `YYYY-MM-DD`, `datetime` is ISO, `multichoice` is an array, `link` is the target's UUID, and a phone comes back normalised. Forms show dd/mm/yyyy and convert before sending.

A record is `{_id, _name, _version, _createdAt, _updatedAt, ...visible fields, _errors?}`. `_errors` maps a field to an Excel error beside its value.

| Call | Request | Success | Errors beyond the common set | Mark |
|---|---|---|---|---|
| `GET /api/auth/status` | none, no session | `{needsSetup}` | | Log |
| `POST /api/auth/setup` | `{username, password}` | 201 `{username, role}`, sets cookie | 409 `{reason}` if already done | C-7 |
| `POST /api/auth/login` | `{username, password}` | 200 `{username, role}`, sets cookie | 401 `{reason}`: wrong login, or throttled | C-7 |
| `POST /api/auth/logout` | none | 204, clears cookie | | C-7 |
| `GET /api/auth/me` | none | `{username, role}` | | C-7 |
| `POST /api/auth/users` | `{username, password, role}`, owner only | 201 `{username, role}` | | Log |
| `GET /api/meta` | none | `{specVersion, app, user, permissions, entities, views, forms, dashboards, workflows, calculators}`, filtered by role. `computed` removed from fields, `cells` and `testCases` removed from calculators | | C-7 |
| `GET /api/e/{entity}` | `q`, `sort=a,-b`, `page`, `pageSize` (max 500), `totals=a,b`, `filter.<field>.<op>=v` | `{rows, total, page, pageSize, totals}` | | C-7; filter syntax Log |
| `POST /api/e/{entity}` | field values | 201 record | | C-7 |
| `GET /api/e/{entity}/{id}` | none | record | | C-7 |
| `PATCH /api/e/{entity}/{id}` | changed fields plus `_version` | record | 409 `{reason}` if stale | C-7; always sending `_version` is Mine |
| `DELETE /api/e/{entity}/{id}` | none | 204 | 409 `{reason}` if linked | C-7 |
| `GET /api/e/{entity}/{id}/history` | none | `{changes: [{id, at, actor, source, entity, recordId, op, changes: {field: [old, new]}, batchId?, revertOf?, revertedBy?}]}`, newest first, hidden values `"*"` | | C-7 |
| `POST /api/e/{entity}/{id}/transition` | `{action}` | 200 record | 409 `{reason}`: role, state or condition | C-7 |
| `POST /api/changes/{id}/revert` | none | 204 | 409 `{reason}` | C-7 |
| `POST /api/batches/{id}/undo` | none | 200 `{undone}` | 409 `{reason}` | C-7 |
| `POST /api/calc/{calculator}` | `{inputKey: value}` | 200 `{outputs: {key: value or {error}}}` | 400 `bad_query`, with no per-field message | C-7 |
| `GET /api/export.xlsx` | `locale=fr-DZ` or `ar-DZ` | the file | 503 `{reason}` | C-7; `locale` Log |
| `POST /api/import?name=` | raw file, sent as `application/octet-stream` (Mine) | 201 `{diffId, entities: {key: {added: [{key, values}], changed: [{key, id, version, fields}], missing: [{key, id}]}}, problems}` | 400 or 413 `{error, reason}`, 503 `{reason}` | C-7 |
| `POST /api/import/{diffId}/apply` | `{selected: {entity: {added: [keys], changed: [keys]}}}` | 200 `{batchId, added, changed, stale, problems}` | 400 `{entity, key, fields}` | C-7 |
| `GET /api/register` | none, owner or accountant | register JSON | | C-7 |
| `GET /api/notifications` | none | `{notifications: [{reminder, label, message, entity, recordId, name, date}]}` | | C-7 |
| `GET /api/audit.csv` | none, owner or accountant | CSV | | Log |

### Errors

Read from `errors.ts`, `app.ts` and the routes. C-7 lists only the first shape and the status numbers.

| Status | Body | What the UI does |
|---|---|---|
| 400 | `{fields: {key: {fr, ar}}}` | Shows each message under its field |
| 400 | `{error: "bad_query", what}` | Treats it as a bug, shows a generic message |
| 401 | `{reason: {fr, ar}}` or `{error: "unauthorized"}` | Login message, or back to login |
| 403 | `{reason}` or `{error: "forbidden"}` | Generic refusal |
| 404 | `{error: "not_found"}` | Not-found screen. An entity the role can't read also gives 404 |
| 409 | `{reason: {fr, ar}, ...}` | Shows `reason`. C-7 names stale writes and transitions; setup, delete and revert use it too |
| 415 | `{error: "json_required"}` | Treats it as a bug |
| 503 | `{reason}` | Shows `reason`, offers a retry |
| other 5xx | Nest's default body | Generic message (Mine) |

### Choices the UI makes on its own

These need no server change:

1. A view becomes query parameters in the browser, because the server has no view route. `relativeDays` is resolved in the browser against `app.timezone`.
2. The buttons offered on a record come from `/api/meta` workflows, using `from` and `roles`. A `condition` isn't checked in advance, so the server's 409 explains a refusal.
3. A KPI uses `?totals=field&pageSize=1` for a sum, and `total` for a count.
4. A link picker uses `GET /api/e/{target}?q=` and shows `_name`.
5. The language choice is stored in the browser and never sent.

### Gaps: waiting for the user's decision

Each one changes C-7, so none is agreed. Don't build on these until this section says so.

I can't build these without a server change. **Each one changes C-7, so the blueprint says to ask the user first.**

| # | Gap | Effect on the UI | Smallest fix |
|---|---|---|---|
| 1 | The login and setup pages can't get the app's name or default language, because `/api/meta` needs a session | They would show no firm name and guess the language | Add `app: {name, locales, defaultLocale}` to `GET /api/auth/status` |
| 2 | A record's link field is only a UUID, and `filter._id` is refused, so a list can't fetch its labels in one go | A list could show a UUID, or make one request per row | Return a label beside each link, or allow `filter._id.in` |
| 3 | Dashboard bar and line charts have no grouping route | The UI would page through every row in the browser (500 a page) | Add `GET /api/e/{entity}/aggregate?groupBy=&aggregate=&field=` |
| 4 | `/api/meta` has no `roles`, and there is no route to list or remove users or change a password | The owner can add staff but can't see or manage them, and the role list would be hard-coded | Add `roles` to meta for the owner, plus `GET` and `DELETE /api/auth/users` and a password route |
| 5 | A calculator's bad input returns `bad_query` with no message | The UI must validate on its own, and can't show the server's wording | Return 400 `{fields}` as forms do |

## Studio

The blueprint has no browser-facing Studio routes: C-7 is the Runtime, and C-4 is internal to the Compose network. Everything below is new, and the shapes come from C-1, C-2, C-4 and `project/`.

### The server

- `daftar studio` serves the API and the UI from one origin, bound to 127.0.0.1.
- **Open, for the user:** D-3 describes a TypeScript Studio API. The project code it would call (`project/`, the analyser) is all Python, so the proposal is that the Python worker serves these routes. The UI sees only HTTP either way.
- There's no login, because it's one operator on their own machine. Owners using the Studio themselves (v2) would need this revisited. `daftar studio --who NAME` fills `decision.by`.
- With no login, these protect the data from other websites open in the same browser:
  - Any `Host` other than `127.0.0.1:<port>` or `localhost:<port>` gets 403, as `daftar label` does.
  - There are no CORS headers.
  - Writes need `application/json`, and uploads need `application/octet-stream`. Anything else gets 415, so a plain cross-site form can't reach them.
- Projects live in `--projects DIR`, never in the repo. The server generates each `id`, and a client never supplies a path.

### Calls

| Call | Request | Response | Based on |
|---|---|---|---|
| `GET /api/projects` | none | `[{id, name, fileName, updatedAt, counts: {pending, accepted, edited, rejected}}]` | new |
| `POST /api/projects?name=&llm=on\|off` | raw file | 202 `{id, jobId}` | `project_init`, C-4 |
| `GET /api/jobs/{id}` | none | `{status, progress, result?, error?}` | C-4 |
| `GET /api/projects/{id}/snapshot` | none | C-1 without `cells`: `source`, sheet summaries, `definedNames`, `unsupported` | C-1 |
| `GET /api/projects/{id}/sheets/{index}?range=A1:Z200` | none | that sheet's `cells`, `merges`, `validations`, `conditionalFormats`, `hiddenRows`, `hiddenColumns`, `rtl`, `dimension` for the range | C-1 |
| `GET /api/projects/{id}/analysis` | none | C-2, with every finding's `decision` | C-2 |
| `PUT /api/projects/{id}/findings/{findingId}/decision` | `{status: accepted\|edited\|rejected\|pending, value?}` | the updated finding | `decide()` |
| `POST /api/projects/{id}/decisions/accept-high` | none | `{acceptedHigh, accepted, rejected, pending}` | `project_decide` |
| `POST /api/projects/{id}/reanalyze` | optional raw file | 202 `{jobId}`, whose result is `{applied, moved, conflicts}` | `project_reanalyze` |
| `GET /api/projects/{id}/conflicts` | none | `[{reason: gone\|changed, finding, now?}]`, where `now` is the new finding's id | `conflicts.json` |
| `POST /api/projects/{id}/generate` | none | 202 `{jobId}`, whose result is `{entities, rows, badValues, parityFailures, seriesFormulas, questions}`, the full lists, as in `generation-report.json` | `project_generate`, which runs a parity check and can be slow |
| `POST /api/projects/{id}/answers` | `{kind: periodYear, sheet, year}` or `{kind: confirmRetention, entity, months}` | updated `questions` | new; answering isn't built yet |
| `POST /api/projects/{id}/preview` | none | 202 `{jobId}`, whose result is `{url}` of a Runtime on the seed data, with an owner session open | D-9, R-14, new |

Changed from the UI agent's list: `generate` and `preview` are jobs, since both can outlast a request. `decide()` already handles `edited` and `pending`; only `project_decide` lacks them.

### Rules

- **Nothing is left behind by a rejected file (R-1).** `POST /api/projects` returns 202 before the file is read. If reading fails, the job ends in `error` and the project disappears from the list.
- **Jobs live in memory.** After a restart, a job id gives 404. The UI re-reads the project instead of waiting.
- **An `edited` decision needs `value`**, in that finding kind's proposal shape, or it gets 400 `{reason: {fr, ar}}`.
- **Sheet data comes by range**, because a workbook can hold 1,000,000 cells. A range over 20,000 cells gets 400.
- **Errors:** C-4's `{code, message: {fr, ar}}`, with `unreadable|protected|too_large|unsupported_format|invalid_spec`. Also 404 for an unknown project, job or finding, and 409 `{reason: {fr, ar}}` if a decision targets a finding that a rerun removed.

### What the review screen must show

These are warnings a person has to see. A report file alone isn't enough.

1. **`engine.modelUnavailable`:** a banner saying the model couldn't be reached, so names and tie-breaks are rules only, with a way to rerun.
2. **`seriesFormulas`:** one formula runs for a whole monthly series, so if one tab doesn't hold it, the column stops calculating for **every** month. Old values stay correct, but staff type that column by hand on new rows. Show the field, the tab and the reason before the operator moves on to the preview, so they can fix that tab and rerun. Each item is `{entity, field, sheet, reason}`, with `reason` one of:
   - `columnMissing`: the tab has no such column.
   - `notAFormula`: the tab has typed values there, or its formula wasn't accepted.
   - `differentFormula`: the tab's formula is different.
   - `parity`: the engine doesn't reproduce Excel's results on that tab.
3. **`parityFailures`, `badValues` and `questions`:** each listed with its sheet and cell or field. A `questions` entry blocks nothing, but a `periodYear` tab stays out of the app until it's answered.

The UI owns the French and Arabic wording for these codes. It shows `explanation.fr` or `.ar` as written, and wraps Latin text, ranges and formulas so they keep their order in Arabic.

### Open

- **How the preview's session opens.** The UI only needs a `url` that opens signed in. The likely way is for the server to create a throwaway owner on the preview database and set its cookie, since cookies on 127.0.0.1 aren't separated by port. If that fails it may need a Runtime route, which would change C-7.
- **Serving the Runtime UI.** `app.ts` serves no static files today. WP-10 adds that, and adds the UI to `apps/runtime/Dockerfile` and its `Dockerfile.dockerignore` allow-list.

**Not in the UI for v1:** `daftar bundle` stays a command.

## Working together

- The UI is built in its own git worktree from `main`, so neither session overwrites the other.
- Discuss on this file's PR. Never paste workbook data there, because the repo is public.
