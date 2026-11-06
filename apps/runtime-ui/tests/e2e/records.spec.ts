/** A record's own page, on a repair tracker with a workflow, a condition and hidden fields, on its own database. */
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

const base = baseOf("records");
const repair = { customer: "حورية سعيدي", received_on: "2026-11-03" };

interface Stored {
  _id: string;
  _version: number;
}

async function add(request: APIRequestContext, device: string, extra: object = {}): Promise<Stored> {
  const response = await request.post(`${base}/api/e/repairs`, { data: { ...repair, device, ...extra } });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as Stored;
}

const fact = (page: Page, label: string): Locator => page.getByRole("main").locator(`dt:text-is("${label}") + dd`);

const openRecord = async (page: Page, id: string): Promise<void> => {
  await page.goto(`${base}/e/repairs/${id}`);
};

test.describe.serial("a record on a phone", () => {
  test.use(PHONE);

  test("a row opens its record: its state, number, values and history", async ({ page }) => {
    const errors = watchForErrors(page);
    await signUp(page, base);
    await add(page.request, "iPhone 11", { price: 9800, problem: "Écran cassé\nBatterie faible" });
    await page.goto(base);
    await page.getByRole("main").getByRole("button", { name: /iPhone 11/ }).click();
    await expect(page).toHaveURL(/\/e\/repairs\/[0-9a-f-]+\?from=/);
    await expect(page.getByRole("heading", { name: "iPhone 11", level: 1 })).toBeVisible();

    const main = page.getByRole("main");
    await expect(main.getByText("مستلم")).toBeVisible();
    await expect(main.getByText(/^REP-/)).toBeVisible();
    await expect(fact(page, "الزبون")).toBeVisible();
    await expect(fact(page, "السعر")).toContainText("9.800,00");
    // The state and the title are said above, so they aren't said twice.
    await expect(main.getByRole("term").filter({ hasText: "الجهاز" })).toHaveCount(0);
    // A person's line breaks are kept, and nothing is left looking like a gap.
    expect(await main.getByRole("definition").filter({ hasText: "Écran cassé" }).evaluate((node) => getComputedStyle(node).whiteSpace)).toBe("pre-line");
    await expect(main.getByText("أُنشئ")).toBeVisible();

    // Nothing else competes with what this page offers.
    await expect(page.getByRole("navigation", { name: "القائمة" })).toHaveCount(0);
    await expectGoodScreen(page, "a record");
    expect(errors).toEqual([]);
  });

  test("a zero is a value, only what's blank reads as blank, and a phone number is grouped", async ({ page }) => {
    await signIn(page, base);
    const { _id, _version } = await add(page.request, "Gratuit", { price: 0, customer_phone: "0550123456" });
    expect((await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { price: 500, _version } })).status()).toBe(200);
    const before = await add(page.request, "Encore gratuit", { price: 0 });
    await openRecord(page, before._id);
    await expect(fact(page, "السعر")).toHaveText("0,00");
    await expect(fact(page, "تكلفة القطع")).toHaveText("–");

    await openRecord(page, _id);
    await expect(fact(page, "الهاتف")).toHaveText("0550 12 34 56");
    await expect(fact(page, "الهاتف").getByRole("link")).toHaveAttribute("href", "tel:0550123456");
    await expect(page.getByRole("main").getByText(/السعر:/)).toContainText("0,00");
  });

  test("a step moves the record, and history says who moved it and how", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    const { _id } = await add(page.request, "Galaxy A15", { price: 4000 });
    await openRecord(page, _id);
    await expect(page.getByRole("button", { name: "بدء التصليح" })).toHaveAttribute("data-variant", "filled");
    await page.getByRole("button", { name: "بدء التصليح" }).click();
    const main = page.getByRole("main");
    await expect(page.getByRole("button", { name: "تحديد كجاهز" })).toBeVisible();
    await expect(main.getByText("قيد التصليح").first()).toBeVisible();
    const line = main.getByRole("listitem").filter({ hasText: "المسار" });
    await expect(line).toContainText("samira");
    await expect(line).toContainText("مستلم");
    await expect(line).toContainText("قيد التصليح");

    // From here it can go on or go back. Going on is what's made primary, wherever the spec lists it.
    await page.getByRole("button", { name: "تحديد كجاهز" }).click();
    await expect(page.getByRole("button", { name: "تسليم" })).toHaveAttribute("data-variant", "filled");
    await expect(page.getByRole("button", { name: "إرجاع إلى التصليح" })).toHaveAttribute("data-variant", "default");
    await expectGoodScreen(page, "a record offering two steps");

    await page.getByRole("button", { name: "تسليم" }).click();
    await expect(main.getByText("مسلّم").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "تحديد كجاهز" })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("a refused step explains itself, names where to look, and goes through once that's fixed", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    const { _id } = await add(page.request, "Sans prix");
    expect((await page.request.post(`${base}/api/e/repairs/${_id}/transition`, { data: { action: "start_repair" } })).status()).toBe(200);
    await openRecord(page, _id);

    await page.getByRole("button", { name: "تحديد كجاهز" }).click();
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("تعذّر «تحديد كجاهز»");
    await expect(alert).toContainText("شروط هذا الإجراء غير مستوفاة");
    await expect(alert).toContainText("يرجى التحقق من: السعر");
    await expect(alert).toBeInViewport();
    await expect(page.getByRole("main").getByText("قيد التصليح").first()).toBeVisible();
    await expectGoodScreen(page, "a refused step");

    await page.getByRole("button", { name: "تعديل", exact: true }).click();
    await page.locator("#field-price").fill("1.500");
    await page.getByRole("button", { name: "حفظ" }).click();
    await expect(page).not.toHaveURL(/\/edit/);
    await expect(page.getByRole("heading", { name: "Sans prix", level: 1 })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByRole("button", { name: "تحديد كجاهز" }).click();
    await expect(page.getByRole("button", { name: "تسليم" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("a step someone else has already taken says so, and shows the record as it now stands", async ({ page }) => {
    await signIn(page, base);
    const { _id } = await add(page.request, "Déjà parti", { price: 100 });
    await openRecord(page, _id);
    await expect(page.getByRole("button", { name: "بدء التصليح" })).toBeVisible();
    expect((await page.request.post(`${base}/api/e/repairs/${_id}/transition`, { data: { action: "start_repair" } })).status()).toBe(200);

    await page.getByRole("button", { name: "بدء التصليح" }).click();
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("هذا الإجراء غير ممكن من الحالة الحالية");
    // Its values aren't what stopped this, so nothing points at them.
    await expect(alert).not.toContainText("يرجى التحقق");
    await expect(page.getByRole("button", { name: "بدء التصليح" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "تحديد كجاهز" })).toBeVisible();
  });

  test("the owner can undo an edit, and undoing what's since changed says why it can't be done", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    const first = await add(page.request, "Avant", { price: 1000 });
    expect((await page.request.patch(`${base}/api/e/repairs/${first._id}`, { data: { price: 2000, _version: first._version } })).status()).toBe(200);
    await openRecord(page, first._id);
    const main = page.getByRole("main");
    await expect(fact(page, "السعر")).toContainText("2.000,00");
    // A creation is undone by deleting: its line offers nothing that says otherwise.
    await expect(main.getByRole("button", { name: "إلغاء هذا التعديل" })).toHaveCount(1);

    await main.getByRole("button", { name: "إلغاء هذا التعديل" }).click();
    await expect(fact(page, "السعر")).toContainText("1.000,00");
    await expect(main.getByText("إلغاء تعديل")).toBeVisible();
    await expect(main.getByText("أُلغي", { exact: false }).first()).toBeVisible();
    await expect(main.getByRole("button", { name: "إلغاء هذا التعديل" })).toHaveCount(0);
    await expectGoodScreen(page, "an undone edit");

    const second = await add(page.request, "Deux fois", { price: 1000 });
    const edited = await page.request.patch(`${base}/api/e/repairs/${second._id}`, { data: { price: 2000, _version: second._version } });
    const { _version } = (await edited.json()) as Stored;
    expect((await page.request.patch(`${base}/api/e/repairs/${second._id}`, { data: { price: 3000, _version } })).status()).toBe(200);
    await openRecord(page, second._id);
    await main.getByRole("button", { name: "إلغاء هذا التعديل" }).last().click();
    await expect(page.getByRole("alert")).toContainText("تغيرت هذه القيم");
    await expect(fact(page, "السعر")).toContainText("3.000,00");
    expect(errors).toEqual([]);
  });

  test("deleting asks first, keeps the way back in reach, and restoring brings it all back", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    const { _id } = await add(page.request, "À supprimer", { price: 700 });
    await openRecord(page, _id);

    await page.getByRole("button", { name: "حذف" }).click();
    await expect(page.getByRole("button", { name: "لا، أبقِه" })).toBeFocused();
    await expectGoodScreen(page, "asking before deleting");
    await page.getByRole("button", { name: "لا، أبقِه" }).click();
    await expect(page.getByRole("button", { name: "حذف" })).toBeFocused();
    expect((await page.request.get(`${base}/api/e/repairs/${_id}`)).status()).toBe(200);

    await page.getByRole("button", { name: "حذف" }).click();
    await page.getByRole("button", { name: "نعم، احذف" }).click();
    await expect(page.getByRole("heading", { name: "حُذف هذا العنصر" })).toBeVisible();
    await expect(page.getByRole("main")).toBeFocused();
    expect((await page.request.get(`${base}/api/e/repairs/${_id}`)).status()).toBe(404);
    await expectGoodScreen(page, "a deleted record");

    await page.getByRole("button", { name: "استرجاع" }).click();
    await expect(page.getByRole("heading", { name: "À supprimer", level: 1 })).toBeVisible();
    await expect(page.getByRole("main").getByText("استُرجع")).toBeVisible();
    await expect(fact(page, "السعر")).toContainText("700,00");
    expect((await page.request.get(`${base}/api/e/repairs/${_id}`)).status()).toBe(200);
    expect(errors).toEqual([]);
  });

  test("back returns to the same search and page, and a shared link goes up to the list", async ({ page }) => {
    await signIn(page, base);
    const { _id } = await add(page.request, "Retrouvable");
    await page.goto(`${base}/v/repairs_all?q=Retrouvable`);
    await expect(page.getByRole("searchbox")).toHaveValue("Retrouvable");
    await page.getByRole("main").getByRole("button", { name: /Retrouvable/ }).click();
    await page.getByRole("button", { name: "تعديل", exact: true }).click();
    await expect(page.locator("#field-device")).toHaveValue("Retrouvable");

    // From the form to the record, then from the record to the list, as a person went.
    await page.getByRole("button", { name: "إلغاء" }).click();
    await expect(page.getByRole("heading", { name: "Retrouvable", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "رجوع" }).click();
    await expect(page).toHaveURL(/q=Retrouvable/);
    await expect(page.getByRole("searchbox")).toHaveValue("Retrouvable");

    await openRecord(page, _id);
    await page.getByRole("button", { name: "رجوع" }).click();
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
    await expect(page).not.toHaveURL(/\/e\/repairs\//);
  });

  test("an address with no such record says so", async ({ page }) => {
    await signIn(page, base);
    for (const id of ["0b0c2c5e-1111-4222-8333-444455556666", "pas-un-identifiant"]) {
      await openRecord(page, id);
      await expect(page.getByRole("heading", { name: "الصفحة غير موجودة", level: 1 })).toBeVisible();
    }
  });
});

test.describe.serial("a record for those with fewer rights", () => {
  test.use(PHONE);

  test("someone who may only read gets no buttons, and only hears that a hidden field changed", async ({ page }) => {
    await signIn(page, base);
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "lecteur", password: PASSWORD, role: "viewer" } })).status()).toBe(201);
    const { _id, _version } = await add(page.request, "Marge cachée", { price: 5000, parts_cost: 1200 });
    expect((await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { parts_cost: 1300, _version } })).status()).toBe(200);
    await page.context().clearCookies();
    await signIn(page, base, "lecteur");
    await openRecord(page, _id);

    const main = page.getByRole("main");
    await expect(page.getByRole("heading", { name: "Marge cachée", level: 1 })).toBeVisible();
    await expect(fact(page, "السعر")).toContainText("5.000,00");
    await expect(main.getByText("تغيّر حقل مخفي")).toBeVisible();
    await expect(main).not.toContainText("parts_cost");
    await expect(main).not.toContainText("1.300");
    for (const name of ["تعديل", "حذف", "بدء التصليح", "إلغاء هذا التعديل"]) await expect(page.getByRole("button", { name })).toHaveCount(0);
    await expectGoodScreen(page, "a record for someone who may only read");
  });

  test("staff can move and edit a record, but not delete it or undo a change", async ({ page }) => {
    await signIn(page, base);
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "rafik", password: PASSWORD, role: "staff" } })).status()).toBe(201);
    const { _id, _version } = await add(page.request, "Pour Rafik", { price: 5000 });
    expect((await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { price: 5500, _version } })).status()).toBe(200);
    await page.context().clearCookies();
    await signIn(page, base, "rafik");
    await openRecord(page, _id);
    await expect(page.getByRole("button", { name: "بدء التصليح" })).toBeVisible();
    await expect(page.getByRole("button", { name: "تعديل", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "حذف" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "إلغاء هذا التعديل" })).toHaveCount(0);
  });
});

test.describe("a record on a PC", () => {
  test.use(PC);

  test("sets its values and its history side by side, cleanly in both languages", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    const { _id, _version } = await add(page.request, "Climatiseur mural Condor 12000 BTU Inverter avec télécommande", { price: 42000, problem: "Ne refroidit plus. Le client signale aussi que l’appareil s’éteint seul après quelques minutes de marche." });
    expect((await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { price: 45000, _version } })).status()).toBe(200);
    for (const [lang, step, history] of [["ar", "بدء التصليح", "سجل التعديلات"], ["fr", "Commencer", "Historique"]] as const) {
      await page.goto(`${base}/e/repairs/${_id}?lang=${lang}`);
      await expect(page.getByRole("button", { name: step })).toBeVisible();
      await expect(page.getByRole("heading", { name: history })).toBeVisible();
      const [facts, past] = await Promise.all([page.getByRole("main").locator("dl").first().boundingBox(), page.getByRole("heading", { name: history }).boundingBox()]);
      expect(Math.abs((facts?.y ?? 0) - (past?.y ?? 100))).toBeLessThan(40);
      await expectGoodScreen(page, `${lang} record`);
    }
    expect(errors).toEqual([]);
  });
});
