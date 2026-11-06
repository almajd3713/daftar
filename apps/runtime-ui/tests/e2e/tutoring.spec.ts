/** Two entities joined by a link, whose children aren't typed in a form. */
import { expect, test } from "@playwright/test";

import { baseOf, expectGoodScreen, PHONE, signUp, watchForErrors } from "./helpers.js";

const base = baseOf("tutoring");

test.describe.serial("the tutoring register", () => {
  test.use(PHONE);

  test("a link is picked by name, and the list shows that name, not an id", async ({ page }) => {
    const errors = watchForErrors(page);
    await signUp(page, base);
    await page.goto(`${base}/?lang=fr`);
    const nav = page.getByRole("navigation", { name: "Menu" });
    await nav.getByRole("button", { name: "Classes" }).click();
    await page.getByRole("button", { name: "Ajouter" }).click();
    await expect(page.locator("#field-students")).toHaveCount(0);
    await page.locator("#field-code").fill("MATH");
    await page.locator("#field-name").fill("Mathématiques");
    await page.locator("#field-monthly_fee").fill("3 000");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("main").getByRole("button", { name: /Mathématiques/ })).toContainText("3\u00a0000,00");

    await nav.getByRole("button", { name: "Élèves" }).click();
    await page.getByRole("button", { name: "Ajouter" }).click();
    // A class's name is its code, as this spec's naming rule says.
    await expect(page.locator("#field-class")).toContainText("MATH");
    await expectGoodScreen(page, "form with a link");

    await page.locator("#field-full_name").fill("Amine Cherif");
    await page.locator("#field-parent_phone").fill("0550123456");
    await page.locator("#field-class").selectOption({ label: "MATH" });
    // Nothing is chosen yet, so saving says so, rather than taking the first option a person never picked.
    await expect(page.locator("#field-level")).toHaveValue("");
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("alert")).toContainText("obligatoire");
    await page.locator("#field-level").selectOption({ index: 1 });
    await page.getByRole("button", { name: "Enregistrer" }).click();
    await expect(page.getByRole("main").getByRole("button", { name: /Amine Cherif/ })).toBeVisible();

    const stored = await (await page.request.get(`${base}/api/e/students`)).json();
    expect(stored.rows[0]._labels.class).toBe("MATH");
    await expect(page.getByRole("main").getByRole("button", { name: /Amine Cherif/ })).not.toContainText(stored.rows[0].class);
    await expectGoodScreen(page, "list");
    expect(errors).toEqual([]);
  });
});
