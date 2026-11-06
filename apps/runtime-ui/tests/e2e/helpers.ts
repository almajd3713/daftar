import AxeBuilder from "@axe-core/playwright";
import { expectClean, measure } from "@daftar/ui/testing";
import { expect, type Page } from "@playwright/test";

export const APPS = {
  repair: { spec: "repair-tracker", port: 5181 },
  payments: { spec: "payments-ledger", port: 5182 },
  tutoring: { spec: "tutoring-register", port: 5183 },
} as const;

export const PREVIEW_ENV = "DAFTAR_E2E_PREVIEW";
export const PASSWORD = "un-long-mot-de-passe-1";

export const baseOf = (app: keyof typeof APPS): string => `http://127.0.0.1:${APPS[app].port}`;

export const PHONE = { viewport: { width: 360, height: 680 }, hasTouch: true, isMobile: true };
export const PC = { viewport: { width: 1280, height: 800 } };

/** The same measures and axe rules the design system's own screens are held to. */
export async function expectGoodScreen(page: Page, label: string): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  expectClean(await page.evaluate(measure));
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
  expect(results.violations.map((violation) => `${label} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** Collects what shouldn't happen on any screen. A refused request logs a network line, which is expected. */
export function watchForErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) errors.push(message.text());
  });
  return errors;
}

export async function signUp(page: Page, base: string, username = "samira"): Promise<void> {
  const response = await page.request.post(`${base}/api/auth/setup`, { data: { username, password: PASSWORD } });
  expect(response.status()).toBe(201);
}

export async function signIn(page: Page, base: string, username = "samira"): Promise<void> {
  const response = await page.request.post(`${base}/api/auth/login`, { data: { username, password: PASSWORD } });
  expect(response.status()).toBe(200);
}
