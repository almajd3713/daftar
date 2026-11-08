/**
 * Everything about the design system that can be measured: every screen, in both languages and themes, with
 * normal and awkward data, at phone and PC size. A person still has to look; this catches what they'd miss.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

import { expectClean, measure } from "./measure.js";

const SCREENS = ["list", "empty", "form", "board", "record", "calc", "dash", "projects", "review", "report", "setup", "menu"] as const;
// The Studio is one operator at a PC. The phone's menu page only exists on a phone.
const PHONE_SCREENS = SCREENS.filter((screen) => !["projects", "review", "report"].includes(screen));
const PC_SCREENS = SCREENS.filter((screen) => screen !== "menu");
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

async function open(page: Page, screen: string, lang: string, mode: string, data: string): Promise<void> {
  await page.goto(`/?bare=1&screen=${screen}&lang=${lang}&mode=${mode}&data=${data}`);
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator("#main, main").first()).toBeVisible();
}

const WIDTHS = {
  phone: { viewport: { width: 360, height: 680 }, hasTouch: true, isMobile: true, screens: PHONE_SCREENS },
  pc: { viewport: { width: 1280, height: 800 }, hasTouch: false, isMobile: false, screens: PC_SCREENS },
} as const;

for (const [device, config] of Object.entries(WIDTHS)) {
  test.describe(device, () => {
    test.use({ viewport: config.viewport, hasTouch: config.hasTouch, isMobile: config.isMobile });
    for (const screen of config.screens) {
      for (const lang of ["ar", "fr"]) {
        test(`${screen} in ${lang}: measures clean in every theme, with any data`, async ({ page }) => {
          const errors: string[] = [];
          page.on("pageerror", (error) => errors.push(error.message));
          page.on("console", (message) => {
            if (message.type() === "error") errors.push(message.text());
          });
          for (const mode of ["light", "dark"]) {
            for (const data of ["normal", "awkward"]) {
              await open(page, screen, lang, mode, data);
              expectClean(await page.evaluate(measure));
            }
          }
          expect(errors).toEqual([]);
        });

        test(`${screen} in ${lang}: passes axe in every theme, with any data`, async ({ page }) => {
          for (const mode of ["light", "dark"]) {
            for (const data of ["normal", "awkward"]) {
              await open(page, screen, lang, mode, data);
              const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
              expect(results.violations.map((violation) => `${mode} ${data} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
            }
          }
        });
      }
    }
  });
}

test.describe("phone, under pressure", () => {
  test.use({ viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true });
  for (const screen of PHONE_SCREENS) {
    test(`${screen} doesn't overflow at 320 px or at a larger text size`, async ({ page }) => {
      for (const lang of ["ar", "fr"]) {
        for (const data of ["normal", "awkward"]) {
          for (const scale of ["100%", "150%"]) {
            await open(page, screen, lang, "light", data);
            await page.evaluate((size) => {
              document.documentElement.style.fontSize = size;
            }, scale);
            const { overflow, culprits } = await page.evaluate(() => {
              const main = document.querySelector("main");
              const width = document.documentElement.clientWidth;
              const beyond = (box: DOMRect): boolean => box.width > 0 && (box.right > width + 1 || box.left < -1);
              const wide = [...document.querySelectorAll("body *")].filter((element) => beyond(element.getBoundingClientRect()) && !element.closest("[class*=visuallyHidden]"));
              // A long word can spill out of a box that itself fits, so check the text too.
              const texts: string[] = [];
              const walker = document.createTreeWalker(main ?? document.body, NodeFilter.SHOW_TEXT);
              for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                const range = document.createRange();
                range.selectNodeContents(node);
                if (beyond(range.getBoundingClientRect())) texts.push(`"${(node.textContent ?? "").slice(0, 30)}"`);
              }
              return {
                overflow: Math.max(document.documentElement.scrollWidth - width, main ? main.scrollWidth - main.clientWidth : 0),
                culprits: [
                  `page ${document.documentElement.scrollWidth}/${width}, main ${main?.scrollWidth}/${main?.clientWidth}`,
                  ...wide.slice(0, 6).map((element) => `${element.tagName} ${String(element.className).slice(0, 40)}`),
                  ...texts.slice(0, 6),
                ],
              };
            });
            expect(overflow, `${lang} ${data} ${scale}: ${culprits.join(", ")}`).toBeLessThanOrEqual(1);
          }
        }
      }
    });
  }
});

test.describe("what the design promises", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("paints with the embedded fonts, and never a system font", async ({ page }) => {
    const cdp = await page.context().newCDPSession(page);
    for (const lang of ["ar", "fr"]) {
      await open(page, "list", lang, "light", "normal");
      await cdp.send("DOM.enable");
      await cdp.send("CSS.enable");
      const { root } = await cdp.send("DOM.getDocument", { depth: 0 });
      for (const selector of ["h1", "td[class*=numeric] bdi", "tbody tr:nth-child(1) td:nth-child(2) bdi", "tbody tr:nth-child(2) td:nth-child(2) bdi"]) {
        const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
        const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
        for (const font of fonts) expect(font.isCustomFont, `${lang} ${selector} ${font.familyName}`).toBe(true);
      }
    }
  });

  test("flips direction with the language, and offers the other language in that language", async ({ page }) => {
    await open(page, "list", "ar", "light", "normal");
    expect(await page.evaluate(() => [document.documentElement.dir, document.documentElement.lang])).toEqual(["rtl", "ar-DZ"]);
    await page.getByRole("button", { name: "Français" }).click();
    expect(await page.evaluate(() => [document.documentElement.dir, document.documentElement.lang])).toEqual(["ltr", "fr-DZ"]);
    await page.getByRole("button", { name: "العربية" }).click();
    expect(await page.evaluate(() => document.documentElement.dir)).toBe("rtl");
  });

  test("keeps rows the same height in both languages, so a switch doesn't move the layout", async ({ page }) => {
    const heights: number[] = [];
    for (const lang of ["ar", "fr"]) {
      await open(page, "list", lang, "light", "normal");
      heights.push(await page.locator("tbody tr").first().evaluate((row) => row.getBoundingClientRect().height));
    }
    expect(heights[0]).toBe(heights[1]);
    expect(heights[0]).toBeCloseTo(40, 0);
  });

  test("aligns amounts by place value in both directions", async ({ page }) => {
    for (const lang of ["ar", "fr"]) {
      await open(page, "list", lang, "light", "normal");
      const rights = await page.locator("tbody td[class*=numeric]:nth-child(4) bdi").evaluateAll((cells) => cells.map((cell) => Math.round(cell.getBoundingClientRect().right)));
      expect(new Set(rights).size, lang).toBe(1);
    }
  });

  test("gives an input's border 3:1 against the page, which axe doesn't check", async ({ page }) => {
    for (const mode of ["light", "dark"]) {
      await open(page, "form", "fr", mode, "normal");
      const contrast = await page.locator("#customer").evaluate((input) => {
        const channels = (color: string): number[] => (/rgba?\(([^)]+)\)/.exec(color)?.[1] ?? "0 0 0").split(/[ ,/]+/).map(Number);
        const lum = (color: string): number => {
          const [r = 0, g = 0, b = 0] = channels(color).map((value) => {
            const v = value / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
          return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const [high = 0, low = 0] = [lum(getComputedStyle(input).borderTopColor), lum(getComputedStyle(document.body).backgroundColor)].sort((x, y) => y - x);
        return (high + 0.05) / (low + 0.05);
      });
      expect(contrast, mode).toBeGreaterThanOrEqual(3);
    }
  });

  test("keeps a form's fields in one gutter on a phone, wherever the form sits", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 680 });
    for (const [screen, id] of [["form", "customer"], ["calc", "subjects"], ["setup", "username"]] as const) {
      await open(page, screen, "fr", "light", "normal");
      expect(await page.locator(`#${id}`).evaluate((input) => Math.round(input.getBoundingClientRect().left)), screen).toBe(16);
    }
  });

  test("closes a total with a double rule", async ({ page }) => {
    await open(page, "list", "fr", "light", "normal");
    expect(await page.locator("tfoot td").first().evaluate((cell) => getComputedStyle(cell).borderBottomStyle)).toBe("double");
  });

  test("shows a zero as a dash, and a screen reader still gets the number", async ({ page }) => {
    await open(page, "list", "fr", "light", "normal");
    const zero = page.locator("tbody tr").first().locator("td").nth(5).locator("[role=img]");
    await expect(zero).toHaveText("–");
    await expect(zero).toHaveAttribute("aria-label", "0,00");
  });

  test("puts a field's error between its label and its input", async ({ page }) => {
    await open(page, "form", "fr", "light", "normal");
    const order = await page.locator(".mantine-InputWrapper-root:has(#phone)").evaluate((wrapper) => {
      const top = (selector: string): number => wrapper.querySelector(selector)?.getBoundingClientRect().top ?? -1;
      return [top("label"), top(".mantine-InputWrapper-error"), top("input")];
    });
    expect(order).toEqual([...order].sort((a, b) => a - b));
    await expect(page.getByRole("alert").getByRole("link")).toHaveAttribute("href", "#phone");
  });

  test("keeps a number's digits left to right inside an Arabic form", async ({ page }) => {
    await open(page, "form", "ar", "light", "normal");
    expect(await page.locator("#price").evaluate((input) => getComputedStyle(input).direction)).toBe("ltr");
    expect(await page.locator("#phone").evaluate((input) => [getComputedStyle(input).direction, getComputedStyle(input).textAlign])).toEqual(["ltr", "left"]);
  });

  test("starts the calendar on Saturday and names Algerian months", async ({ page }) => {
    await open(page, "form", "ar", "light", "normal");
    await page.locator("#received").click();
    const dropdown = page.locator(".mantine-Popover-dropdown");
    await expect(dropdown).toBeVisible();
    await expect(dropdown).toContainText("نوفمبر");
    // Saturday's short name, ahead of Sunday's.
    expect(await dropdown.locator("thead").first().textContent()).toMatch(/^\s*سب\s*أح/);
  });
});

async function openCalendar(page: Page): Promise<Locator> {
  await page.locator("#received").click();
  const dropdown = page.locator(".mantine-Popover-dropdown");
  await expect(dropdown).toBeVisible();
  // It fades in, and visible is true from the start. Part way through, axe reads its muted text as too faint.
  await expect(dropdown).toHaveCSS("opacity", "1");
  return dropdown;
}

// It floats outside the frame, so nothing above reaches it unless it's open.
for (const [device, config] of Object.entries(WIDTHS)) {
  test.describe(`the open calendar on a ${device}`, () => {
    test.use({ viewport: config.viewport, hasTouch: config.hasTouch, isMobile: config.isMobile });
    for (const lang of ["ar", "fr"]) {
      test(`in ${lang}: measures clean and passes axe on days, months and years`, async ({ page }) => {
        for (const mode of ["light", "dark"]) {
          await open(page, "form", lang, mode, "normal");
          const dropdown = await openCalendar(page);
          for (const control of [".mantine-DateInput-day", ".mantine-DateInput-monthsListControl", ".mantine-DateInput-yearsListControl"]) {
            if (!control.endsWith("-day")) await dropdown.locator(".mantine-DateInput-calendarHeaderLevel").click();
            await expect(dropdown.locator(control).first()).toBeVisible();
            expectClean(await page.evaluate(measure));
            const results = await new AxeBuilder({ page }).include(".mantine-Popover-dropdown").withTags(AXE_TAGS).analyze();
            expect(results.violations.map((violation) => `${mode} ${control} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
          }
        }
      });
    }
  });
}

test.describe("the open calendar", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("keeps a weekend in ink, because red means late", async ({ page }) => {
    for (const mode of ["light", "dark"]) {
      await open(page, "form", "ar", mode, "normal");
      const dropdown = await openCalendar(page);
      const [weekend, ink] = await dropdown.locator("button[data-weekend]:not([data-outside], [data-selected])").first().evaluate((day) => [getComputedStyle(day).color, getComputedStyle(document.body).color]);
      expect(weekend, mode).toBe(ink);
    }
  });

  test("names its arrows in the page's language, and points them the way time reads", async ({ page }) => {
    for (const [lang, previous, next] of [["fr", "Mois précédent", "Mois suivant"], ["ar", "الشهر السابق", "الشهر التالي"]] as const) {
      await open(page, "form", lang, "light", "normal");
      const dropdown = await openCalendar(page);
      const before = await dropdown.getByRole("button", { name: previous }).boundingBox();
      const after = await dropdown.getByRole("button", { name: next }).boundingBox();
      if (!before || !after) throw new Error("the calendar has no arrows");
      expect(lang === "ar" ? before.x > after.x : before.x < after.x, lang).toBe(true);
    }
  });
});

test.describe("the open calendar, under pressure", () => {
  test.use({ viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true });

  test("fits a 320 px phone at a larger text size, with full-height targets", async ({ page }) => {
    for (const lang of ["ar", "fr"]) {
      for (const scale of ["100%", "150%"]) {
        await open(page, "form", lang, "light", "normal");
        await page.evaluate((size) => {
          document.documentElement.style.fontSize = size;
        }, scale);
        const dropdown = await openCalendar(page);
        const box = await dropdown.boundingBox();
        if (!box) throw new Error("the calendar isn't on screen");
        expect(box.x, `${lang} ${scale}`).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width, `${lang} ${scale}`).toBeLessThanOrEqual(320);
        const day = await dropdown.locator(".mantine-DateInput-day").first().boundingBox();
        expect(day?.height, `${lang} ${scale}`).toBeGreaterThanOrEqual(44);
        expect(day?.width, `${lang} ${scale}`).toBeGreaterThanOrEqual(24);
      }
    }
  });
});

// What `/aggregate` can return: one point per date with data, up to 500 of them, with gaps, a refund and a blank.
for (const [device, config] of Object.entries(WIDTHS)) {
  test.describe(`a long series on a ${device}`, () => {
    test.use({ viewport: config.viewport, hasTouch: config.hasTouch, isMobile: config.isMobile });

    for (const lang of ["ar", "fr"]) {
      test(`keeps its axis readable in ${lang}, and isn't a wall of tab stops`, async ({ page }) => {
        await open(page, "dash", lang, "light", "awkward");
        const chart = page.locator("figure svg").first();
        await expect(chart.locator("rect[tabindex]")).toHaveCount(0);
        const labels = await chart.locator('text[text-anchor="middle"]').evaluateAll((texts) => texts.map((text) => text.getBoundingClientRect()).map((box) => [Math.min(box.left, box.right), Math.max(box.left, box.right)] as const).sort((a, b) => a[0] - b[0]));
        expect(labels.length).toBeGreaterThan(1);
        labels.slice(1).forEach(([left], index) => expect(left, `label ${index + 1}`).toBeGreaterThanOrEqual(labels[index]?.[1] ?? 0));
        const { area, line } = await chart.evaluate((svg) => {
          const [fill, stroke] = svg.querySelectorAll("path");
          return { area: fill?.getAttribute("d") ?? "", line: stroke?.getAttribute("d") ?? "" };
        });
        expect(area).toMatch(/^M/);
        // The blank day breaks the line into two runs, and it isn't drawn as a zero.
        expect(line.match(/M/g)).toHaveLength(2);
      });
    }
  });
}

test.describe("a short series", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("can be read a point at a time with the keyboard", async ({ page }) => {
    await open(page, "dash", "fr", "light", "normal");
    await expect(page.locator("figure svg").first().locator("rect[tabindex]")).toHaveCount(6);
  });
});

test.describe("work under way", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("moves along the reading direction, and stops moving for someone who asked", async ({ page }) => {
    await open(page, "projects", "ar", "light", "normal");
    const bar = page.locator("[role=status] i");
    expect(await bar.evaluate((element) => getComputedStyle(element).animationName)).not.toBe("none");
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(await bar.evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
  });
});

test.describe("a file field", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("shows the name it was given, in that name's own direction", async ({ page }) => {
    await open(page, "projects", "fr", "light", "normal");
    await page.locator('input[type="file"]').setInputFiles({ name: "تصليحات.xlsx", mimeType: "application/octet-stream", buffer: Buffer.from("x") });
    const name = page.locator("#workbook bdi");
    await expect(name).toHaveText("تصليحات.xlsx");
    expect(await name.getAttribute("dir")).toBe("auto");
  });
});

test.describe("phone navigation", () => {
  test.use({ viewport: { width: 360, height: 680 }, hasTouch: true, isMobile: true });

  test("is on screen, with four pages and More", async ({ page }) => {
    await open(page, "list", "fr", "light", "normal");
    const bar = page.getByRole("navigation", { name: "Menu" });
    await expect(bar.getByRole("button")).toHaveCount(5);
    await expect(bar.getByRole("button", { name: "Paiements" })).toHaveAttribute("aria-current", "page");
    await expect(bar.getByRole("button", { name: "Plus" })).toBeVisible();
  });

  test("marks More for a page past the first four", async ({ page }) => {
    await open(page, "calc", "fr", "light", "normal");
    await expect(page.getByRole("navigation", { name: "Menu" }).getByRole("button", { name: "Plus" })).toHaveAttribute("aria-current", "page");
  });

  test("gives way to back and the page's own actions on a detail page", async ({ page }) => {
    await open(page, "record", "fr", "light", "normal");
    await expect(page.getByRole("navigation", { name: "Menu" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Retour" })).toBeVisible();
  });

  test("leaves room for six full rows on the commonest Algerian screen", async ({ page }) => {
    for (const lang of ["ar", "fr"]) {
      await open(page, "list", lang, "light", "normal");
      const count = await page.evaluate(() => {
        const main = document.querySelector("main")?.getBoundingClientRect();
        if (!main) return 0;
        return [...document.querySelectorAll("main li button")].filter((row) => {
          const box = row.getBoundingClientRect();
          return box.top >= main.top - 1 && box.bottom <= main.bottom + 1;
        }).length;
      });
      expect(count, lang).toBeGreaterThanOrEqual(6);
    }
  });
});
