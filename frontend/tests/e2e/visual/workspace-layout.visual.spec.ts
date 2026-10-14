import { test, expect } from "@playwright/test";

import { mockLangGraphAPI } from "../utils/mock-api";
import { waitForAnimationsSettled } from "../utils/settle";

test.describe("Workspace layout — visual regression", () => {
  test.beforeEach(async ({ page }) => {
    mockLangGraphAPI(page);
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  test("default viewport screenshot", async ({ page }) => {
    await page.goto("/workspace");
    await expect(page.getByTestId("workbench-home")).toBeVisible();
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("workspace-default.png", {
      fullPage: true,
    });
  });

  test("mobile viewport screenshot", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/workspace");
    await expect(page.getByTestId("workbench-home")).toBeVisible();
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("workspace-mobile.png", {
      fullPage: true,
    });
  });

  test("dark mode screenshot", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/workspace");
    await expect(page.getByTestId("workbench-home")).toBeVisible();
    // Let animations finish observably before the pixel capture
    // (bounded: persistent animations degrade to the fixed wait).
    await waitForAnimationsSettled(page, 5_000);

    await expect(page).toHaveScreenshot("workspace-dark.png", {
      fullPage: true,
    });
  });
});
