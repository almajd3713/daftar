/**
 * Starting up (docs/studio-api.md, Login), then the signed-in app. A later 401 returns here and shows login,
 * while the address keeps the person's page, so they land back on it.
 */
import type { Entity } from "@daftar/spec/types";
import {
  AppFrame,
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

import { call, canDo, problemOf, whenSignedOut, type Meta, type Status } from "./api.js";
import { MissingPage, PreviewEndedScreen, SetupScreen, SignInScreen, UnreachableScreen } from "./auth.js";
import { BoardPage } from "./board.js";
import { CalculatorPage } from "./calculator.js";
import { DeletedPage } from "./deleted.js";
import { EditRecordPage, NewRecordPage } from "./form.js";
import { ListPage } from "./list.js";
import { RecordPage } from "./record.js";
import { goBack, navigate, useRoute, type Route } from "./router.js";
import { boardWorkflow, isListView, usableCalculators, viewsOf } from "./views.js";
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

/** Somewhere the navigation leads. Its key says what kind, so an entity and a calculator can share a name. */
interface Place {
  key: string;
  label: string;
  route: Route;
}

const entityPlace = (key: string): string => `entity:${key}`;
const calculatorPlace = (key: string): string => `calculator:${key}`;

function SignedIn({ meta, status, onLocale, onSignOut }: { meta: Meta; status: Status; onLocale: (locale: Locale) => void; onSignOut: () => void }): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const route = useRoute();
  const entityOf = (key: string): Entity | undefined => meta.entities.find((entity) => entity.key === key);
  // One entry per entity, opening on its first view. Its other views are tabs on its page.
  const nav = meta.entities.flatMap((entity) => {
    const first = viewsOf(meta, entity.key)[0];
    return first ? [{ entity, view: first }] : [];
  });
  const groups: Place[][] = [
    nav.map(({ entity, view }) => ({ key: entityPlace(entity.key), label: say(entity.label), route: { name: "view", view: view.key, q: "", page: 1 } })),
    usableCalculators(meta).map((calculator) => ({ key: calculatorPlace(calculator.key), label: say(calculator.label), route: { name: "calculator", calculator: calculator.key } })),
  ];
  const places = groups.flat();
  const current = currentKey(route, meta.views) ?? places[0]?.key;
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
      nav={groups.filter((group) => group.length)}
      current={route.name === "more" ? "more" : current}
      onNavigate={(key) => {
        const target = key === "more" ? { name: "more" as const } : places.find((place) => place.key === key)?.route;
        if (target) navigate(target);
      }}
      user={<span><UserText>{meta.user.username}</UserText> · <TextLink onClick={onSignOut}>{t("signOut")}</TextLink></span>}
      language={language}
      hideNavOnPhone={route.name === "new" || route.name === "edit" || route.name === "record" || route.name === "deleted"}
    >
      <Screen route={route} meta={meta} entityOf={entityOf} firstView={nav[0]?.view} places={places} onLocale={onLocale} onSignOut={onSignOut} canSwitch={Boolean(language)} />
    </AppFrame>
  );
}

function currentKey(route: Route, views: Meta["views"]): string | undefined {
  if (route.name === "view") {
    const entity = views.find((view) => view.key === route.view)?.entity;
    return entity ? entityPlace(entity) : undefined;
  }
  if (route.name === "new" || route.name === "edit" || route.name === "record" || route.name === "deleted") return entityPlace(route.entity);
  if (route.name === "calculator") return calculatorPlace(route.calculator);
  return undefined;
}

interface ScreenProps {
  route: Route;
  meta: Meta;
  entityOf: (key: string) => Entity | undefined;
  firstView: Meta["views"][number] | undefined;
  places: Place[];
  onLocale: (locale: Locale) => void;
  onSignOut: () => void;
  canSwitch: boolean;
}

/** A view as its own kind of page. One a role can't use, such as a board whose state it can't see, isn't there for them. */
function ViewScreen({ meta, view, entity, q, page, state }: { meta: Meta; view: Meta["views"][number]; entity: Entity; q: string; page: number; state: string | undefined }): ReactNode {
  if (isListView(view)) return <ListPage key={view.key} meta={meta} view={view} entity={entity} q={q} page={page} />;
  const workflow = boardWorkflow(meta, view);
  return workflow ? <BoardPage key={view.key} meta={meta} view={view} workflow={workflow} entity={entity} state={state} /> : <MissingPage />;
}

function Screen({ route, meta, entityOf, firstView, places, onLocale, onSignOut, canSwitch }: ScreenProps): ReactNode {
  const { say } = useDaftar();
  const t = useWords();
  const calculators = usableCalculators(meta);
  if (route.name === "home") {
    if (!firstView) {
      const first = calculators[0];
      if (first) return <CalculatorPage key={first.key} calculator={first} />;
      return <Page title={say(meta.app.name)}><EmptyState title={t("nothingToShowTitle")}>{t("nothingToShowBody")}</EmptyState></Page>;
    }
    const entity = entityOf(firstView.entity);
    return entity ? <ViewScreen meta={meta} view={firstView} entity={entity} q="" page={1} state={undefined} /> : null;
  }
  if (route.name === "view") {
    const view = meta.views.find((item) => item.key === route.view);
    const entity = view ? entityOf(view.entity) : undefined;
    if (view && entity) return <ViewScreen meta={meta} view={view} entity={entity} q={route.q} page={route.page} state={route.state} />;
  }
  if (route.name === "new" || route.name === "edit" || route.name === "record") {
    const entity = entityOf(route.entity);
    const views = viewsOf(meta, route.entity);
    const list = views.find((view) => view.key === route.from) ?? views[0];
    const toList = (): void => goBack(list ? { name: "view", view: list.key, q: "", page: 1 } : { name: "home" });
    if (route.name === "record") {
      return entity ? <RecordPage key={`${route.entity}/${route.id}`} meta={meta} entity={entity} id={route.id} from={route.from} onBack={toList} /> : <MissingPage />;
    }
    const form = meta.forms.find((item) => item.entity === route.entity);
    if (entity && form) {
      if (route.name === "new") return <NewRecordPage entity={entity} form={form} onClose={toList} />;
      return <EditRecordPage key={route.id} entity={entity} form={form} id={route.id} onClose={() => goBack({ name: "record", entity: route.entity, id: route.id, from: route.from })} />;
    }
  }
  if (route.name === "deleted") {
    const entity = entityOf(route.entity);
    if (!entity || !canDo(meta, entity.key, "revert")) return <MissingPage />;
    const list = viewsOf(meta, entity.key)[0];
    return <DeletedPage key={entity.key} entity={entity} page={route.page} onBack={() => goBack(list ? { name: "view", view: list.key, q: "", page: 1 } : { name: "home" })} />;
  }
  if (route.name === "calculator") {
    const calculator = calculators.find((item) => item.key === route.calculator);
    if (calculator) return <CalculatorPage key={calculator.key} calculator={calculator} />;
  }
  if (route.name === "more") return <MorePage meta={meta} places={places} onLocale={onLocale} onSignOut={onSignOut} canSwitch={canSwitch} />;
  return <MissingPage />;
}

/** On a phone, what doesn't fit along the bottom: pages past the first four, the language, and signing out. */
function MorePage({ meta, places, onLocale, onSignOut, canSwitch }: Pick<ScreenProps, "meta" | "places" | "onLocale" | "onSignOut" | "canSwitch">): ReactNode {
  const { say, locale } = useDaftar();
  const { narrow } = useFrame();
  const t = useWords();
  const beyond = narrow ? places.slice(4) : [];
  return (
    <Page title={say(meta.app.name)}>
      <MenuList>
        {beyond.length ? (
          <>
            <MenuHeading>{t("otherPages")}</MenuHeading>
            {beyond.map((place) => (
              <MenuItem key={place.key} label={place.label} onClick={() => navigate(place.route)} />
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
