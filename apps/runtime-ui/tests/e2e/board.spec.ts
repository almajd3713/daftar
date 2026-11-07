/** R-20: a workflow's board. Moving a card only ever asks the server, and a refusal says why, however the move was made. */
import { expect, test, type Locator, type Page } from "@playwright/test";

import { baseOf, expectGoodScreen, PASSWORD, PC, PHONE, signIn, signUp, watchForErrors } from "./helpers.js";

const base = baseOf("board");

interface Stored {
  _id: string;
  _version: number;
}

async function add(page: Page, device: string, extra: object = {}): Promise<Stored> {
  const response = await page.request.post(`${base}/api/e/repairs`, { data: { customer: "حورية سعيدي", received_on: "2026-11-03", device, ...extra } });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as Stored;
}

async function moveTo(page: Page, id: string, ...actions: string[]): Promise<void> {
  for (const action of actions) {
    const response = await page.request.post(`${base}/api/e/repairs/${id}/transition`, { data: { action } });
    expect(response.status(), await response.text()).toBe(200);
  }
}

// A notice is a section with a heading too, and says the state a card moved to.
const column = (page: Page, state: string): Locator => page.locator("section:not([role])", { has: page.getByRole("heading", { name: state, level: 2 }) });
const card = (page: Page, device: string): Locator => page.locator("article", { hasText: device });

test.describe.serial("the board on a PC", () => {
  test.use(PC);

  test("is the page of an entity whose first view it is, and says so when it's empty", async ({ page }) => {
    await signUp(page, base);
    const errors = watchForErrors(page);
    await page.goto(`${base}/?lang=fr`);
    await expect(page.getByRole("heading", { name: "Réparations", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Rien pour l’instant" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Réparations" }).getByRole("button", { name: "Tableau" })).toHaveAttribute("aria-current", "true");
    await expectGoodScreen(page, "an empty board");
    expect(errors).toEqual([]);
  });

  test("shows each state as a column, and each card what the spec lists", async ({ page }) => {
    await signIn(page, base);
    await add(page, "iPhone 11", { promised_on: "2026-12-01" });
    const errors = watchForErrors(page);
    const asked: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/e/repairs?")) asked.push(request.url());
    });
    await page.goto(`${base}/?lang=fr`);
    for (const state of ["Reçu", "En réparation", "Prêt", "Livré"]) await expect(column(page, state)).toBeVisible();
    // Each state once: a column's count has to be its own, and a slow phone shouldn't pay for this twice.
    expect(asked).toHaveLength(4);
    await expect(column(page, "Reçu")).toContainText("1");
    const iphone = column(page, "Reçu").locator("article", { hasText: "iPhone 11" });
    await expect(iphone).toContainText("حورية سعيدي");
    await expect(iphone).toContainText("01/12/2026");
    await expect(iphone).toContainText(/REP-\d+/);
    await expectGoodScreen(page, "a board");

    await iphone.getByRole("button", { name: "iPhone 11" }).click();
    await expect(page).toHaveURL(/\/e\/repairs\/[0-9a-f-]+\?from=repairs_board$/);
    await page.goBack();
    await expect(column(page, "Reçu")).toContainText("iPhone 11");
    expect(errors).toEqual([]);
  });

  test("moves a card with its button, says so, and keeps the person with the card", async ({ page }) => {
    await signIn(page, base);
    await add(page, "Bouton");
    const errors = watchForErrors(page);
    await page.goto(`${base}/?lang=fr`);
    await card(page, "Bouton").getByRole("button", { name: "Commencer" }).click();
    await expect(column(page, "En réparation").locator("article", { hasText: "Bouton" })).toBeVisible();
    await expect(page.getByRole("status")).toContainText("En réparation");
    await expect(card(page, "Bouton").getByRole("button", { name: "Bouton" })).toBeFocused();
    await page.reload();
    await expect(column(page, "En réparation").locator("article", { hasText: "Bouton" })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("moves a card by dragging it to a column", async ({ page }) => {
    await signIn(page, base);
    await add(page, "Glissé");
    await page.goto(`${base}/?lang=fr`);
    await card(page, "Glissé").dragTo(column(page, "En réparation"));
    await expect(column(page, "En réparation").locator("article", { hasText: "Glissé" })).toBeVisible();
    await expect(column(page, "Reçu").locator("article", { hasText: "Glissé" })).toHaveCount(0);
  });

  test("does nothing when a card is dropped back on its own column", async ({ page }) => {
    await signIn(page, base);
    await add(page, "Sur place");
    await page.goto(`${base}/?lang=fr`);
    let asked = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/transition")) asked += 1;
    });
    await card(page, "Sur place").dragTo(column(page, "Reçu"), { targetPosition: { x: 20, y: 10 } });
    await expect(card(page, "Sur place").getByRole("status")).toHaveCount(0);
    expect(asked).toBe(0);
  });

  test("explains a refused drag, names where to look, keeps the card, and clears once it goes through", async ({ page }) => {
    await signIn(page, base);
    const { _id, _version } = await add(page, "Sans prix");
    await moveTo(page, _id, "start_repair");
    await page.goto(`${base}/?lang=fr`);
    await card(page, "Sans prix").dragTo(column(page, "Prêt"));
    const refusal = card(page, "Sans prix").getByRole("status");
    await expect(refusal).toContainText("Marquer prêt");
    await expect(refusal).toContainText("Prix");
    await expect(column(page, "En réparation").locator("article", { hasText: "Sans prix" })).toBeVisible();
    await expectGoodScreen(page, "a refused move");

    const fixed = await page.request.patch(`${base}/api/e/repairs/${_id}`, { data: { price: 5000, _version: _version + 1 } });
    expect(fixed.status(), await fixed.text()).toBe(200);
    await card(page, "Sans prix").getByRole("button", { name: "Marquer prêt" }).click();
    await expect(column(page, "Prêt").locator("article", { hasText: "Sans prix" })).toBeVisible();
    await expect(card(page, "Sans prix").getByRole("status")).toHaveCount(0);
  });

  test("explains a drag to where no step leads, without asking the server, and says where it can go", async ({ page }) => {
    await signIn(page, base);
    await add(page, "Trop loin");
    await page.goto(`${base}/?lang=fr`);
    let asked = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/transition")) asked += 1;
    });
    await card(page, "Trop loin").dragTo(column(page, "Livré"));
    const refusal = card(page, "Trop loin").getByRole("status");
    await expect(refusal).toContainText("Aucune étape");
    await expect(refusal).toContainText("En réparation");
    await expect(column(page, "Reçu").locator("article", { hasText: "Trop loin" })).toBeVisible();
    expect(asked).toBe(0);
  });

  test("says when the server can't be reached, and leaves the card where it was", async ({ page }) => {
    await signIn(page, base);
    await add(page, "Hors ligne");
    await page.goto(`${base}/?lang=fr`);
    await page.route("**/transition", (route) => route.abort());
    await card(page, "Hors ligne").getByRole("button", { name: "Commencer" }).click();
    await expect(page.getByRole("alert")).toContainText("Le serveur ne répond pas");
    await expect(column(page, "Reçu").locator("article", { hasText: "Hors ligne" })).toBeVisible();
  });

  test("has its entity's other views beside it as tabs", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/?lang=fr`);
    const tabs = page.getByRole("navigation", { name: "Réparations" });
    await tabs.getByRole("button", { name: "Toutes les réparations" }).click();
    await expect(page).toHaveURL(/\/v\/repairs_all$/);
    await expect(page.locator("tbody tr").first()).toBeVisible();
    await tabs.getByRole("button", { name: "Tableau" }).click();
    await expect(page).toHaveURL(/\/v\/repairs_board$/);
    await expect(column(page, "Reçu")).toBeVisible();
  });

  test("offers someone who may only read neither a button nor a drag", async ({ page }) => {
    await signIn(page, base);
    expect((await page.request.post(`${base}/api/auth/users`, { data: { username: "lecteur", password: PASSWORD, role: "viewer" } })).status()).toBe(201);
    await page.context().clearCookies();
    await signIn(page, base, "lecteur");
    await page.goto(`${base}/?lang=fr`);
    const iphone = card(page, "iPhone 11");
    await expect(iphone).toBeVisible();
    await expect(iphone.getByRole("button", { name: "Commencer" })).toHaveCount(0);
    await expect(iphone).not.toHaveAttribute("draggable", "true");
    await expect(page.getByRole("button", { name: "Ajouter" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Éléments supprimés" })).toHaveCount(0);
  });

  test("shows the first of a long column, its true count, and the way to the rest", async ({ page }) => {
    await signIn(page, base);
    const before = ((await (await page.request.get(`${base}/api/e/repairs?filter.status.eq=received&pageSize=1`)).json()) as { total: number }).total;
    for (let index = before; index < 51; index += 1) await add(page, `Lot ${index}`);
    await page.goto(`${base}/?lang=fr`);
    const received = column(page, "Reçu");
    await expect(received.locator("article")).toHaveCount(50);
    await expect(received).toContainText("51");
    // A working state is the queue to work through, so its oldest come first.
    await expect(received.locator("article").first()).toContainText("iPhone 11");
    await received.getByRole("button", { name: "Tout voir (51)" }).click();
    await expect(page).toHaveURL(/\/v\/repairs_all$/);
  });

  test("shows a job just finished at the top of a long end state, rather than losing it past the first page", async ({ page }) => {
    await signIn(page, base);
    for (let index = 0; index < 51; index += 1) {
      const { _id } = await add(page, `Ancien ${index}`, { price: 100 });
      await moveTo(page, _id, "start_repair", "mark_ready", "deliver");
    }
    const { _id } = await add(page, "Tout juste fini", { price: 100 });
    await moveTo(page, _id, "start_repair", "mark_ready");
    await page.goto(`${base}/?lang=fr`);
    const delivered = column(page, "Livré");
    await expect(delivered.locator("article")).toHaveCount(50);

    await card(page, "Tout juste fini").getByRole("button", { name: "Livrer" }).click();
    await expect(delivered.locator("article").first()).toContainText("Tout juste fini");
    await expect(page.getByRole("status")).toContainText("Tout juste fini");
    await expect(card(page, "Tout juste fini").getByRole("button", { name: "Tout juste fini" })).toBeFocused();
    await expect(delivered).toContainText("52");
    await expect(delivered.locator("article")).toHaveCount(50);
  });
});

test.describe.serial("the board on a phone", () => {
  test.use(PHONE);

  test("shows one state at a time, keeps it in the address, and moves a card on with its button", async ({ page }) => {
    await signIn(page, base);
    const { _id } = await add(page, "Téléphone rouge");
    await moveTo(page, _id, "start_repair");
    const errors = watchForErrors(page);
    await page.goto(`${base}/v/repairs_board?lang=ar&state=in_repair`);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    const tabs = page.getByRole("navigation", { name: "التصليحات" });
    await expect(tabs.getByRole("button", { name: /قيد التصليح/ })).toHaveAttribute("aria-current", "true");
    await expect(card(page, "Téléphone rouge")).toBeVisible();
    await expect(page.getByRole("button", { name: "إضافة" })).toBeVisible();
    await expect(card(page, "Téléphone rouge")).not.toHaveAttribute("draggable", "true");
    await expectGoodScreen(page, "a board on a phone, in Arabic");

    await page.reload();
    await expect(tabs.getByRole("button", { name: /قيد التصليح/ })).toHaveAttribute("aria-current", "true");

    // It has no price, so this is the refusal, on a phone.
    await card(page, "Téléphone rouge").getByRole("button", { name: "تحديد كجاهز" }).click();
    await expect(card(page, "Téléphone rouge").getByRole("status")).toContainText("السعر");
    await expectGoodScreen(page, "a refused move on a phone");

    await page.goto(`${base}/v/repairs_board?lang=ar&state=received`);
    await expect(tabs.getByRole("button", { name: /مستلم/ })).toHaveAttribute("aria-current", "true");
    const first = page.locator("article").first();
    const title = (await first.getByRole("button").first().textContent()) ?? "";
    await first.getByRole("button", { name: "بدء التصليح" }).click();
    // The card has left this tab, so the page says where it went, and focus has somewhere to be.
    await expect(page.getByRole("status")).toContainText("قيد التصليح");
    await expect(page.getByRole("main")).toBeFocused();
    await expect(page.locator("article", { hasText: title })).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("opens on the first state with something in it, and reaches the entity's other views", async ({ page }) => {
    await signIn(page, base);
    await page.goto(`${base}/?lang=fr`);
    const tabs = page.getByRole("navigation", { name: "Réparations" });
    await expect(tabs.getByRole("button", { name: /Reçu/ })).toHaveAttribute("aria-current", "true");
    await tabs.getByRole("button", { name: "Toutes les réparations" }).click();
    await expect(page).toHaveURL(/\/v\/repairs_all$/);
    await tabs.getByRole("button", { name: "Tableau" }).click();
    await expect(page).toHaveURL(/\/v\/repairs_board$/);
    await expect(page.locator("article").first()).toBeVisible();
  });

  test("says so when a state is empty", async ({ page }) => {
    await signIn(page, base);
    const delivered = await page.request.get(`${base}/api/e/repairs?filter.status.eq=delivered&pageSize=500`);
    for (const { _id } of ((await delivered.json()) as { rows: Stored[] }).rows) {
      expect((await page.request.delete(`${base}/api/e/repairs/${_id}`)).status()).toBe(204);
    }
    await page.goto(`${base}/v/repairs_board?lang=fr&state=delivered`);
    await expect(page.getByRole("heading", { name: "Rien dans cet état." })).toBeVisible();
    await expectGoodScreen(page, "an empty state on a phone");
  });
});
