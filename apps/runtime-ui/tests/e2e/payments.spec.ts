/** A ledger with several views of one entity, and enough rows to need paging. */
import { expect, test } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, signIn, signUp, watchForErrors } from "./helpers.js";

const base = baseOf("payments");

test.describe.serial("the payments ledger", () => {
  test.use(PC);

  test("its views are tabs, each with its own filter, sort and total", async ({ page }) => {
    await signUp(page, base);
    const receipt = (index: number, due: string, due_amount: number, paid: number, status: string): object => ({ receipt_no: `R-${String(index).padStart(4, "0")}`, payer: index % 2 ? "Benali Samir" : "حورية سعيدي", period: "2026-11-01", due_on: due, amount_due: due_amount, amount_paid: paid, status });
    const rows = [receipt(1, "2020-01-10", 1000, 1000, "paid"), receipt(2, "2020-01-11", 2000, 0, "unpaid"), receipt(3, "2099-01-12", 4000, 0, "unpaid")];
    for (const data of rows) {
      const response = await page.request.post(`${base}/api/e/payments`, { data });
      expect(response.status(), await response.text()).toBe(201);
    }
    const errors = watchForErrors(page);
    await page.goto(`${base}/?lang=fr`);
    const tabs = page.getByRole("navigation", { name: "Paiements" });
    await expect(page.locator("tbody tr")).toHaveCount(3);

    await tabs.getByRole("button", { name: /Impayés/ }).click();
    await expect(page.locator("tbody tr")).toHaveCount(2);
    await expect(page).toHaveURL(/\/v\/payments_unpaid$/);
    await expect(page.locator("tbody")).not.toContainText("R-0001");

    // A date relative to today: overdue means before today, wherever today is.
    await tabs.getByRole("button", { name: /En retard/ }).click();
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await expect(page.locator("tbody")).toContainText("R-0002");
    await expectGoodScreen(page, "a filtered view");
    expect(errors).toEqual([]);
  });

  test("search narrows the list, stays in the address, and says when nothing matches", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/?lang=fr`);
    await page.getByRole("searchbox").fill("R-0003");
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await expect(page).toHaveURL(/q=R-0003/);
    await page.reload();
    await expect(page.getByRole("searchbox")).toHaveValue("R-0003");
    await expect(page.locator("tbody tr")).toHaveCount(1);

    await page.getByRole("searchbox").fill("rien-de-tel");
    await expect(page.getByRole("heading", { name: "Aucun résultat" })).toBeVisible();
    await expectGoodScreen(page, "no results");
  });

  test("a long list pages, and the page survives a reload and the back button", async ({ page }) => {
    await signIn(page, base);
    for (let index = 10; index < 62; index += 1) {
      const response = await page.request.post(`${base}/api/e/payments`, { data: { receipt_no: `R-${String(index).padStart(4, "0")}`, payer: "Benali Samir", period: "2026-11-01", due_on: "2099-02-01", amount_due: 100, amount_paid: 0, status: "unpaid" } });
      expect(response.status()).toBe(201);
    }
    await page.goto(`${base}/?lang=fr`);
    const pager = page.getByRole("navigation", { name: "Tous les paiements" });
    await expect(pager).toContainText("1–50 sur 55");
    await expect(page.locator("tbody tr")).toHaveCount(50);
    await expectGoodScreen(page, "first page");

    await pager.getByRole("button", { name: "Suivant" }).click();
    await expect(pager).toContainText("51–55 sur 55");
    await expect(page).toHaveURL(/page=2/);
    await expect(page.locator("tbody tr")).toHaveCount(5);
    await expect(pager.getByRole("button", { name: "Suivant" })).toHaveCount(0);

    await page.reload();
    await expect(pager).toContainText("51–55 sur 55");
    await page.goBack();
    await expect(pager).toContainText("1–50 sur 55");
    await expect(page.getByRole("main")).toBeFocused();
  });

  test("a computed field shows, and isn't offered for typing", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/?lang=fr`);
    await page.locator("tbody tr").first().getByRole("button").first().click();
    // On the record it's a value like any other, worked out by the server.
    await expect(page.getByRole("term").filter({ hasText: "Reste" })).toBeVisible();
    await expectGoodScreen(page, "a record with computed fields");
    await page.getByRole("button", { name: "Modifier" }).click();
    await expect(page.locator("#field-receipt_no")).toBeVisible();
    await expect(page.locator("#field-amount_due")).toBeVisible();
    await expect(page.locator("#field-remaining")).toHaveCount(0);
  });

  test("someone limited to their own records can open one, with its history, but not anyone else's", async ({ page }) => {
    await signIn(page, base);
    const others = await (await page.request.get(`${base}/api/e/payments?pageSize=1`)).json();
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "kamel", password: PASSWORD, role: "staff" } })).status()).toBe(201);
    await page.context().clearCookies();
    await signIn(page, base, "kamel");
    const mine = await page.request.post(`${base}/api/e/payments`, { data: { receipt_no: "R-9000", payer: "Kamel", period: "2026-11-01", due_on: "2099-02-01", amount_due: 500, amount_paid: 0, status: "unpaid" } });
    expect(mine.status(), await mine.text()).toBe(201);

    await page.goto(`${base}/?lang=fr`);
    await page.getByRole("main").getByRole("button", { name: "R-9000" }).click();
    await expect(page.getByRole("heading", { name: "R-9000", level: 1 })).toBeVisible();
    await expect(page.getByText("Créé", { exact: true })).toBeVisible();

    await page.goto(`${base}/e/payments/${others.rows[0]._id}`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Restaurer" })).toHaveCount(0);
  });
});
