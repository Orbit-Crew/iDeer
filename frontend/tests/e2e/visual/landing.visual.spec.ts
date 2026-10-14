import { test, expect } from "@playwright/test";

import { mockLangGraphAPI } from "../utils/mock-api";
import { waitForAnimationsSettled } from "../utils/settle";

test.describe("Landing — visual regression", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      const nativeSetInterval = window.setInterval.bind(window);
      window.setInterval = ((handler, timeout, ...args) => {
        if (timeout === 2200) {
          return nativeSetInterval(() => undefined, 2_147_483_647);
        }
        return nativeSetInterval(handler, timeout, ...args);
      }) as typeof window.setInterval;
    });
    mockLangGraphAPI(page);
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  test("default viewport screenshot", async ({ page }) => {
    await page.goto("/");
    // Wait for the hero section to render (rotating word component)
    await page
      .locator("h1")
      .first()
      .waitFor({ state: "visible", timeout: 10000 });
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("landing-default.png", {
      fullPage: true,
    });
  });

  test("mobile viewport screenshot", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await page
      .locator("h1")
      .first()
      .waitFor({ state: "visible", timeout: 10000 });
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("landing-mobile.png", {
      fullPage: true,
    });
  });

  test("dark mode screenshot", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/");
    await page
      .locator("h1")
      .first()
      .waitFor({ state: "visible", timeout: 10000 });
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("landing-dark.png", {
      fullPage: true,
    });
  });
});
