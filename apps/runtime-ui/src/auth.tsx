/** First start, signing in, and what a person sees when nothing can go further. */
import { AuthLayout, Button, EmptyState, ErrorSummary, FormBody, FormSection, LanguageSwitch, Notice, Page, PasswordField, TextField, useDaftar, type Locale } from "@daftar/ui";
import { useState, type ReactNode } from "react";

import { call, problemOf, type Problem, type Status } from "./api.js";
import { navigate } from "./router.js";
import { aboutField, useWords } from "./words.js";

interface AuthProps {
  status: Status;
  onLocale: (locale: Locale) => void;
}

function Language({ status, onLocale }: AuthProps): ReactNode {
  return status.app.locales.length > 1 ? <LanguageSwitch onSwitch={onLocale} /> : null;
}

/** A failure that isn't about one field: the server's own sentence where it has one. */
export function ProblemNotice({ problem, title }: { problem: Problem | undefined; title?: string }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  if (!problem || problem.kind === "fields" || problem.kind === "signedOut") return null;
  if (problem.kind === "reason") return <Notice tone="wrong" title={title ?? say(problem.reason)}>{title ? say(problem.reason) : null}</Notice>;
  if (problem.kind === "refused") return <Notice tone="wrong" title={t("refusedTitle")}>{t("refusedBody")}</Notice>;
  if (problem.kind === "missing") return <Notice tone="wrong" title={t("missingTitle")}>{t("missingBody")}</Notice>;
  return <Notice tone="wrong" title={t("failedTitle")}>{t("failedBody")}</Notice>;
}

/** An address with nothing behind it, or nothing this person may see. */
export function MissingPage(): ReactNode {
  const t = useWords();
  return (
    <Page title={t("missingTitle")}>
      <EmptyState title={t("missingTitle")} actions={<Button onClick={() => navigate({ name: "home" })}>{t("goHome")}</Button>}>{t("missingBody")}</EmptyState>
    </Page>
  );
}

function useSubmit(path: string, onDone: () => void): { busy: boolean; problem: Problem | undefined; submit: (body: unknown) => void } {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem>();
  const submit = (body: unknown): void => {
    setBusy(true);
    setProblem(undefined);
    call("POST", path, body).then(onDone, (error: unknown) => {
      setProblem(problemOf(error));
      setBusy(false);
    });
  };
  return { busy, problem, submit };
}

export function SetupScreen({ status, onLocale, onDone }: AuthProps & { onDone: () => void }): ReactNode {
  const { say, locale } = useDaftar();
  const t = useWords();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, problem, submit } = useSubmit("/api/auth/setup", onDone);
  const fields = problem?.kind === "fields" ? problem.fields : {};
  const errors = [
    ...(fields.username ? [{ fieldId: "username", message: aboutField(t("username"), say(fields.username), locale) }] : []),
    ...(fields.password ? [{ fieldId: "password", message: aboutField(t("password"), say(fields.password), locale) }] : []),
  ];
  return (
    <AuthLayout firm={say(status.app.name)} language={<Language status={status} onLocale={onLocale} />} title={t("setupTitle")} intro={t("setupIntro")}>
      <FormBody onSubmit={() => submit({ username, password })}>
        <ErrorSummary errors={errors} />
        <ProblemNotice problem={problem} />
        <FormSection>
          <TextField id="username" label={t("username")} required autoComplete="username" value={username} onChange={(event) => setUsername(event.currentTarget.value)} error={fields.username ? say(fields.username) : undefined} />
          <PasswordField id="password" label={t("password")} required autoComplete="new-password" description={t("passwordHint")} value={password} onChange={(event) => setPassword(event.currentTarget.value)} error={fields.password ? say(fields.password) : undefined} />
          <Button primary fullWidth type="submit" loading={busy}>{t("createAccount")}</Button>
        </FormSection>
      </FormBody>
    </AuthLayout>
  );
}

export function SignInScreen({ status, onLocale, onDone }: AuthProps & { onDone: () => void }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, problem, submit } = useSubmit("/api/auth/login", onDone);
  return (
    <AuthLayout firm={say(status.app.name)} language={<Language status={status} onLocale={onLocale} />} title={t("signInTitle")}>
      <FormBody onSubmit={() => submit({ username, password })}>
        <ProblemNotice problem={problem} />
        <FormSection>
          <TextField id="username" label={t("username")} required autoComplete="username" value={username} onChange={(event) => setUsername(event.currentTarget.value)} />
          <PasswordField id="password" label={t("password")} required autoComplete="current-password" value={password} onChange={(event) => setPassword(event.currentTarget.value)} />
          <Button primary fullWidth type="submit" loading={busy}>{t("signIn")}</Button>
        </FormSection>
      </FormBody>
    </AuthLayout>
  );
}

/** A preview's owner has a random password, so login would be a dead end. Only the Studio can sign in again. */
export function PreviewEndedScreen({ status, onLocale }: AuthProps): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  return <AuthLayout firm={say(status.app.name)} language={<Language status={status} onLocale={onLocale} />} title={t("previewTitle")} intro={t("previewBody")}>{null}</AuthLayout>;
}

/** Before the app's name or language is known, so it has only the device's language to go on. */
export function UnreachableScreen({ onRetry }: { onRetry: () => void }): ReactNode {
  const t = useWords();
  return (
    <AuthLayout title={t("failedTitle")} intro={t("failedBody")}>
      <div>
        <Button onClick={onRetry}>{t("retry")}</Button>
      </div>
    </AuthLayout>
  );
}
