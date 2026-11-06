/** The shell: a text-only index down the side on a PC, visible navigation along the bottom on a phone. */
import { Button as MantineButton, type ButtonProps as MantineButtonProps } from "@mantine/core";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { Locale } from "./format.js";
import { Frame, useDaftar, useFrame } from "./provider.js";
import classes from "./layout.module.css";

export interface ButtonProps extends MantineButtonProps, Omit<ButtonHTMLAttributes<HTMLButtonElement>, keyof MantineButtonProps | "style" | "color"> {
  /** At most one primary per page. */
  primary?: boolean | undefined;
}

export function Button({ primary, type = "button", ...props }: ButtonProps): ReactNode {
  return <MantineButton type={type} variant={primary ? "filled" : "default"} {...props} />;
}

export const PlusIcon = (): ReactNode => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <path d="M8 3v10M3 8h10" />
  </svg>
);

export const WarningIcon = (): ReactNode => (
  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <circle cx="7" cy="7" r="5.8" />
    <path d="M7 4v3.6M7 10.1v.1" />
  </svg>
);

export const SearchIcon = (): ReactNode => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5 14 14" />
  </svg>
);

function BackIcon(): ReactNode {
  const { dir } = useDaftar();
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={dir === "rtl" ? "M8 4l6 6-6 6" : "M12 4l-6 6 6 6"} />
    </svg>
  );
}

export interface NavItem {
  key: string;
  label: ReactNode;
}

export interface AppFrameProps {
  firm: ReactNode;
  /** Groups of pages. Lists first, then what's built on them. A phone shows the first four, then More. */
  nav: NavItem[][];
  current?: string | undefined;
  onNavigate?: ((key: string) => void) | undefined;
  /** The key `onNavigate` gets for More, whose page lists the rest. */
  moreKey?: string | undefined;
  user?: ReactNode;
  language?: ReactNode;
  /** A detail page swaps the bar for back and its own actions. */
  hideNavOnPhone?: boolean | undefined;
  children: ReactNode;
}

function NavButton({ item, current, onNavigate, className }: { item: NavItem; current: boolean; onNavigate?: ((key: string) => void) | undefined; className: string }): ReactNode {
  return (
    <button type="button" className={className} aria-current={current ? "page" : undefined} onClick={() => onNavigate?.(item.key)}>
      {item.label}
    </button>
  );
}

function Shell({ firm, nav, current, onNavigate, moreKey = "more", user, language, hideNavOnPhone, children }: AppFrameProps): ReactNode {
  const { narrow } = useFrame();
  const { ui } = useDaftar();
  const flat = nav.flat();
  const onBar = flat.slice(0, 4);
  const moreIsCurrent = current === moreKey || (current !== undefined && flat.slice(4).some((item) => item.key === current));
  // One tree for both layouts, with `children` in the same place. Otherwise turning a phone or resizing a window
  // across the breakpoint would rebuild the screen, and throw away whatever someone had typed into a form.
  return (
    <div className={narrow ? classes.narrow : classes.wide}>
      {narrow ? null : (
        <aside className={classes.side}>
          <strong className={classes.firm}>{firm}</strong>
          <nav className={classes.index} aria-label={ui("menu")}>
            {nav.map((group, index) => (
              <ul key={index}>
                {group.map((item) => (
                  <li key={item.key}>
                    <NavButton item={item} current={item.key === current} onNavigate={onNavigate} className={classes.indexItem ?? ""} />
                  </li>
                ))}
              </ul>
            ))}
          </nav>
          <div className={classes.sideFoot}>
            {user}
            {language}
          </div>
        </aside>
      )}
      {children}
      {narrow && !hideNavOnPhone && flat.length > 0 ? (
        <nav className={classes.bar} aria-label={ui("menu")}>
          <ul>
            {onBar.map((item) => (
              <li key={item.key}>
                <NavButton item={item} current={item.key === current} onNavigate={onNavigate} className={classes.barItem ?? ""} />
              </li>
            ))}
            <li>
              <NavButton item={{ key: moreKey, label: ui("more") }} current={moreIsCurrent} onNavigate={onNavigate} className={classes.barItem ?? ""} />
            </li>
          </ul>
        </nav>
      ) : null}
    </div>
  );
}

/** The whole app's frame. Put one `Page` inside. */
export function AppFrame(props: AppFrameProps): ReactNode {
  const { ui } = useDaftar();
  return (
    <Frame className={classes.frame}>
      <a className={classes.skip} href="#main">
        {ui("skipToContent")}
      </a>
      <Shell {...props} />
    </Frame>
  );
}

/** A frame with no navigation, for the Studio's review screen. */
export function BareFrame({ children }: { children: ReactNode }): ReactNode {
  return <Frame className={`${classes.frame} ${classes.bare}`}>{children}</Frame>;
}

/** Offers the other language in that language, so someone who can't read this screen can still find theirs. */
export function LanguageSwitch({ onSwitch }: { onSwitch: (locale: Locale) => void }): ReactNode {
  const { locale } = useDaftar();
  const other: Locale = locale === "ar-DZ" ? "fr-DZ" : "ar-DZ";
  return (
    <button type="button" className={classes.language} lang={other} onClick={() => onSwitch(other)}>
      {other === "ar-DZ" ? "العربية" : "Français"}
    </button>
  );
}

export interface AuthLayoutProps {
  firm?: ReactNode;
  language?: ReactNode;
  title: ReactNode;
  intro?: ReactNode;
  children: ReactNode;
}

/** First start and login: the firm's name, one short form, and the language switch always in reach. */
export function AuthLayout({ firm, language, title, intro, children }: AuthLayoutProps): ReactNode {
  return (
    <Frame className={classes.frame}>
      <main id="main" className={classes.auth}>
        <div className={classes.authTop}>
          <strong className={classes.firm}>{firm}</strong>
          {language}
        </div>
        <div className={classes.authBody}>
          <div>
            <h1 className={classes.title}>{title}</h1>
            {intro ? <p className={classes.authIntro}>{intro}</p> : null}
          </div>
          {children}
        </div>
      </main>
    </Frame>
  );
}

export interface PageProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  /** Sits beside the title on a PC. On a phone, pass the same buttons as `foot`. */
  actions?: ReactNode;
  /** Pinned above the navigation on a phone: the page's action, and a total if it has one. */
  foot?: ReactNode;
  /** Closes the foot with the double rule, because it holds a total. */
  closing?: boolean | undefined;
  onBack?: (() => void) | undefined;
  children: ReactNode;
}

/** One screen's heading, body and foot. The body scrolls on a phone, and the foot stays in reach. */
export function Page({ title, subtitle, actions, foot, closing, onBack, children }: PageProps): ReactNode {
  const { narrow } = useFrame();
  const { ui } = useDaftar();
  // As in the shell, `children` keeps its place in both layouts, so a field keeps its focus when a phone turns.
  return (
    <>
      {narrow && title ? (
        <header className={onBack ? `${classes.top} ${classes.topBack}` : classes.top}>
          {onBack ? (
            <button type="button" className={classes.backButton} aria-label={ui("back")} onClick={onBack}>
              <BackIcon />
            </button>
          ) : null}
          <h1 className={classes.title}>{title}</h1>
        </header>
      ) : null}
      <main id="main" className={narrow ? classes.mainNarrow : classes.mainWide} tabIndex={-1}>
        {narrow && subtitle ? <div className={classes.subtitleNarrow}>{subtitle}</div> : null}
        {!narrow && title ? (
          <header className={classes.head}>
            <div>
              <h1 className={classes.title}>{title}</h1>
              {subtitle ? <div className={classes.subtitle}>{subtitle}</div> : null}
            </div>
            {actions ? <div className={classes.actions}>{actions}</div> : null}
          </header>
        ) : null}
        {children}
      </main>
      {narrow && foot ? <footer className={closing ? `${classes.foot} ${classes.footClosing}` : classes.foot}>{foot}</footer> : null}
    </>
  );
}

export interface ViewItem {
  key: string;
  label: ReactNode;
  count?: number | undefined;
}

export interface ViewTabsProps {
  label: string;
  views: ViewItem[];
  current?: string | undefined;
  onSelect?: ((key: string) => void) | undefined;
  /** Search and filter, on the tabs' own line on a PC. On a phone they sit above the tabs. */
  tools?: ReactNode;
}

/** A spec's saved views, or a board's states on a phone. They scroll sideways when they don't fit. */
export function ViewTabs({ label, views, current, onSelect, tools }: ViewTabsProps): ReactNode {
  const { narrow } = useFrame();
  const tabs = (
    <nav className={classes.views} aria-label={label}>
      {views.map((view) => (
        <button key={view.key} type="button" className={classes.view} aria-current={view.key === current ? "true" : undefined} onClick={() => onSelect?.(view.key)}>
          {view.label}
          {view.count !== undefined ? <span className={classes.count}>{view.count}</span> : null}
        </button>
      ))}
    </nav>
  );
  if (narrow) {
    return (
      <>
        {tools ? <div className={classes.toolsNarrow}>{tools}</div> : null}
        {tabs}
      </>
    );
  }
  return (
    <div className={classes.viewsRow}>
      {tabs}
      {tools ? <div className={classes.tools}>{tools}</div> : null}
    </div>
  );
}

/** A row in a phone's foot: a total at the start, the action at the end. */
export function FootRow({ total, totalLabel, children }: { total?: ReactNode; totalLabel?: ReactNode; children: ReactNode }): ReactNode {
  return (
    <div className={classes.footRow}>
      {total !== undefined ? (
        <div className={classes.footTotal}>
          {totalLabel ? <span className={classes.footLabel}>{totalLabel}</span> : null}
          <b>{total}</b>
        </div>
      ) : null}
      <div className={total !== undefined ? classes.footAction : classes.footActions}>{children}</div>
    </div>
  );
}
