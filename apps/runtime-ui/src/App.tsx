/**
 * Starting up (docs/studio-api.md, Login), then the signed-in app. A later 401 returns here and shows login,
 * while the address keeps the person's page, so they land back on it.
 */
import type { Entity, ViewList } from "@daftar/spec/types";
import {
  AppFrame,
  Button,
  DaftarProvider,
  EmptyState,
  LanguageSwitch,
  MenuHeading,
  MenuItem,
  MenuList,
  Page,
  TextLink,
  useDaftar,
  useFrame,
  UserText,
  useStoredLocale,
  type Locale,
} from "@daftar/ui";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { call, problemOf, whenSignedOut, type Meta, type Status } from "./api.js";
import { PreviewEndedScreen, SetupScreen, SignInScreen, UnreachableScreen } from "./auth.js";
import { EditRecordPage, NewRecordPage } from "./form.js";
import { ListPage } from "./list.js";
import { navigate, useRoute, type Route } from "./router.js";
import { isListView } from "./views.js";
import { useWords } from "./words.js";

type Boot =
  | { phase: "starting"; status?: undefined }
  | { phase: "unreachable"; status?: undefined }
  | { phase: "setup" | "signIn" | "previewEnded"; status: Status }
  | { phase: "ready"; status: Status; meta: Meta };

const deviceLocale = (): Locale => (navigator.language.toLowerCase().startsWith("ar") ? "ar-DZ" : "fr-DZ");

export function App(): ReactNode {
  const [boot, setBoot] = useState<Boot>({ phase: "starting" });
  const [locale, setLocale] = useStoredLocale(boot.status?.app.defaultLocale ?? deviceLocale(), boot.status?.app.locales);

  // A preview arrives on a new port each time, so the Studio says which language to use in the address.
  useLayoutEffect(() => {
    const params = new URLSearchParams(location.search);
    const lang = params.get("lang");
    if (lang !== "fr" && lang !== "ar") return;
    setLocale(lang === "ar" ? "ar-DZ" : "fr-DZ");
    params.delete("lang");
    const rest = params.toString();
    history.replaceState(null, "", `${location.pathname}${rest ? `?${rest}` : ""}`);
  }, [setLocale]);

  const start = useCallback(async (): Promise<void> => {
    let status: Status;
    try {
      status = await call<Status>("GET", "/api/auth/status");
    } catch {
      setBoot({ phase: "unreachable" });
      return;
    }
    if (status.needsSetup) {
      setBoot({ phase: "setup", status });
      return;
    }
    try {
      setBoot({ phase: "ready", status, meta: await call<Meta>("GET", "/api/meta") });
    } catch (error) {
      if (problemOf(error).kind === "signedOut") setBoot({ phase: status.preview ? "previewEnded" : "signIn", status });
      else setBoot({ phase: "unreachable" });
    }
  }, []);

  useEffect(() => {
    void start();
  }, [start]);

  useEffect(() => {
    whenSignedOut(() => setBoot((current) => (current.status ? { phase: current.status.preview ? "previewEnded" : "signIn", status: current.status } : current)));
  }, []);

  const signOut = useCallback((): void => {
    void call("POST", "/api/auth/logout").finally(() => void start());
  }, [start]);

  const again = (): void => void start();
  const shared = boot.status ? { status: boot.status, onLocale: setLocale } : undefined;
  return (
    <DaftarProvider locale={locale}>
      {/* Nothing until the app's language is known, or the page would flip direction as it arrives. */}
      {boot.phase === "unreachable" ? <UnreachableScreen onRetry={again} /> : null}
      {boot.phase === "setup" && shared ? <SetupScreen {...shared} onDone={again} /> : null}
      {boot.phase === "signIn" && shared ? <SignInScreen {...shared} onDone={again} /> : null}
      {boot.phase === "previewEnded" && shared ? <PreviewEndedScreen {...shared} /> : null}
      {boot.phase === "ready" ? <SignedIn meta={boot.meta} status={boot.status} onLocale={setLocale} onSignOut={signOut} /> : null}
    </DaftarProvider>
  );
}

function SignedIn({ meta, status, onLocale, onSignOut }: { meta: Meta; status: Status; onLocale: (locale: Locale) => void; onSignOut: () => void }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const route = useRoute();
  const lists = meta.views.filter(isListView);
  const entityOf = (key: string): Entity | undefined => meta.entities.find((entity) => entity.key === key);
  // One entry per entity. Its other views are tabs on its page.
  const nav = meta.entities.flatMap((entity) => {
    const first = lists.find((view) => view.entity === entity.key);
    return first ? [{ entity, view: first }] : [];
  });
  const current = currentKey(route, lists);
  const language = status.app.locales.length > 1 ? <LanguageSwitch onSwitch={onLocale} /> : undefined;

  // A new page moves focus to it, as a real page load would, so a screen reader and the keyboard start there.
  const firstPage = useRef(true);
  const place = JSON.stringify(route);
  useEffect(() => {
    if (firstPage.current) {
      firstPage.current = false;
      return;
    }
    document.getElementById("main")?.focus();
    window.scrollTo(0, 0);
  }, [place]);

  useEffect(() => {
    document.title = say(meta.app.name);
  }, [meta.app.name, say]);

  return (
    <AppFrame
      firm={say(meta.app.name)}
      nav={[nav.map(({ entity }) => ({ key: entity.key, label: say(entity.label) }))]}
      current={route.name === "more" ? "more" : current}
      onNavigate={(key) => {
        if (key === "more") navigate({ name: "more" });
        else {
          const target = nav.find(({ entity }) => entity.key === key);
          if (target) navigate({ name: "view", view: target.view.key, q: "", page: 1 });
        }
      }}
      user={<span><UserText>{meta.user.username}</UserText> · <TextLink onClick={onSignOut}>{t("signOut")}</TextLink></span>}
      language={language}
      hideNavOnPhone={route.name === "new" || route.name === "edit"}
    >
      <Screen route={route} meta={meta} entityOf={entityOf} firstView={nav[0]?.view} nav={nav} onLocale={onLocale} onSignOut={onSignOut} canSwitch={Boolean(language)} />
    </AppFrame>
  );
}

function currentKey(route: Route, lists: ViewList[]): string | undefined {
  if (route.name === "view") return lists.find((view) => view.key === route.view)?.entity;
  if (route.name === "new" || route.name === "edit") return route.entity;
  return lists[0]?.entity;
}

interface ScreenProps {
  route: Route;
  meta: Meta;
  entityOf: (key: string) => Entity | undefined;
  firstView: ViewList | undefined;
  nav: { entity: Entity; view: ViewList }[];
  onLocale: (locale: Locale) => void;
  onSignOut: () => void;
  canSwitch: boolean;
}

function Screen({ route, meta, entityOf, firstView, nav, onLocale, onSignOut, canSwitch }: ScreenProps): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  if (route.name === "home") {
    if (!firstView) {
      return <Page title={say(meta.app.name)}><EmptyState title={t("nothingToShowTitle")}>{t("nothingToShowBody")}</EmptyState></Page>;
    }
    const entity = entityOf(firstView.entity);
    return entity ? <ListPage meta={meta} view={firstView} entity={entity} q="" page={1} /> : null;
  }
  if (route.name === "view") {
    const view = meta.views.filter(isListView).find((item) => item.key === route.view);
    const entity = view ? entityOf(view.entity) : undefined;
    if (view && entity) return <ListPage key={view.key} meta={meta} view={view} entity={entity} q={route.q} page={route.page} />;
  }
  if (route.name === "new" || route.name === "edit") {
    const entity = entityOf(route.entity);
    const form = meta.forms.find((item) => item.entity === route.entity);
    const back = meta.views.filter(isListView).find((view) => view.key === route.from) ?? meta.views.filter(isListView).find((view) => view.entity === route.entity);
    const close = (): void => navigate(back ? { name: "view", view: back.key, q: "", page: 1 } : { name: "home" });
    if (entity && form) {
      return route.name === "new" ? <NewRecordPage entity={entity} form={form} onClose={close} /> : <EditRecordPage key={route.id} entity={entity} form={form} id={route.id} onClose={close} />;
    }
  }
  if (route.name === "more") return <MorePage meta={meta} nav={nav} onLocale={onLocale} onSignOut={onSignOut} canSwitch={canSwitch} />;
  return (
    <Page title={t("missingTitle")}>
      <EmptyState title={t("missingTitle")} actions={<Button onClick={() => navigate({ name: "home" })}>{t("goHome")}</Button>}>{t("missingBody")}</EmptyState>
    </Page>
  );
}

/** On a phone, what doesn't fit along the bottom: pages past the first four, the language, and signing out. */
function MorePage({ meta, nav, onLocale, onSignOut, canSwitch }: Pick<ScreenProps, "meta" | "nav" | "onLocale" | "onSignOut" | "canSwitch">): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const beyond = narrow ? nav.slice(4) : [];
  return (
    <Page title={say(meta.app.name)}>
      <MenuList>
        {beyond.length ? (
          <>
            <MenuHeading>{t("otherPages")}</MenuHeading>
            {beyond.map(({ entity, view }) => (
              <MenuItem key={entity.key} label={say(entity.label)} onClick={() => navigate({ name: "view", view: view.key, q: "", page: 1 })} />
            ))}
          </>
        ) : null}
        <MenuHeading>{t("account")}</MenuHeading>
        <MenuItem label={<UserText>{meta.user.username}</UserText>} />
        {canSwitch ? <MenuItem label={t("language")} value={locale === "ar-DZ" ? "العربية" : "Français"} onClick={() => onLocale(locale === "ar-DZ" ? "fr-DZ" : "ar-DZ")} /> : null}
        <MenuItem label={t("signOut")} onClick={onSignOut} />
      </MenuList>
    </Page>
  );
}
