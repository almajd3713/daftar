/** Someone who deleted the wrong thing last week has to be able to find it and bring it back. */
import { expect, test, type Page } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

const base = baseOf("deleted");

async function addPayment(page: Page, receipt_no: string): Promise<string> {
  const response = await page.request.post(`${base}/api/e/payments`, { data: { receipt_no, payer: "Benali Samir", period: "2026-11-01", amount_due: 1000 } });
  expect(response.status(), await response.text()).toBe(201);
  return ((await response.json()) as { _id: string })._id;
}

async function deletePayment(page: Page, id: string): Promise<void> {
  expect((await page.request.delete(`${base}/api/e/payments/${id}`)).status()).toBe(204);
}

test.describe.serial("the deleted list on a PC", () => {
  test.use(PC);

  test("says so when nothing has been deleted, and leads back to the list", async ({ page }) => {
    await signUp(page, base);
    await addPayment(page, "R-KEEP");
    const errors = watchForErrors(page);
    await page.goto(`${base}/?lang=fr`);
    await expect(page.locator("tbody")).toContainText("R-KEEP");
    await page.getByRole("button", { name: "Éléments supprimés" }).click();
    await expect(page).toHaveURL(/\/e\/payments\/deleted$/);
    await expect(page.getByRole("heading", { name: "Aucun élément supprimé" })).toBeVisible();
    await expectGoodScreen(page, "no deleted records");
    await page.goBack();
    await expect(page.locator("tbody")).toContainText("R-KEEP");
    expect(errors).toEqual([]);
  });

  test("finds a deleted record by name, newest first, and brings it back", async ({ page }) => {
    await signIn(page, base);
    await deletePayment(page, await addPayment(page, "R-OLD"));
    await deletePayment(page, await addPayment(page, "R-NEW"));
    const errors = watchForErrors(page);

    await page.goto(`${base}/?lang=fr`);
    await page.getByRole("button", { name: "Éléments supprimés" }).click();
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toContainText("R-NEW");
    await expect(rows.nth(0)).toContainText("samira");
    await expect(rows.nth(1)).toContainText("R-OLD");
    await expectGoodScreen(page, "the deleted list");

    await rows.nth(1).getByRole("button", { name: "R-OLD" }).click();
    await expect(page.getByRole("heading", { name: "R-OLD", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Cet élément a été supprimé" })).toBeVisible();
    await expectGoodScreen(page, "a deleted record opened from the list");

    await page.getByRole("button", { name: "Restaurer" }).click();
    await expect(page.getByRole("heading", { name: "Cet élément a été supprimé" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "R-OLD", level: 1 })).toBeVisible();

    await page.goBack();
    await expect(page).toHaveURL(/\/e\/payments\/deleted$/);
    await expect(rows).toHaveCount(1);
    await expect(rows.nth(0)).toContainText("R-NEW");
    expect(errors).toEqual([]);
  });

  test("says in words which value is in the way when a record can't come back, and it stays listed", async ({ page }) => {
    await signIn(page, base);
    await deletePayment(page, await addPayment(page, "R-TAKEN"));
    await addPayment(page, "R-TAKEN");
    await page.goto(`${base}/e/payments/deleted?lang=fr`);
    await page.getByRole("button", { name: "R-TAKEN" }).click();
    await page.getByRole("button", { name: "Restaurer" }).click();
    const notice = page.getByRole("alert");
    await expect(notice).toContainText("N° de reçu");
    await expect(page.getByRole("heading", { name: "Cet élément a été supprimé" })).toBeVisible();
    await expectGoodScreen(page, "a restore refused");

    await page.goto(`${base}/e/payments/deleted?lang=fr`);
    await expect(page.locator("tbody")).toContainText("R-TAKEN");
  });

  test("pages through a long list, keeps the page in the address, and leaves an emptied page", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/e/payments/deleted?lang=fr`);
    const count = await page.request.get(`${base}/api/e/payments/deleted?pageSize=1`);
    const already = ((await count.json()) as { total: number }).total;
    // One more than a page holds, so the second page has exactly one row on it.
    for (let index = already; index < 51; index += 1) await deletePayment(page, await addPayment(page, `R-M${String(index).padStart(3, "0")}`));

    await page.goto(`${base}/e/payments/deleted?lang=fr`);
    const pager = page.getByRole("navigation", { name: "Éléments supprimés" });
    await expect(pager).toContainText("1–50 sur 51");
    await pager.getByRole("button", { name: "Suivant" }).click();
    await expect(page).toHaveURL(/page=2/);
    await expect(pager).toContainText("51–51 sur 51");
    await page.reload();
    await expect(page.locator("tbody tr")).toHaveCount(1);

    await page.locator("tbody").getByRole("button").first().click();
    await page.getByRole("button", { name: "Restaurer" }).click();
    await expect(page.getByRole("heading", { name: "Cet élément a été supprimé" })).toHaveCount(0);
    await page.goBack();
    // That page has nothing left on it, so the list goes back to the start rather than show an empty table.
    await expect(page).toHaveURL(/\/e\/payments\/deleted$/);
    await expect(page.locator("tbody tr")).toHaveCount(50);
  });

  test("isn't offered to someone who can't restore, and its address leads nowhere for them", async ({ page }) => {
    await signIn(page, base);
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "comptable", password: PASSWORD, role: "accountant" } })).status()).toBe(201);
    await page.context().clearCookies();
    await signIn(page, base, "comptable");
    await page.goto(`${base}/?lang=fr`);
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Éléments supprimés" })).toHaveCount(0);
    await page.goto(`${base}/e/payments/deleted?lang=fr`);
    await expect(page.getByRole("heading", { name: "Page introuvable", level: 1 })).toBeVisible();
  });
});

test.describe.serial("the deleted list on a phone", () => {
  test.use(PHONE);

  test("works in Arabic, with the same way in and back", async ({ page }) => {
    await signIn(page, base);
    await deletePayment(page, await addPayment(page, "R-PHONE"));
    const errors = watchForErrors(page);
    await page.goto(`${base}/?lang=ar`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    // A row whose name is its title has only a date under it, with nothing for a separator to separate.
    await expect(page.getByRole("button", { name: /R-KEEP/ })).not.toContainText("·");
    await page.getByRole("button", { name: "العناصر المحذوفة" }).scrollIntoViewIfNeeded();
    await expectGoodScreen(page, "a list with its link to what's deleted, on a phone");
    await page.getByRole("button", { name: "العناصر المحذوفة" }).click();
    await expect(page.getByRole("heading", { name: "العناصر المحذوفة", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: /R-PHONE/ })).toBeVisible();
    await expectGoodScreen(page, "the deleted list on a phone, in Arabic");

    await page.getByRole("button", { name: /R-PHONE/ }).click();
    await expect(page.getByRole("heading", { name: "R-PHONE", level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "استرجاع" })).toBeVisible();
    await expectGoodScreen(page, "a deleted record on a phone, in Arabic");

    await page.getByRole("button", { name: "رجوع" }).click();
    await expect(page.getByRole("heading", { name: "العناصر المحذوفة", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "رجوع" }).click();
    await expect(page).toHaveURL(/\/v\/payments_all$|\/$/);
    expect(errors).toEqual([]);
  });
});
