/** The Studio's preview, on its real server: nobody knows its owner's password, so login would be a dead end. */
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import { expect, test } from "@playwright/test";

import { expectGoodScreen, PC, PREVIEW_ENV } from "./helpers.js";

const { port, cookie } = JSON.parse(process.env[PREVIEW_ENV] ?? "{}") as { port: number; cookie: string };
const base = `http://127.0.0.1:${port}`;
const [name = "", value = ""] = (cookie ?? "").split("=");

test.describe("a preview", () => {
  test.use(PC);

  test("signed in by the Studio, shows the app in the language the Studio asked for", async ({ page, context }) => {
    await context.addCookies([{ name, value, url: base }]);
    await page.goto(`${base}/?lang=ar`);
    await expect(page.getByRole("heading", { name: "التصليحات", level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.dir)).toBe("rtl");
    await expect(page).not.toHaveURL(/lang=/);
    await page.goto(`${base}/?lang=fr`);
    await expect(page.getByRole("heading", { name: "Réparations", level: 1 })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.dir)).toBe("ltr");
  });

  test("with no session, says to reopen it from the Studio instead of offering a login nobody can use", async ({ page }) => {
    await page.goto(`${base}/?lang=fr`);
    await expect(page.getByRole("heading", { name: "Cet aperçu a été fermé" })).toBeVisible();
    await expect(page.getByLabel("Mot de passe")).toHaveCount(0);
    await expectGoodScreen(page, "preview ended");
  });

  test("can be shown inside the Studio's page, at a phone's width, and takes the phone layout", async ({ page, context }) => {
    await context.addCookies([{ name, value, url: base, sameSite: "Lax", httpOnly: true }]);
    // A real server on the Studio's kind of address. Same host makes the cookie same-site, and a loopback page is
    // what Chromium's Local Network Access check lets frame another loopback address: a faked page gets blocked.
    const studio = createServer((_request, response) => {
      response.setHeader("Content-Type", "text/html");
      response.end(`<!doctype html><iframe id="preview" src="${base}/?lang=fr" width="360" height="680"></iframe>`);
    });
    await new Promise<void>((resolve) => studio.listen(0, "127.0.0.1", resolve));
    try {
      await page.goto(`http://127.0.0.1:${(studio.address() as AddressInfo).port}/`);
      const frame = page.frameLocator("#preview");
      await expect(frame.getByRole("heading", { name: "Réparations", level: 1 })).toBeVisible();
      await expect(frame.locator("[data-layout]").first()).toHaveAttribute("data-layout", "narrow");
    } finally {
      studio.closeAllConnections();
      studio.close();
    }
  });
});
