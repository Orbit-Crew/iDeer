import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("account notification setting survives clearing browser storage", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const owner = "00000000-0000-0000-0000-000000000025";
  const preferenceRequests: Array<{
    method: string;
    owner: string | undefined;
    status: number;
    patch?: unknown;
  }> = [];
  let enabled: boolean | null = null;
  const patches: unknown[] = [];
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: owner,
        email: "preferences@example.com",
        system_role: "admin",
        needs_setup: false,
      },
    }),
  );
  await page.route("**/api/v1/auth/preferences", async (route) => {
    const expectedUserId = route.request().headers()["x-expected-user-id"];
    if (route.request().method() === "GET" && expectedUserId === "e2e-user") {
      preferenceRequests.push({
        method: "GET",
        owner: expectedUserId,
        status: 409,
      });
      await route.fulfill({ status: 409 });
      return;
    }
    expect(expectedUserId).toBe(owner);
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON() as {
        notification_enabled: boolean;
      };
      preferenceRequests.push({
        method: "PATCH",
        owner: expectedUserId,
        status: 204,
        patch,
      });
      patches.push(patch);
      enabled = patch.notification_enabled;
      await route.fulfill({ status: 204 });
    } else {
      preferenceRequests.push({
        method: "GET",
        owner: expectedUserId,
        status: 200,
      });
      await route.fulfill({
        json: {
          notification_enabled: enabled,
          model_name: null,
          mode: null,
          reasoning_effort: null,
        },
      });
    }
  });
  await page.addInitScript(() => {
    Object.defineProperty(Notification, "permission", {
      configurable: true,
      get: () => "granted",
    });
  });

  async function openSettings(page: Page) {
    await page.goto("/workspace/chats/new");
    await page
      .locator("[data-sidebar='sidebar']")
      .getByRole("button", { name: /Settings and more/ })
      .click();
    await page.getByRole("menuitem", { name: "Settings", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
    await dialog
      .getByRole("button", { name: "Notification", exact: true })
      .click();
    // Opening the dialog also waits for hydration. The mock web server starts
    // auth-disabled; refresh the real AuthProvider to this session fixture.
    const hydrated = page.waitForResponse((response) => {
      const request = response.request();
      return (
        response.url().endsWith("/api/v1/auth/preferences") &&
        request.method() === "GET" &&
        request.headers()["x-expected-user-id"] === owner
      );
    });
    await page.evaluate(() =>
      document.dispatchEvent(new Event("visibilitychange")),
    );
    await hydrated;
    // Account resolution remounts the dialog at its default section.
    await dialog
      .getByRole("button", { name: "Notification", exact: true })
      .click();
    return dialog.getByRole("switch", { name: "Notification", exact: true });
  }

  const toggle = await openSettings(page);
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect.poll(() => enabled).toBe(false);
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await expect(await openSettings(page)).not.toBeChecked();
  expect(patches).toEqual([{ notification_enabled: false }]);
  expect(preferenceRequests[0]).toEqual({
    method: "GET",
    owner: "e2e-user",
    status: 409,
  });
  expect(
    preferenceRequests
      .filter(({ method, status }) => method === "GET" && status === 200)
      .every(({ owner: requestOwner }) => requestOwner === owner),
  ).toBe(true);
  expect(preferenceRequests.filter(({ method }) => method === "PATCH")).toEqual(
    [
      {
        method: "PATCH",
        owner,
        status: 204,
        patch: { notification_enabled: false },
      },
    ],
  );
});
