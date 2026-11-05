# Daftar UI and server contract

**Status:** the Runtime part is agreed and on `main`. The Studio part is on `main` too, including the preview. It's still open to change: the UI agent hasn't commented yet. The UI and the server each change this file before changing code that depends on it.

It starts from what the UI agent said it will assume (2026-11-05, `main` at `0d43875`). Marks:

- **C-7**: the path is in the blueprint's C-7. C-7 gives almost no JSON, so the shapes were read from `apps/runtime/src`.
- **Log**: not in C-7. It exists in the code and the blueprint Log records it.
- **Mine**: the UI agent's assumption. Nothing promises it.

The Runtime tables were written by the UI agent. On the server side only the login routes, the gaps and the Studio's source functions have been checked against the code so far, not every row.

## Versions this assumes

| Change | Where | What the UI reads |
|---|---|---|
| Per-tab layouts | PR #16, merged | C-2 `periodUnion.tabs[].columns`, a union in `columns`, new `period_union` wording; C-3 `mapping.sources[].columns` and `headerRow`; `seriesFormulas` in the generation report |
| Lost model | PR #17, merged | C-2 `engine.modelUnavailable` |
| Runtime additions | PR #20, merged | Everything under "Runtime additions" below |
| Structured references | PR #22, merged | C-1 `cells[].fStructured`: what the file said, when `f` holds the expanded A1 form. Show it beside `f` if useful |
| Group labels | PR #21, merged | A new C-2 finding kind, `groupColumn`: `proposal {table, groups: [{row, label}]}`, with one evidence range per heading row |

Everything is on `main`, including the preview (PR #24).

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

### Runtime additions

The user approved these on 2026-11-05, and C-7 records them. They're on `main`.

**Before sign-in.** `GET /api/auth/status` also returns `app: {name, locales, defaultLocale}`.

**Link labels.** A record carries `_labels: {field: name}` beside its link ids, wherever a record is returned. A label is left out if the user may not read that row of the target, so the UI needs a fallback for a link with no label.

**Charts.** `GET /api/e/{entity}/aggregate?groupBy=&aggregate=&field=`, plus the list's `q` and `filter.<field>.<op>`:

- `aggregate` is `count`, `sum`, `avg`, `min` or `max`. Every one but `count` needs a numeric `field`.
- Returns `{groups: [{key, value, label?}], truncated}`, sorted by `key`, at most 500 groups. `label` is set when `groupBy` is a link the user may read. `key` is null for rows with no value.
- `groupBy` and `field` get 400 `bad_query` if hidden from the role or if `groupBy` is `multichoice`. An entity the role can't read gets 404. Row scope applies.
- There are no date buckets, since no C-3 widget asks for them. A line chart grouped by a date gets one point per distinct date.
- Like list totals, a sum skips a row whose formula gave an Excel error.

**Accounts.** All owner only, except changing your own password:

| Call | Request | Success | Errors |
|---|---|---|---|
| `GET /api/auth/users` | none | `{users: [{id, username, role, createdAt}]}` | 403 |
| `DELETE /api/auth/users/{id}` | none | 204. Their history and records stay | 403, 404, 409 `{reason}` for your own account |
| `POST /api/auth/users/{id}/password` | `{password}` | 204, and that person is signed out | 400 `{fields}`, 403, 404, 409 `{reason}` for your own account |
| `POST /api/auth/password` | `{currentPassword, newPassword}`, for yourself | 204, and your other devices are signed out | 400 `{fields}`, on `currentPassword` if wrong or throttled |

`GET /api/meta` includes `roles: [{key, label}]` for the owner only. A person's role can't be changed.

**Calculators.** A bad input gets 400 `{fields: {key: {fr, ar}}}`, as forms do, listing every bad input at once. This replaces `bad_query` in the table above.

## Studio

The blueprint has no browser-facing Studio routes: C-7 is the Runtime, and C-4 is internal to the Compose network. Everything below is new, and the shapes come from C-1, C-2, C-4 and `project/`.

### The server

- `daftar studio --projects DIR --who NAME` serves the API, and later the UI, from one origin, bound to 127.0.0.1, on port 8791 by default.
- The Python worker serves these routes. The user decided this on 2026-11-05, in place of D-3's TypeScript Studio API, because the code it calls (`project/`, the analyser) is all Python.
- There's no login, because it's one operator on their own machine. Owners using the Studio themselves (v2) would need this revisited. `daftar studio --who NAME` fills `decision.by`.
- With no login, these protect the data from other websites open in the same browser:
  - Any `Host` other than `127.0.0.1:<port>` or `localhost:<port>` gets 403, as `daftar label` does.
  - There are no CORS headers.
  - An `Origin` that isn't this server gets 403.
  - Writes need `application/json`, and uploads need `application/octet-stream`. Anything else gets 415, so a plain cross-site form can't reach them. That includes a POST with no body: send `{}`.
- Projects live in `--projects DIR`, never in the repo. The server generates each `id`, and a client never supplies a path.

### Calls

| Call | Request | Response | Based on |
|---|---|---|---|
| `GET /api/projects` | none | `[{id, name, fileName, updatedAt, counts: {pending, accepted, edited, rejected}}]` | new |
| `POST /api/projects?fileName=&name=&llm=on\|off` | raw file. `fileName` is required, as its extension gives the format | 202 `{id, jobId}` | `project_init`, C-4 |
| `GET /api/jobs/{id}` | none | `{status, progress, result?, error?}` | C-4 |
| `GET /api/projects/{id}/snapshot` | none | C-1 without `cells`: `source`, sheet summaries, `definedNames`, `unsupported` | C-1 |
| `GET /api/projects/{id}/sheets/{index}?range=A1:Z200` | none | that sheet's `cells`, `merges`, `validations`, `conditionalFormats`, `hiddenRows`, `hiddenColumns`, `rtl`, `dimension` for the range | C-1 |
| `GET /api/projects/{id}/analysis` | none | C-2, with every finding's `decision` | C-2 |
| `PUT /api/projects/{id}/findings/{findingId}/decision` | `{status: accepted\|edited\|rejected\|pending, value?}` | the updated finding | `decide()` |
| `POST /api/projects/{id}/decisions/accept-high` | `{}` as JSON | `{acceptedHigh, accepted, rejected, pending}` | `project_decide` |
| `POST /api/projects/{id}/reanalyze?fileName=&llm=` | a raw file with `fileName`, or `{}` as JSON to rerun the same workbook | 202 `{jobId}`, whose result is `{applied, moved, conflicts}` | `project_reanalyze` |
| `GET /api/projects/{id}/conflicts` | none | `[{reason: gone\|changed, finding, now?}]`, where `now` is the new finding's id | `conflicts.json` |
| `POST /api/projects/{id}/generate` | `{}` as JSON | 202 `{jobId}`, whose result is `{entities, rows, badValues, parityFailures, seriesFormulas, questions}`, the full lists, as in `generation-report.json` | `project_generate`, which runs a parity check and can be slow |
| `POST /api/projects/{id}/answers` | `{kind: periodYear, sheet, year}` or `{kind: confirmRetention, entity, months}` | `{questions}`, those still open. Generate again to apply the answers | `answers.json` |
| `POST /api/projects/{id}/preview` | `{}` as JSON | 202 `{jobId}`, whose result is `{url}`. 409 if not generated yet, 503 if previews aren't set up on this machine | D-9, R-14 |
| `GET /api/projects/{id}/preview/open` | none, opened by the browser | 303 to the running preview, with its session cookie set. 404 if none is running | new |
| `DELETE /api/projects/{id}/preview` | none | 204. Starting a preview again replaces the old one | new |

Changed from the UI agent's list: `generate` and `preview` are jobs, since both can outlast a request. `decide()` already handles `edited` and `pending`; only `project_decide` lacks them.

### Rules

- **Nothing is left behind by a rejected file (R-1).** `POST /api/projects` returns 202 before the file is read. If reading fails, the job ends with `status: failed` and `error`. A project joins the list only when its first analysis finishes, and its `id` gives 404 until then.
- **Nothing changes during a job.** A decision, accept-high, answer, generate or rerun gets 409 `{reason}` while a job runs on that project. Reads still work.
- **Jobs live in memory.** After a restart, a job id gives 404. The UI re-reads the project instead of waiting.
- **An `edited` decision needs `value`**, holding the proposal's fields to change. The result must fit that finding kind's shape, or it gets 400 `{reason: {fr, ar}}`.
- **Sheet data comes by range**, because a workbook can hold 1,000,000 cells. A range over 20,000 cells gets 400. `cells` and `merges` follow the range; `validations`, `conditionalFormats` and the hidden lists are the whole sheet's. The snapshot's sheet summaries give `cellCount`.
- **Errors:** C-4's `{code, message: {fr, ar}}`, with `unreadable|protected|too_large|unsupported_format|invalid_spec`, as a job's `error` or directly: an upload with no file gets 422, one over the limit 413. Also 404 `{error: "not_found"}` for an unknown project, job or finding, and 409 `{reason: {fr, ar}}` if a decision targets a finding that a rerun removed.

### What the review screen must show

These are warnings a person has to see. A report file alone isn't enough.

1. **`engine.modelUnavailable`:** a banner saying the model couldn't be reached, so names and tie-breaks are rules only, with a way to rerun.
2. **`seriesFormulas`:** one formula runs for a whole monthly series, so if one tab doesn't hold it, the column stops calculating for **every** month. Old values stay correct, but staff type that column by hand on new rows. Show the field, the tab and the reason before the operator moves on to the preview, so they can fix that tab and rerun. Each item is `{entity, field, sheet, reason}`, with `reason` one of:
   - `columnMissing`: the tab has no such column.
   - `notAFormula`: the tab has typed values there, or its formula wasn't accepted.
   - `differentFormula`: the tab's formula is different.
   - `parity`: the engine doesn't reproduce Excel's results on that tab.
3. **`parityFailures`, `badValues` and `questions`:** each listed with its sheet and cell or field. A `questions` entry blocks nothing, but a `periodYear` tab stays out of the app until it's answered and generated again.

The UI owns the French and Arabic wording for these codes. It shows `explanation.fr` or `.ar` as written, and wraps Latin text, ranges and formulas so they keep their order in Arabic.

### Open

- **The preview's page.** The Runtime serves only its API until WP-10 adds the UI, so `url` leads to a 404 until then. Open `url` as a page, not with `fetch`. Export and re-import answer 503 in a preview, because it has no worker attached.
- **Serving the Runtime UI.** `app.ts` serves no static files today. WP-10 adds that, and adds the UI to `apps/runtime/Dockerfile` and its `Dockerfile.dockerignore` allow-list.

**Not in the UI for v1:** `daftar bundle` stays a command.

## Working together

- The UI is built in its own git worktree from `main`, so neither session overwrites the other.
- Discuss on this file's PR. Never paste workbook data there, because the repo is public.
