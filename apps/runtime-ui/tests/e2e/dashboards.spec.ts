/** A dashboard's figures come from the server's rows. The hand-written examples only count and sum, so a fixture covers the rest. */
import { expect, test, type Locator, type Page } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

const payments = baseOf("dashPayments");
const models = baseOf("dashModels");
const generated = baseOf("dashGenerated");

const line = (page: Page, label: string): Locator => page.locator("dl > div", { has: page.locator("dt", { hasText: new RegExp(`^${label}$`) }) }).locator("dd");
const panel = (page: Page, title: string): Locator => page.locator("section", { has: page.getByRole("heading", { name: title, level: 2 }) });
const barsIn = (scope: Locator): Locator => scope.locator("li");

async function add(page: Page, base: string, entity: string, data: object): Promise<string> {
  const response = await page.request.post(`${base}/api/e/${entity}`, { data });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { _id: string })._id;
}

test.describe.serial("a ledger's dashboard on a PC", () => {
  test.use(PC);

  test("comes after the lists, leads with its figure, and draws its line in time", async ({ page }) => {
    await signUp(page, payments);
    const pay = (receipt_no: string, period: string, amount_due: number, amount_paid: number, status: string): object => ({ receipt_no, payer: "Benali Samir", period, amount_due, amount_paid, status });
    await add(page, payments, "payments", pay("R-1", "2026-01-01", 1000, 1000, "paid"));
    await add(page, payments, "payments", pay("R-2", "2026-01-01", 2000, 500, "partial"));
    await add(page, payments, "payments", pay("R-3", "2026-03-01", 4000, 1500, "partial"));
    const errors = watchForErrors(page);

    await page.goto(`${payments}/?lang=fr`);
    const menu = page.getByRole("navigation", { name: "Menu" });
    await expect(menu.getByRole("button")).toHaveText(["Paiements", "Encaissements"]);
    await menu.getByRole("button", { name: "Encaissements" }).click();
    await expect(page).toHaveURL(/\/d\/cash$/);
    await expect(menu.getByRole("button", { name: "Encaissements" })).toHaveAttribute("aria-current", "page");

    // The figure is filtered: what's already paid isn't still to collect.
    await expect(page.getByText("Total à encaisser")).toBeVisible();
    await expect(page.getByRole("main")).toContainText("4\u00a0000,00");
    await expect(page.getByRole("main")).toContainText("DA");

    const chart = panel(page, "Encaissé par mois");
    await expect(chart.locator("svg")).toBeVisible();
    await chart.getByText("Voir les chiffres").click();
    await expect(chart.locator("tbody tr")).toHaveCount(2);
    await expect(chart.locator("tbody tr").nth(0)).toContainText("1\u00a0500,00");
    await expect(chart.locator("tbody tr").nth(1)).toContainText("1\u00a0500,00");
    await expect(chart.locator("th").first()).toHaveText("Mois");
    await expectGoodScreen(page, "a dashboard");
    expect(errors).toEqual([]);
  });

  test("keeps its address across a reload, and an unknown one is a missing page", async ({ page }) => {
    await signIn(page, payments);
    await page.goto(`${payments}/d/cash?lang=fr`);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Encaissements", level: 1 })).toBeVisible();
    await page.goto(`${payments}/d/nothing_like_it?lang=fr`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();
  });
});

test.describe.serial("a ledger's dashboard on a phone", () => {
  test.use(PHONE);

  test("works in Arabic", async ({ page }) => {
    await signIn(page, payments);
    const errors = watchForErrors(page);
    await page.goto(`${payments}/d/cash?lang=ar`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByRole("heading", { name: "التحصيل", level: 1 })).toBeVisible();
    await expect(page.getByRole("main")).toContainText("4.000,00");
    await expect(page.getByRole("main")).toContainText("د.ج.");
    await expectGoodScreen(page, "a dashboard on a phone, in Arabic");
    expect(errors).toEqual([]);
  });
});

test.describe.serial("every kind of widget", () => {
  test.use(PC);

  test("works out each figure, and a blank neither lowers an average nor counts as the smallest", async ({ page }) => {
    await signUp(page, models);
    await add(page, models, "sales", { ref: "A", amount: 100, qty: 1, rate: 0.05, zone: "east", day: "2026-11-02", month: "2026-01-01" });
    await add(page, models, "sales", { ref: "B", amount: 300, qty: 2, rate: 0.125, zone: "east", day: "2026-11-02", month: "2026-02-01" });
    await add(page, models, "sales", { ref: "C", amount: 500, qty: 2, zone: "west", day: "2026-11-09", month: "2026-02-01" });
    // Has no amount, no rate and no zone.
    await add(page, models, "sales", { ref: "D", qty: 1, day: "2026-11-10", month: "2027-01-01" });
    const errors = watchForErrors(page);

    await page.goto(`${models}/d/figures?lang=fr`);
    await expect(page.getByText("Total des ventes")).toBeVisible();
    await expect(page.getByRole("main")).toContainText("900,00");
    await expect(line(page, "Nombre de ventes")).toHaveText("4");
    await expect(line(page, "Vente moyenne")).toHaveText("300,00\u00a0DA");
    await expect(line(page, "Plus petite vente")).toHaveText("100,00\u00a0DA");
    await expect(line(page, "Plus grande vente")).toHaveText("500,00\u00a0DA");
    await expect(line(page, "Quantité vendue")).toHaveText("6");
    await expect(line(page, "Quantité moyenne")).toHaveText("1,50");
    await expect(line(page, "Meilleure remise")).toHaveText("12,5\u00a0%");
    await expect(line(page, "Ventes à l’Est")).toHaveText("2");
    await expectGoodScreen(page, "every kind of figure");
    expect(errors).toEqual([]);
  });

  test("keeps a choice's bars in the spec's order, puts blanks last, and says a bar's currency once", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/d/figures?lang=fr`);
    const counted = barsIn(panel(page, "Ventes par zone"));
    await expect(counted).toHaveCount(3);
    // West is first in the spec, though it has fewer sales and sorts after east.
    await expect(counted.nth(0)).toContainText("Ouest");
    await expect(counted.nth(0)).toContainText("1");
    await expect(counted.nth(1)).toContainText("Est");
    await expect(counted.nth(1)).toContainText("2");
    await expect(counted.nth(2)).toContainText("Sans valeur");

    const amounts = panel(page, "Montant par zone (DA)");
    await expect(amounts).toBeVisible();
    await expect(barsIn(amounts).nth(0)).toContainText("500,00");
  });

  test("draws a bar to its value however long the number is, because two different amounts mustn't look the same", async ({ page }) => {
    await signIn(page, models);
    await add(page, models, "sales", { ref: "Grande Ouest", amount: 6000000, zone: "west" });
    await add(page, models, "sales", { ref: "Grande Est", amount: 5400000, zone: "east" });
    await page.goto(`${models}/d/figures?lang=fr`);
    const fills = barsIn(panel(page, "Montant par zone (DA)")).locator("[class*=fill]");
    await expect(fills).toHaveCount(2);
    const widths = await fills.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().width));
    expect((widths[1] ?? 0) / (widths[0] ?? 1)).toBeCloseTo(5400400 / 6000500, 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });

  test("draws lines oldest first, keeps a date's place in time, and names a month", async ({ page }) => {
    await signIn(page, models);
    await page.goto(`${models}/d/trends?lang=fr`);
    const days = panel(page, "Ventes par jour");
    await days.getByText("Voir les chiffres").click();
    await expect(days.locator("tbody tr")).toHaveCount(3);
    await expect(days.locator("tbody tr").nth(0)).toContainText("02/11");
    await expect(days.locator("tbody tr").nth(0)).toContainText("400,00");
    await expect(days.locator("tbody tr").nth(2)).toContainText("10/11");

    const months = panel(page, "Ventes par mois");
    await months.getByText("Voir les chiffres").click();
    await expect(months.locator("tbody tr")).toHaveCount(3);
    // These run across a new year, so each month says which.
    await expect(months.locator("tbody tr").nth(2)).toContainText("27");
    // In the narrower panel too, its text is the size the type scale says, not scaled with the chart.
    for (const svg of await page.locator("figure svg").all()) {
      expect(await svg.evaluate((item: SVGSVGElement) => Math.abs(item.getBoundingClientRect().width - item.viewBox.baseVal.width))).toBeLessThanOrEqual(1);
    }
    await expectGoodScreen(page, "line charts");
  });

  test("ranks bars with no order of their own, names a link's target, and shows only the first of many", async ({ page }) => {
    await signIn(page, models);
    const ids: string[] = [];
    for (let index = 0; index < 25; index += 1) ids.push(await add(page, models, "clients", { name: `Client ${String(index).padStart(2, "0")}` }));
    // The last client buys the most, so it leads however it sorts by name.
    for (let index = 0; index < 3; index += 1) await add(page, models, "sales", { ref: `Grand ${index}`, customer: ids[24] });
    for (const id of ids.slice(0, 24)) await add(page, models, "sales", { ref: "Un", customer: id });

    await page.goto(`${models}/d/customers?lang=fr`);
    const chart = panel(page, "Ventes par client");
    await expect(barsIn(chart)).toHaveCount(20);
    await expect(barsIn(chart).first()).toContainText("Client 24");
    await expect(barsIn(chart).first()).toContainText("3");
    await expect(chart).toContainText("Les 20 premiers sur 26");
    await expectGoodScreen(page, "many bars");
  });

  test("says so when a chart has nothing to draw", async ({ page }) => {
    await signIn(page, models);
    const errors = watchForErrors(page);
    await page.goto(`${models}/d/nothing_yet?lang=fr`);
    await expect(panel(page, "Aucune barre")).toContainText("Rien à afficher pour l’instant.");
    await expect(panel(page, "Aucune courbe")).toContainText("Rien à afficher pour l’instant.");
    await expectGoodScreen(page, "empty charts");
    expect(errors).toEqual([]);
  });

  test("says when the server can't be reached, and offers to try again", async ({ page }) => {
    await signIn(page, models);
    await page.route("**/api/e/sales**", (route) => route.abort());
    await page.goto(`${models}/d/figures?lang=fr`);
    await expect(page.getByRole("alert")).toContainText("Le serveur ne répond pas");
    await page.unroute("**/api/e/sales**");
    await page.getByRole("button", { name: "Réessayer" }).click();
    await expect(line(page, "Nombre de ventes")).toBeVisible();
  });

  test("shows a role only what it may see, and a dashboard with nothing left isn't there", async ({ page }) => {
    await signIn(page, models);
    expect((await page.request.post(`${models}/api/auth/users`, { data: { username: "rafik", password: PASSWORD, role: "staff" } })).status()).toBe(201);
    await page.goto(`${models}/?lang=fr`);
    const menu = page.getByRole("navigation", { name: "Menu" });
    await expect(menu.getByRole("button", { name: "Pour le patron" })).toBeVisible();

    await page.context().clearCookies();
    await signIn(page, models, "rafik");
    const errors = watchForErrors(page);
    await page.goto(`${models}/?lang=fr`);
    await expect(menu.getByRole("button", { name: "Chiffres" })).toBeVisible();
    await expect(menu.getByRole("button", { name: "Pour le patron" })).toHaveCount(0);
    await page.goto(`${models}/d/for_the_owner?lang=fr`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();

    // One figure is filtered on a field this role can't see. It goes, and the other still shows.
    await page.goto(`${models}/d/partly_hidden?lang=fr`);
    await expect(page.getByRole("main").getByText("Ventes", { exact: true })).toBeVisible();
    await expect(page.getByText("Ventes coûteuses")).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});

test.describe.serial("what a generated app gets", () => {
  test.use(PHONE);

  test("is a dashboard of figures, which works in both languages", async ({ page }) => {
    await signUp(page, generated);
    const errors = watchForErrors(page);
    await page.goto(`${generated}/d/overview?lang=fr`);
    await expect(page.getByRole("heading", { name: "Vue d’ensemble", level: 1 }).or(page.getByRole("heading", { name: "Vue d'ensemble", level: 1 }))).toBeVisible();
    await expect(page.getByRole("main").getByText("Élèves")).toBeVisible();
    await expectGoodScreen(page, "a generated dashboard, in French");
    await page.goto(`${generated}/d/overview?lang=ar`);
    await expect(page.getByRole("heading", { name: "نظرة عامة", level: 1 })).toBeVisible();
    await expectGoodScreen(page, "a generated dashboard, in Arabic");
    expect(errors).toEqual([]);
  });

  test("names a person on a list's phone row, where its title is only a code", async ({ page }) => {
    await signIn(page, generated);
    const students = (await (await page.request.get(`${generated}/api/e/eleves?pageSize=1`)).json()) as { rows: { eleve: string }[] };
    const student = students.rows[0]?.eleve ?? "";
    expect(student).not.toBe("");
    await page.goto(`${generated}/?lang=fr`);
    await expect(page.locator("[class*=rowMeta]").first()).toContainText(student);
  });
});
