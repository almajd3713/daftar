/**
 * The reference app. `?bare=1` draws one screen filling the window, which is what the browser tests use.
 * Otherwise it draws a phone frame and a PC frame side by side, each measuring its own width, with controls.
 */
import "../src/styles/index.css";

import { useState, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

import { DaftarProvider, type Locale } from "../src/index.js";
import { SCREENS, type ScreenKey } from "./screens.js";
import classes from "./preview.module.css";

const params = new URLSearchParams(location.search);
const initialScreen = (params.get("screen") ?? "list") as ScreenKey;
const initialLocale: Locale = params.get("lang") === "fr" ? "fr-DZ" : "ar-DZ";
const initialMode = params.get("mode") === "dark" ? "dark" : params.get("mode") === "light" ? "light" : undefined;
const initialAwkward = params.get("data") === "awkward";

function App(): ReactNode {
  const [screen, setScreen] = useState<ScreenKey>(SCREENS[initialScreen] ? initialScreen : "list");
  const [locale, setLocale] = useState<Locale>(initialLocale);
  const [mode, setMode] = useState<"light" | "dark" | undefined>(initialMode);
  const [awkward, setAwkward] = useState(initialAwkward);
  const Screen = SCREENS[screen].component;
  if (params.get("bare") === "1") {
    return (
      <DaftarProvider locale={locale} colorScheme={mode}>
        <Screen awkward={awkward} onLocale={setLocale} />
      </DaftarProvider>
    );
  }
  return (
    <DaftarProvider locale={locale} colorScheme={mode}>
      <div className={classes.bench} dir="ltr">
        <div className={classes.controls}>
          {(Object.keys(SCREENS) as ScreenKey[]).map((key) => (
            <button key={key} type="button" aria-pressed={key === screen} onClick={() => setScreen(key)}>
              {SCREENS[key].name}
            </button>
          ))}
          <span className={classes.gap} />
          <button type="button" aria-pressed={locale === "ar-DZ"} onClick={() => setLocale("ar-DZ")}>العربية</button>
          <button type="button" aria-pressed={locale === "fr-DZ"} onClick={() => setLocale("fr-DZ")}>Français</button>
          <span className={classes.gap} />
          <button type="button" aria-pressed={mode !== "dark"} onClick={() => setMode("light")}>Light</button>
          <button type="button" aria-pressed={mode === "dark"} onClick={() => setMode("dark")}>Dark</button>
          <span className={classes.gap} />
          <button type="button" aria-pressed={awkward} onClick={() => setAwkward(!awkward)}>Awkward data</button>
        </div>
        <div className={classes.frames} dir={locale === "ar-DZ" ? "rtl" : "ltr"}>
          <div className={classes.phone}><Screen awkward={awkward} onLocale={setLocale} /></div>
          <div className={classes.desk}><Screen awkward={awkward} onLocale={setLocale} /></div>
        </div>
      </div>
    </DaftarProvider>
  );
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);
