/** The server runs a workbook's formulas. The page has to send what's on screen, and never show a figure that isn't its answer. */
import { expect, test, type Locator, type Page } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

const fee = baseOf("fee");
const models = baseOf("models");
const generated = baseOf("generated");

/** The value on a result's line. */
function resultOf(page: Page, label: string): Locator {
  return page.locator("dl > div", { has: page.locator("dt", { hasText: new RegExp(`^${label}$`) }) }).locator("dd");
}

test.describe.serial("a spec that is only a calculator", () => {
  test.use(PC);

  test("opens on it, showing what the workbook shows for its own values", async ({ page }) => {
    await signUp(page, fee);
    const errors = watchForErrors(page);
    await page.goto(`${fee}/?lang=fr`);
    await expect(page.getByRole("heading", { name: "Frais de scolarité", level: 1 })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Menu" }).getByRole("button", { name: "Frais de scolarité" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByLabel("Nombre de matières")).toHaveValue("1");
    await expect(resultOf(page, "Taux de remise")).toHaveText("0 %");
    await expect(resultOf(page, "Total à payer")).toHaveText("3 000,00 DA");
    await expectGoodScreen(page, "a calculator on a PC");
    expect(errors).toEqual([]);
  });

  test("gives the workbook's answer for what's typed, and Enter works as the button does", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await page.getByLabel("Prix par matière").fill("2500");
    await page.getByLabel("Nombre de matières").fill("3");
    await page.getByLabel("Frères et sœurs inscrits").fill("2");
    await page.getByLabel("Frères et sœurs inscrits").press("Enter");
    await expect(resultOf(page, "Taux de remise")).toHaveText("10 %");
    await expect(resultOf(page, "Total à payer")).toHaveText("6 750,00 DA");
    // On a PC the result is beside the form, so the person stays in the field to try another value.
    await expect(page.getByLabel("Frères et sœurs inscrits")).toBeFocused();
  });

  test("takes the figure away as soon as a value changes, so it can't be read against the wrong values", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await expect(resultOf(page, "Total à payer")).toHaveText("3 000,00 DA");
    await page.getByLabel("Nombre de matières").fill("2");
    await expect(resultOf(page, "Total à payer")).toHaveText("–");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Total à payer")).toHaveText("6 000,00 DA");
  });

  test("drops an answer that arrives after a value has changed", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await expect(resultOf(page, "Total à payer")).toHaveText("3 000,00 DA");
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/calc/**", async (route) => {
      await held;
      await route.continue();
    });
    await page.getByLabel("Nombre de matières").fill("2");
    const answered = page.waitForResponse("**/api/calc/**");
    await page.getByRole("button", { name: "Calculer" }).click();
    await page.getByLabel("Nombre de matières").fill("4");
    release();
    await answered;
    await page.unroute("**/api/calc/**");
    // Past the moment that answer would have been drawn: the figure for 2 must not stand beside the 4.
    await expect(page.getByRole("button", { name: "Calculer" })).toBeEnabled();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
    await expect(resultOf(page, "Total à payer")).toHaveText("–");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Total à payer")).toHaveText("12 000,00 DA");
  });

  test("calculates a cleared value as blank, as the workbook would, and not as its default", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await page.getByLabel("Nombre de matières").fill("");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Total à payer")).toHaveText("0,00 DA");
  });

  test("says what's wrong with a value in the server's words, and shows no figure until it's fixed", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await page.getByLabel("Nombre de matières").fill("beaucoup");
    await page.getByRole("button", { name: "Calculer" }).click();
    const summary = page.getByRole("alert");
    await expect(summary).toContainText("Nombre de matières");
    await expect(summary).toBeFocused();
    await expect(page.getByLabel("Nombre de matières")).toHaveAttribute("aria-invalid", "true");
    await expect(resultOf(page, "Total à payer")).toHaveText("–");
    await expectGoodScreen(page, "a refused input");
    await page.getByLabel("Nombre de matières").fill("2");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Total à payer")).toHaveText("6 000,00 DA");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("says when the server can't be reached, and keeps what's typed", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await page.route("**/api/calc/**", (route) => route.abort());
    await page.getByLabel("Nombre de matières").fill("5");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(page.getByRole("alert")).toContainText("Le serveur ne répond pas");
    await expect(page.getByLabel("Nombre de matières")).toHaveValue("5");
    await page.unroute("**/api/calc/**");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Total à payer")).toHaveText("15 000,00 DA");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("keeps its address across a reload, and an unknown one is a missing page", async ({ page }) => {
    await signIn(page, fee);
    await page.goto(`${fee}/c/tuition_fee?lang=fr`);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Frais de scolarité", level: 1 })).toBeVisible();
    await page.goto(`${fee}/c/nothing_like_it?lang=fr`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();
  });
});

test.describe.serial("a calculator on a phone", () => {
  test.use(PHONE);

  test("works in French and in Arabic", async ({ page }) => {
    await signIn(page, fee);
    const errors = watchForErrors(page);
    await page.goto(`${fee}/?lang=ar`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "رسوم الدراسة", level: 1 })).toBeVisible();
    await expect(resultOf(page, "المبلغ الإجمالي")).toContainText("د.ج.");
    await expectGoodScreen(page, "a calculator on a phone, in Arabic");

    await page.getByLabel("عدد المواد").fill("2");
    await page.getByLabel("عدد الإخوة المسجلين").fill("1");
    await page.getByRole("button", { name: "احسب" }).click();
    await expect(resultOf(page, "نسبة التخفيض")).toContainText("5");
    await expect(resultOf(page, "المبلغ الإجمالي")).toContainText("5.700,00");
    await expectGoodScreen(page, "a result on a phone, in Arabic");

    await page.goto(`${fee}/?lang=fr`);
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
    await expect(resultOf(page, "Total à payer")).toHaveText("3 000,00 DA");
    await expectGoodScreen(page, "a calculator on a phone, in French");
    expect(errors).toEqual([]);
  });
});

/**
 * The hand-written examples have money and whole numbers. A generated calculator is what a client really gets, and
 * so far every number in one is a decimal. The figures are checked without a currency, so this holds once it has one.
 */
test.describe.serial("a calculator generated from a real workbook", () => {
  test.use(PHONE);

  test("works in both languages, and a count doesn't read as 2,00", async ({ page }) => {
    await signUp(page, generated);
    const errors = watchForErrors(page);
    await page.goto(`${generated}/c/calcul?lang=fr`);
    await expect(page.getByLabel("Nombre de matières")).toHaveValue("2");
    await expect(page.getByLabel("Prix par matière")).toHaveValue("3 000");
    await expect(resultOf(page, "À payer")).toContainText("5 700");
    await expectGoodScreen(page, "a generated calculator, in French");

    await page.getByLabel("Nombre de matières").fill("3");
    await page.getByLabel("Nombre de matières").press("Enter");
    await expect(resultOf(page, "À payer")).toContainText("8 550");

    await page.goto(`${generated}/c/calcul?lang=ar`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(resultOf(page, "À payer")).toContainText("5.700");
    await expectGoodScreen(page, "a generated calculator, in Arabic");
    expect(errors).toEqual([]);
  });
});

test.describe.serial("calculators beside a firm's lists", () => {
  test.use(PC);

  test("come after the lists, and an entity may share a calculator's name", async ({ page }) => {
    await signUp(page, models);
    await page.goto(`${models}/?lang=fr`);
    const menu = page.getByRole("navigation", { name: "Menu" });
    await expect(menu.getByRole("button")).toHaveText(["Clients", "Location", "Marge", "Réservé", "Barème clients"]);
    await expect(menu.getByRole("button", { name: "Clients", exact: true })).toHaveAttribute("aria-current", "page");

    await menu.getByRole("button", { name: "Barème clients" }).click();
    await expect(page).toHaveURL(/\/c\/clients$/);
    await expect(menu.getByRole("button", { name: "Barème clients" })).toHaveAttribute("aria-current", "page");
    await expect(menu.getByRole("button", { name: "Clients", exact: true })).not.toHaveAttribute("aria-current", "page");
    await expect(resultOf(page, "Points")).toHaveText("20");

    await menu.getByRole("button", { name: "Clients", exact: true }).click();
    await expect(page).toHaveURL(/\/v\/clients_all$/);
  });

  test("show each type as the rest of the app does, even when a formula gives something else", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/c/rental?lang=fr`);
    await expect(resultOf(page, "Fin")).toHaveText("01/12/2026");
    await expect(resultOf(page, "Mois de début")).toHaveText("11");
    await expect(resultOf(page, "Zone retenue")).toHaveText("Nord");
    // A whole result has no decimals, because the analyser calls any number a decimal.
    await expect(resultOf(page, "Coût par jour")).toHaveText("1 190");
    await expect(resultOf(page, "Prime")).toHaveText("–");
    await expect(resultOf(page, "Remarque")).toHaveText("-");
    await expect(resultOf(page, "Longue durée")).toHaveText("Non");
    await expect(resultOf(page, "Part de la taxe")).toHaveText("15,97 %");
    await expect(resultOf(page, "Prix total")).toHaveText("35 700,00 DA");
    // A workbook's count isn't "4,00", though the analyser can only call it a decimal.
    await expect(page.getByLabel("Semaines par bloc")).toHaveValue("4");
    await expect(page.getByLabel("Taxe")).toHaveValue("19,00");
    await expectGoodScreen(page, "every kind of result");
  });

  test("send every kind of input, so a change to any of them reaches the formula", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/c/rental?lang=fr`);
    await expect(resultOf(page, "Prix total")).toHaveText("35 700,00 DA");
    await page.getByLabel("Jours").fill("10");
    await page.getByLabel("Taxe").fill("10");
    await page.getByLabel("Urgent").check();
    await page.getByLabel("Zone", { exact: true }).selectOption("south");
    await page.getByLabel("Début").fill("25/12/2026");
    await page.getByLabel("Début").press("Tab");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Fin")).toHaveText("04/01/2027");
    await expect(resultOf(page, "Mois de début")).toHaveText("12");
    await expect(resultOf(page, "Zone retenue")).toHaveText("Sud");
    await expect(resultOf(page, "Prix total")).toHaveText("22 000,00 DA");

    await page.getByLabel("Taxe").fill("12,345");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Coût par jour")).toHaveText("2 246,90");
  });

  test("show an Excel error where its value would be, and say so in words", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/c/rental?lang=fr`);
    await page.getByLabel("Jours").fill("0");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Coût par jour")).toHaveText("#DIV/0!");
    await expect(page.getByRole("alert")).toContainText("Le calcul donne une erreur avec ces valeurs");
    await expectGoodScreen(page, "an Excel error");
    await page.getByLabel("Jours").fill("5");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("keep their figures when the language changes", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/c/rental?lang=fr`);
    await page.getByLabel("Jours").fill("10");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Prix total")).toHaveText("11 900,00 DA");
    await page.getByRole("button", { name: "العربية" }).click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(resultOf(page, "السعر الإجمالي")).toContainText("11.900,00");
    await expect(page.getByLabel("الأيام")).toHaveValue("10");
    await expectGoodScreen(page, "every kind of result, in Arabic");
  });

  test("wait for the person when an input has no value, instead of showing what a blank gives", async ({ page }) => {
    await signIn(page, models);
    let asked = 0;
    page.on("request", (request) => {
      if (request.url().includes("/api/calc/")) asked += 1;
    });
    await page.goto(`${models}/c/margin?lang=fr`);
    await expect(resultOf(page, "Prix de vente")).toHaveText("–");
    await expectGoodScreen(page, "a calculator waiting for a value");
    expect(asked).toBe(0);
    await page.getByLabel("Coût").fill("100");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Prix de vente")).toHaveText("150,00 DA");
    await expect(resultOf(page, "Marge gardée")).toHaveText("50,00 DA");
  });

  test("hide from a role the outputs it may not read, and a calculator with none left", async ({ page }) => {
    await signIn(page, models);
    expect((await page.request.post(`${models}/api/auth/users`, { data: { username: "rafik", password: PASSWORD, role: "staff" } })).status()).toBe(201);
    await page.context().clearCookies();
    await signIn(page, models, "rafik");
    await page.goto(`${models}/?lang=fr`);
    await expect(page.getByRole("navigation", { name: "Menu" }).getByRole("button")).toHaveText(["Clients", "Location", "Marge", "Barème clients"]);

    await page.goto(`${models}/c/margin?lang=fr`);
    await page.getByLabel("Coût").fill("100");
    await page.getByRole("button", { name: "Calculer" }).click();
    await expect(resultOf(page, "Prix de vente")).toHaveText("150,00 DA");
    await expect(page.getByText("Marge gardée")).toHaveCount(0);

    await page.goto(`${models}/c/owners_only?lang=fr`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();
  });
});

test.describe.serial("a long calculator on a phone", () => {
  test.use(PHONE);

  test("brings the result up and closes the keyboard when a person asks for it", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/c/rental?lang=fr`);
    await expect(resultOf(page, "Prix total")).toHaveText("35 700,00 DA");
    await expect(page.getByRole("button", { name: "Calculer" })).toBeVisible();
    const days = page.getByLabel("Jours");
    await days.fill("10");
    await days.press("Enter");
    await expect(resultOf(page, "Prix total")).toHaveText("11 900,00 DA");
    // Focus on anything but a field is what closes a phone's keyboard.
    await expect(page.locator("[aria-live]")).toBeFocused();
    await expect(resultOf(page, "Fin")).toBeInViewport();
    await expectGoodScreen(page, "a long result on a phone");
  });

  test("reaches what doesn't fit along the bottom through More", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/?lang=fr`);
    const bar = page.getByRole("navigation", { name: "Menu" });
    await expect(bar.getByRole("button")).toHaveText(["Clients", "Location", "Marge", "Réservé", "Plus"]);
    await bar.getByRole("button", { name: "Plus" }).click();
    await page.getByRole("button", { name: "Barème clients" }).click();
    await expect(page).toHaveURL(/\/c\/clients$/);
    await expect(resultOf(page, "Points")).toHaveText("20");
    await expect(bar.getByRole("button", { name: "Plus" })).toHaveAttribute("aria-current", "page");
  });
});
