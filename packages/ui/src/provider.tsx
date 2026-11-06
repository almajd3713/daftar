import "dayjs/locale/ar-dz";
import "dayjs/locale/fr";

import { DirectionProvider, MantineProvider, useDirection, type MantineColorScheme } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { createContext, use, useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";

import { dirOf, langOf, pick, type Lang, type Label, type Locale } from "./format.js";
import { uiText } from "./messages.js";
import { cssVariablesResolver, theme } from "./theme.js";
import { narrowBelowPx } from "./tokens.js";

interface DaftarContext {
  locale: Locale;
  lang: Lang;
  dir: "rtl" | "ltr";
  /** A spec label or a server message, in the current language. */
  say: (label: Label) => string;
  /** One of the components' own words. */
  ui: (key: keyof typeof uiText) => string;
}

const Context = createContext<DaftarContext | null>(null);

export function useDaftar(): DaftarContext {
  const value = use(Context);
  if (!value) throw new Error("Wrap the app in <DaftarProvider>.");
  return value;
}

/** Keeps Mantine's direction in step with the language, so a switch flips everything at once. */
function DirectionSync({ dir }: { dir: "rtl" | "ltr" }): null {
  const { setDirection } = useDirection();
  useLayoutEffect(() => {
    setDirection(dir);
  }, [dir, setDirection]);
  return null;
}

export interface DaftarProviderProps {
  locale: Locale;
  /** Leave it out to follow the device. */
  colorScheme?: Exclude<MantineColorScheme, "auto"> | undefined;
  children: ReactNode;
}

/**
 * Language, direction, theme and date settings for everything inside. R-21: the week starts on Saturday,
 * and the weekend is Friday and Saturday.
 */
export function DaftarProvider({ locale, colorScheme, children }: DaftarProviderProps): ReactNode {
  const dir = dirOf(locale);
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.lang = locale;
    root.dir = dir;
  }, [locale, dir]);
  const context = useMemo<DaftarContext>(() => ({ locale, lang: langOf(locale), dir, say: (label) => pick(label, locale), ui: (key) => pick(uiText[key], locale) }), [locale, dir]);
  const dates = useMemo(() => ({ locale: locale === "ar-DZ" ? "ar-dz" : "fr", firstDayOfWeek: 6 as const, weekendDays: [5, 6] as (0 | 1 | 2 | 3 | 4 | 5 | 6)[], consistentWeeks: true }), [locale]);
  return (
    <DirectionProvider initialDirection={dir} detectDirection={false}>
      <DirectionSync dir={dir} />
      <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto" {...(colorScheme ? { forceColorScheme: colorScheme } : {})}>
        <DatesProvider settings={dates}>
          <Context value={context}>{children}</Context>
        </DatesProvider>
      </MantineProvider>
    </DirectionProvider>
  );
}

const STORAGE_KEY = "daftar.locale";

/**
 * The person's language, kept on this device. Storage can be blocked, so a failure only loses the memory.
 *
 * `fallback` is the app's `defaultLocale`, which only arrives once `/api/auth/status` answers, so it can change:
 * until the person chooses, the language follows it. `allowed` is the app's `locales`: a language stored for
 * another app on this address doesn't apply to one that doesn't offer it.
 */
export function useStoredLocale(fallback: Locale, allowed?: readonly Locale[]): [Locale, (locale: Locale) => void] {
  const [stored, setStored] = useState<Locale | null>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved === "fr-DZ" || saved === "ar-DZ" ? saved : null;
    } catch {
      return null;
    }
  });
  const setLocale = useCallback((next: Locale) => {
    setStored(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private mode, or storage turned off.
    }
  }, []);
  return [stored && (!allowed || allowed.includes(stored)) ? stored : fallback, setLocale];
}

const FrameContext = createContext<{ narrow: boolean }>({ narrow: false });

/** Is the enclosing frame phone-sized? Its own width decides, so the Studio's embedded preview works too. */
export function useFrame(): { narrow: boolean } {
  return use(FrameContext);
}

/** Measures itself, and tells the components inside which layout they're in. Null until it has measured. */
export function useFrameWidth(ref: RefObject<HTMLElement | null>): boolean | null {
  const [narrow, setNarrow] = useState<boolean | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = (): void => setNarrow(element.offsetWidth < narrowBelowPx);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return narrow;
}

export interface FrameProps {
  children: ReactNode;
  className?: string | undefined;
}

/** The root of any screen, or of a preview of one. Sets `data-layout`, which the narrow tokens hang from. */
export function Frame({ children, className }: FrameProps): ReactNode {
  const ref = useRef<HTMLDivElement>(null);
  const narrow = useFrameWidth(ref);
  const value = useMemo(() => ({ narrow: narrow ?? false }), [narrow]);
  // Nothing inside until the width is known. Mounting a screen for the wrong layout, then again for the right one,
  // would send every request it makes on mounting twice. A measure happens before the first paint, so nobody sees this.
  return (
    <div ref={ref} className={className} data-layout={narrow === null ? undefined : narrow ? "narrow" : "wide"}>
      {narrow === null ? null : <FrameContext value={value}>{children}</FrameContext>}
    </div>
  );
}
