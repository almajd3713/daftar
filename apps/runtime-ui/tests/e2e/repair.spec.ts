/** The thin path, on a phone, in Arabic, as this app's owner would first meet it: a tracker whose default language is Arabic. */
import { expect, test } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, watchForErrors } from "./helpers.js";

const base = baseOf("repair");

test.describe.serial("the repair tracker", () => {
  test.use(PHONE);

  test("first start asks for an owner, and refuses a short password in the server's words", async ({ page }) => {
    const errors = watchForErrors(page);
    await page.goto(base);
    await expect(page.getByRole("heading", { name: "إنشاء حساب المالك" })).toBeVisible();
    expect(await page.evaluate(() => [document.documentElement.lang, document.documentElement.dir])).toEqual(["ar-DZ", "rtl"]);
    await expectGoodScreen(page, "setup");

    await page.locator("#username").fill("samira");
    await page.locator("#password").fill("court");
    await page.getByRole("button", { name: "إنشاء الحساب" }).click();
    const summary = page.getByRole("alert");
    await expect(summary).toBeVisible();
    await expect(summary).toBeFocused();
    await expect(summary.getByRole("link")).toHaveAttribute("href", "#password");
    await expectGoodScreen(page, "setup with an error");

    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: "إنشاء الحساب" }).click();
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "لا شيء بعد" })).toBeVisible();
    await expectGoodScreen(page, "empty list");
    expect(errors).toEqual([]);
  });

  test("a form shows the server's refusals, and saves what a person typed in their own habits", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    await page.goto(base);
    await page.getByRole("button", { name: "إضافة" }).click();
    await expect(page.getByRole("heading", { name: "بطاقة التصليح" })).toBeVisible();
    await expect(page).toHaveURL(/\/e\/repairs\/new/);
    await expectGoodScreen(page, "new form");

    // The pinned button is outside the form, so this also proves it submits.
    await page.getByRole("button", { name: "حفظ" }).click();
    const summary = page.getByRole("alert");
    await expect(summary).toBeFocused();
    await expect(summary).toContainText("هذا الحقل إجباري");
    // Each line names its field: three "this field is required" would tell nobody what to fix.
    const customer = summary.getByRole("link", { name: /الزبون.*هذا الحقل إجباري/ });
    await expect(customer).toHaveAttribute("href", "#field-customer");
    await customer.click();
    await expect(page.locator("#field-customer")).toBeFocused();

    await page.locator("#field-customer").fill("حورية سعيدي");
    await page.locator("#field-customer_phone").fill("055 12");
    await page.locator("#field-device").fill("Samsung A15");
    await page.locator("#field-problem").fill("Écran cassé");
    await page.locator("#field-received_on").fill("٠٣/١١/٢٠٢٦");
    await page.locator("#field-received_on").press("Tab");
    await page.keyboard.press("Escape");
    await page.locator("#field-price").fill("9.800,50");
    await page.getByRole("button", { name: "حفظ" }).click();
    await expect(page.getByRole("alert")).toContainText("أدخل رقم هاتف جزائري");
    await expect(page.locator("#field-customer_phone")).toHaveAttribute("aria-invalid", "true");
    await expectGoodScreen(page, "form with an error");

    await page.locator("#field-customer_phone").fill("0550 12 34 56");
    await page.getByRole("button", { name: "حفظ" }).click();
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
    const row = page.getByRole("main").getByRole("button", { name: /Samsung A15/ });
    await expect(row).toContainText("9.800,50");
    await expect(row).toContainText("REP-");
    await expect(page.getByRole("contentinfo")).toContainText("9.800,50");
    await expectGoodScreen(page, "list");

    const stored = await (await page.request.get(`${base}/api/e/repairs`)).json();
    expect(stored.rows[0]).toMatchObject({ customer: "حورية سعيدي", device: "Samsung A15", customer_phone: "0550123456", received_on: "2026-11-03", price: 9800.5, status: "received" });
    expect(errors).toEqual([]);
  });

  test("an edit sends only what changed, and a stale one says so rather than overwriting", async ({ page }) => {
    await signIn(page, base);
    await page.goto(base);
    await page.getByRole("main").getByRole("button", { name: /Samsung A15/ }).click();
    await expect(page.locator("#field-device")).toHaveValue("Samsung A15");
    await expect(page.locator("#field-price")).toHaveValue("9.800,50");
    await expect(page.locator("#field-received_on")).toHaveValue("03/11/2026");

    const sent: unknown[] = [];
    page.on("request", (request) => {
      if (request.method() === "PATCH") sent.push(request.postDataJSON());
    });

    // Someone else saves while this form is open.
    const list = await (await page.request.get(`${base}/api/e/repairs`)).json();
    const { _id, _version } = list.rows[0];
    expect((await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { problem: "Écran et batterie", _version } })).status()).toBe(200);

    await page.locator("#field-device").fill("Samsung A16");
    await page.getByRole("button", { name: "حفظ" }).click();
    await expect(page.getByRole("alert")).toContainText("لم يتم الحفظ");
    await expect(page).toHaveURL(/\/edit/);
    expect(sent).toEqual([{ device: "Samsung A16", _version }]);
    const after = await (await page.request.get(`${base}/api/e/repairs/${_id}`)).json();
    expect(after).toMatchObject({ device: "Samsung A15", problem: "Écran et batterie" });

    // The fresh copy loads, and the same change now goes through.
    await page.reload();
    await expect(page.locator("#field-problem")).toHaveValue("Écran et batterie");
    await page.locator("#field-device").fill("Samsung A16");
    await page.getByRole("button", { name: "حفظ" }).click();
    await expect(page.getByRole("main").getByRole("button", { name: /Samsung A16/ })).toBeVisible();
  });

  test("losing the session goes to login, and signing in lands back on the same page", async ({ page, context }) => {
    await signIn(page, base);
    const list = await (await page.request.get(`${base}/api/e/repairs`)).json();
    const editPath = `/e/repairs/${list.rows[0]._id}/edit`;
    await page.goto(`${base}${editPath}`);
    await expect(page.locator("#field-device")).toHaveValue("Samsung A16");

    await context.clearCookies();
    await page.reload();
    await expect(page.getByRole("heading", { name: "تسجيل الدخول" })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(editPath));
    await expectGoodScreen(page, "login");

    await page.locator("#username").fill("samira");
    await page.locator("#password").fill("pas-le-bon-mot-de-passe");
    await page.getByRole("button", { name: "دخول" }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expectGoodScreen(page, "login refused");

    await page.locator("#password").fill(PASSWORD);
    await page.getByRole("button", { name: "دخول" }).click();
    await expect(page.locator("#field-device")).toHaveValue("Samsung A16");
    await expect(page).toHaveURL(new RegExp(editPath));
  });

  test("a call that finds the session gone mid-use also goes to login", async ({ page, context }) => {
    await signIn(page, base);
    await page.goto(base);
    await expect(page.getByRole("main").getByRole("button", { name: /Samsung A16/ })).toBeVisible();
    await context.clearCookies();
    await page.getByRole("main").getByRole("button", { name: /Samsung A16/ }).click();
    await expect(page.getByRole("heading", { name: "تسجيل الدخول" })).toBeVisible();
    await expect(page).toHaveURL(/\/edit/);
  });

  test("More holds the language and signing out, and the language sticks", async ({ page }) => {
    await signIn(page, base);
    await page.goto(base);
    await page.getByRole("navigation", { name: "القائمة" }).getByRole("button", { name: "المزيد" }).click();
    await expect(page).toHaveURL(/\/more$/);
    await expectGoodScreen(page, "more");
    await page.getByRole("button", { name: /اللغة/ }).click();
    expect(await page.evaluate(() => [document.documentElement.lang, document.documentElement.dir])).toEqual(["fr-DZ", "ltr"]);
    await page.getByRole("navigation", { name: "Menu" }).getByRole("button", { name: "Réparations" }).click();
    await expect(page.getByRole("heading", { name: "Réparations", level: 1 })).toBeVisible();
    await expect(page.getByRole("main").getByRole("button", { name: /Samsung A16/ })).toContainText("9\u00a0800,50");
    await expectGoodScreen(page, "list in French");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Réparations", level: 1 })).toBeVisible();

    await page.getByRole("button", { name: "Plus" }).click();
    await page.getByRole("button", { name: "Se déconnecter" }).click();
    await expect(page.getByRole("heading", { name: "Se connecter" })).toBeVisible();
    expect((await page.request.get(`${base}/api/auth/me`)).status()).toBe(401);
  });

  test("an address that doesn't exist says so, and offers the way home", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/v/nothing_here`);
    await expect(page.getByRole("heading", { name: "الصفحة غير موجودة", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "العودة إلى الرئيسية" }).click();
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
  });
});

test.describe.serial("the repair tracker across the phone layout's edge", () => {
  test.use(PHONE);

  test("opening a page mounts it once, so it asks for its data once", async ({ page }) => {
    await signIn(page, base);
    const asked: string[] = [];
    const dropped: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/e/repairs?")) asked.push(request.url());
    });
    page.on("requestfailed", (request) => dropped.push(request.url()));
    await page.goto(base);
    await expect(page.getByRole("main").getByRole("button", { name: /Samsung A16/ })).toBeVisible();
    expect(asked).toHaveLength(1);
    expect(dropped).toEqual([]);
  });

  test("turning a phone or resizing a window keeps what's been typed, and the field's focus", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/e/repairs/new`);
    await page.locator("#field-device").fill("Lave-linge");
    await page.locator("#field-customer").fill("Haddad Lynda");
    await page.locator("#field-price").fill("1.250,00");
    await page.locator("#field-problem").focus();
    await expect(page.locator("[data-layout]").first()).toHaveAttribute("data-layout", "narrow");

    await page.setViewportSize({ width: 1024, height: 680 });
    await expect(page.locator("[data-layout]").first()).toHaveAttribute("data-layout", "wide");
    await expect(page.locator("#field-device")).toHaveValue("Lave-linge");
    await expect(page.locator("#field-customer")).toHaveValue("Haddad Lynda");
    await expect(page.locator("#field-price")).toHaveValue("1.250,00");
    await expect(page.locator("#field-problem")).toBeFocused();

    await page.setViewportSize({ width: 360, height: 680 });
    await expect(page.locator("[data-layout]").first()).toHaveAttribute("data-layout", "narrow");
    await expect(page.locator("#field-device")).toHaveValue("Lave-linge");
    await expect(page.locator("#field-problem")).toBeFocused();
  });
});

test.describe.serial("the repair tracker for someone who may only read", () => {
  test.use(PHONE);

  test("offers no way to add or edit, and doesn't show what's hidden from them", async ({ page }) => {
    await signIn(page, base);
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "lecteur", password: PASSWORD, role: "viewer" } })).status()).toBe(201);
    await page.context().clearCookies();
    await signIn(page, base, "lecteur");
    await page.goto(base);
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
    await expect(page.getByRole("main").getByRole("button", { name: /Samsung A16/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "إضافة" })).toHaveCount(0);
    await page.getByRole("main").getByRole("button", { name: /Samsung A16/ }).click();
    await expect(page).not.toHaveURL(/\/edit/);
    await page.goto(`${base}/e/repairs/new`);
    await expect(page.getByRole("heading", { name: "الصفحة غير موجودة", level: 1 })).toBeVisible();
  });
});

test.describe("the repair tracker on a PC", () => {
  test.use(PC);

  test("shows a ledger table with its total, and its form, cleanly in both languages", async ({ page }) => {
    const errors = watchForErrors(page);
    await signIn(page, base);
    for (const [lang, title, form, add] of [["ar", "التصليحات", "بطاقة التصليح", "إضافة"], ["fr", "Réparations", "Fiche de réparation", "Ajouter"]] as const) {
      await page.goto(`${base}/?lang=${lang}`);
      await expect(page).not.toHaveURL(/lang=/);
      await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
      await expect(page.locator("tbody tr")).toHaveCount(1);
      expect(await page.locator("tfoot td").last().evaluate((cell) => getComputedStyle(cell).borderBottomStyle)).toBe("double");
      await expectGoodScreen(page, `${lang} list`);
      await page.getByRole("button", { name: add }).click();
      await expect(page.getByRole("heading", { name: form })).toBeVisible();
      await expectGoodScreen(page, `${lang} form`);
    }
    expect(errors).toEqual([]);
  });
});
