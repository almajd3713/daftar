/** Two entities joined by a link, whose children aren't typed in a form. */
import { expect, test } from "@playwright/test";

import { baseOf, expectGoodScreen, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

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

  test("a link leads to the record it names, and a record lists those pointing at it", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    await page.goto(`${base}/?lang=fr`);
    await page.getByRole("navigation", { name: "Menu" }).getByRole("button", { name: "Élèves" }).click();
    await page.getByRole("main").getByRole("button", { name: /Amine Cherif/ }).click();
    await expect(page.getByRole("heading", { name: "Amine Cherif", level: 1 })).toBeVisible();
    await expectGoodScreen(page, "a record with a link");

    await page.getByRole("main").getByRole("button", { name: "MATH" }).click();
    await expect(page.getByRole("heading", { name: "Mathématiques", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Élèves (1)" })).toBeVisible();
    await expectGoodScreen(page, "a record with children");

    await page.getByRole("main").getByRole("button", { name: "Amine Cherif" }).click();
    await expect(page.getByRole("heading", { name: "Amine Cherif", level: 1 })).toBeVisible();
    // Back goes where this person came from, one step at a time.
    await page.getByRole("button", { name: "Retour" }).click();
    await expect(page.getByRole("heading", { name: "Mathématiques", level: 1 })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("deleting what others depend on says why it can't be done", async ({ page }) => {
    await signIn(page, base);
    const classes = await (await page.request.get(`${base}/api/e/classes`)).json();
    await page.goto(`${base}/e/classes/${classes.rows[0]._id}?lang=fr`);
    await page.getByRole("button", { name: "Supprimer" }).click();
    await page.getByRole("button", { name: "Oui, supprimer" }).click();
    await expect(page.getByRole("alert")).toContainText("D'autres éléments dépendent de celui-ci");
    await expect(page.getByRole("heading", { name: "Mathématiques", level: 1 })).toBeVisible();
    await expectGoodScreen(page, "a refused deletion");
  });

  test("history names a link's target, not its id", async ({ page }) => {
    await signIn(page, base);
    const created = await page.request.post(`${base}/api/e/classes`, { data: { code: "PHY", name: "Physique", monthly_fee: 3500 } });
    expect(created.status(), await created.text()).toBe(201);
    const physics = await created.json();
    const students = await (await page.request.get(`${base}/api/e/students`)).json();
    const { _id, _version, class: maths } = students.rows[0];
    expect((await page.request.patch(`${base}/api/e/students/${_id}`, { data: { class: physics._id, _version } })).status()).toBe(200);

    await page.goto(`${base}/e/students/${_id}?lang=fr`);
    const line = page.getByText(/Classe\s*:/).last();
    await expect(line).toContainText("MATH");
    await expect(line).toContainText("PHY");
    await expect(page.getByRole("main")).not.toContainText(maths);
    await expect(page.getByRole("main")).not.toContainText(physics._id);
    await expectGoodScreen(page, "history with a link");
  });
});
