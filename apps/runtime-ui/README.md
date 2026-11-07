# @daftar/runtime-ui

The screens a firm uses: React on [`packages/ui`](../../packages/ui/README.md), driven by the spec through `GET /api/meta`. The Runtime serves the build from its own origin, so the session cookie just works and nothing needs CORS. `docs/studio-api.md` is the contract with the server.

Being built under WP-10. So far: first start, login, list views, forms, a record's own page with its steps, history, undo and delete, a list of what's been deleted, and calculators. Still to come: the board, dashboards, reminders, sort and filter controls, a searching link picker, and the owner's page for accounts, the processing register and the audit download. Export and import belong to WP-13.

## Running it

```sh
pnpm -r build
DAFTAR_DATABASE_URL=postgres://… DAFTAR_SPEC_PATH=packages/spec/examples/repair-tracker.spec.json DAFTAR_SECRET=… node apps/runtime/dist/main.js
```

That serves the app on port 3000. To change the screens with a live reload, leave it running and use `pnpm --filter @daftar/runtime-ui dev`, which hands API calls to it.

## Rules

- **The spec is the app.** Labels, columns, forms and filters come from `/api/meta`. Only `src/words.ts` holds words of its own.
- **The server judges what's valid.** A form sends what it can read, and text it can't read as it is, so an error is in the server's words, in the right language. The UI never repeats a rule.
- **An edit sends only what changed, with `_version`.** It can't undo someone else's change, and a stale one is refused rather than overwriting.
- **The address is the state.** A reload, a shared link or signing in again lands on the same page, search and page number. Back within the app returns to the page a person left, and a shared link's back goes up to its list.
- **A refusal explains itself.** It shows the server's sentence. When a step's condition wasn't met, it also names the fields that condition reads, because the server's sentence can't. A field this person can't see is never named.
- **History says what happened in a person's words.** A link shows its target's name, a hidden field only says that it changed, and a creation or a deletion is one word.
- **A calculator's figure only stands beside the values it came from.** It goes as soon as one changes, and an answer that arrives after that is dropped. A cleared input is sent as blank, because one left out would take its default.
- **`src/fields.tsx` is the one place that knows a field type.** A new type belongs there, both how it shows and which input takes it.
- **State stays above what `useFrame()` switches on,** so turning a phone keeps what's been typed.

## Checks

```sh
pnpm --filter @daftar/runtime-ui test       # routes, a view's query, what a form holds and sends
pnpm --filter @daftar/runtime-ui test:e2e   # after pnpm -r build; needs DAFTAR_TEST_DATABASE_URL
```

`test:e2e` drives a real browser against a real Runtime for each spec it covers, on throwaway databases, plus a real preview. Nothing is mocked, and each screen gets the same measures and axe rules as the design system's reference screens.

Not tested: Safari, a real phone, and any native speaker's review of the wording.
