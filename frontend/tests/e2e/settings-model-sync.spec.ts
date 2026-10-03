import { expect, test } from "@playwright/test";

import { mockLangGraphAPI, MOCK_THREAD_ID } from "./utils/mock-api";

for (const agent of [false, true]) {
  for (const field of ["effort", "mode"] as const) {
    test(`${agent ? "agent" : "normal"} thread ${field} selection preserves the account model`, async ({
      page,
    }) => {
      mockLangGraphAPI(page, {
        agents: [{ name: "researcher", description: "Research agent" }],
        threads: [
          {
            thread_id: MOCK_THREAD_ID,
            agent_name: agent ? "researcher" : undefined,
          },
        ],
      });
      await page.addInitScript(
        ({ threadId }) => {
          localStorage.setItem(
            `deerflow.thread-model.${threadId}`,
            "thread-model",
          );
        },
        { threadId: MOCK_THREAD_ID },
      );
      await page.route("**/api/models", (route) =>
        route.fulfill({
          json: {
            models: [
              {
                name: "account-model",
                display_name: "Account Model",
                supports_thinking: true,
                supports_reasoning_effort: true,
              },
              {
                name: "thread-model",
                display_name: "Thread Model",
                supports_thinking: true,
                supports_reasoning_effort: true,
              },
            ],
          },
        }),
      );
      await page.route("**/api/v1/auth/me", (route) =>
        route.fulfill({
          json: {
            id: "00000000-0000-0000-0000-000000000028",
            email: "thread@example.com",
            system_role: "admin",
            needs_setup: false,
          },
        }),
      );
      const owner = "00000000-0000-0000-0000-000000000028";
      const preferenceRequests: Array<{
        method: string;
        owner: string | undefined;
        status?: number;
        patch?: unknown;
      }> = [];
      const patches: unknown[] = [];
      let reads = 0;
      let server = {
        model_name: "account-model",
        mode: "pro",
        reasoning_effort: "medium",
        notification_enabled: true,
      };
      await page.route("**/api/v1/auth/preferences", async (route) => {
        const expectedUserId = route.request().headers()["x-expected-user-id"];
        if (route.request().method() === "PATCH") {
          const patch = route.request().postDataJSON() as Partial<
            typeof server
          >;
          preferenceRequests.push({
            method: "PATCH",
            owner: expectedUserId,
            patch,
          });
          patches.push(patch);
          server = { ...server, ...patch };
          await route.fulfill({ status: 204 });
        } else {
          if (expectedUserId === "e2e-user") {
            preferenceRequests.push({
              method: "GET",
              owner: expectedUserId,
              status: 409,
            });
            await route.fulfill({ status: 409 });
            return;
          }
          if (expectedUserId !== owner) {
            preferenceRequests.push({
              method: "GET",
              owner: expectedUserId,
              status: 409,
            });
            await route.fulfill({ status: 409 });
            return;
          }
          reads++;
          preferenceRequests.push({
            method: "GET",
            owner: expectedUserId,
            status: 200,
          });
          await route.fulfill({ json: server });
        }
      });
      await page.goto(
        `/workspace/${agent ? "agents/researcher/chats" : "chats"}/${MOCK_THREAD_ID}`,
      );
      await page
        .locator("[data-sidebar='sidebar']")
        .getByRole("button", { name: /Settings and more/ })
        .click();
      await page.keyboard.press("Escape");
      await page.evaluate(() =>
        document.dispatchEvent(new Event("visibilitychange")),
      );
      await expect.poll(() => reads).toBe(1);
      await expect(page.getByTestId("model-selector-trigger")).toContainText(
        "Thread Model",
      );
      await expect(
        page.getByRole("button", {
          name: "Reasoning Effort: Medium",
          exact: true,
        }),
      ).toBeVisible();
      if (field === "effort") {
        await page
          .getByRole("button", {
            name: "Reasoning Effort: Medium",
            exact: true,
          })
          .click();
        await page.getByRole("menuitem").filter({ hasText: /^High/ }).click();
      } else {
        const modeButton = page.getByRole("button", {
          name: "Mode",
          exact: true,
        });
        await expect(modeButton).toContainText("Pro");
        await modeButton.click();
        await page
          .getByRole("menuitem")
          .filter({ hasText: /^Ultra/ })
          .click();
      }
      await expect
        .poll(() => patches)
        .toEqual([
          field === "effort"
            ? { reasoning_effort: "high" }
            : { mode: "ultra", reasoning_effort: "high" },
        ]);
      expect(server.model_name).toBe("account-model");
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("model-selector-trigger")).toContainText(
        "Thread Model",
      );
      expect(
        preferenceRequests.filter(({ method }) => method === "PATCH"),
      ).toEqual([
        {
          method: "PATCH",
          owner,
          patch:
            field === "effort"
              ? { reasoning_effort: "high" }
              : { mode: "ultra", reasoning_effort: "high" },
        },
      ]);
    });
  }
}

test("custom agent automatic default does not become an account preference", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    agents: [
      {
        name: "researcher",
        description: "Research agent",
        model: "agent-model",
      },
    ],
  });
  const owner = "00000000-0000-0000-0000-000000000027";
  const preferenceRequests: Array<{
    method: string;
    owner: string | undefined;
    status?: number;
    patch?: unknown;
  }> = [];
  const patches: unknown[] = [];
  let reads = 0;
  let allowModels!: () => void;
  const modelsReady = new Promise<void>((resolve) => {
    allowModels = resolve;
  });
  await page.route("**/api/models", async (route) => {
    // Do not let the auth-disabled fixture select a model before the account
    // is activated. The real agent page must then choose its configured model.
    await modelsReady;
    await route.fulfill({
      json: {
        models: [
          {
            name: "first-model",
            display_name: "First Model",
            supports_thinking: true,
          },
          {
            name: "agent-model",
            display_name: "Agent Model",
            supports_thinking: true,
          },
        ],
      },
    });
  });
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "00000000-0000-0000-0000-000000000027",
        email: "agent@example.com",
        system_role: "admin",
        needs_setup: false,
      },
    }),
  );
  await page.route("**/api/v1/auth/preferences", async (route) => {
    const expectedUserId = route.request().headers()["x-expected-user-id"];
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON();
      preferenceRequests.push({
        method: "PATCH",
        owner: expectedUserId,
        patch,
      });
      patches.push(patch);
      await route.fulfill({ status: 204 });
    } else {
      if (expectedUserId === "e2e-user") {
        preferenceRequests.push({
          method: "GET",
          owner: expectedUserId,
          status: 409,
        });
        await route.fulfill({ status: 409 });
        return;
      }
      if (expectedUserId !== owner) {
        preferenceRequests.push({
          method: "GET",
          owner: expectedUserId,
          status: 409,
        });
        await route.fulfill({ status: 409 });
        return;
      }
      reads++;
      preferenceRequests.push({
        method: "GET",
        owner: expectedUserId,
        status: 200,
      });
      await route.fulfill({
        json: {
          model_name: null,
          mode: null,
          reasoning_effort: null,
          notification_enabled: true,
        },
      });
    }
  });
  const agentResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/resources/researcher/published"),
  );
  await page.goto("/workspace/agents/researcher/chats/new");
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: /Settings and more/ })
    .click();
  await page.keyboard.press("Escape");
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect.poll(() => reads).toBe(1);
  await agentResponse;
  allowModels();
  await expect(page.getByTestId("model-selector-trigger")).toContainText(
    "Agent Model",
  );
  // Flush the local outbox cycle through a completed server read, so this also
  // catches a PATCH that would otherwise arrive just after the UI assertion.
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => reads).toBe(2);
  expect(patches).toEqual([]);
  // Explicit model selections on this same page must still be synchronized.
  await expect(page.getByTestId("model-selector-trigger")).toContainText(
    "Agent Model",
  );
  await page.getByTestId("model-selector-trigger").click();
  await page
    .getByRole("button", { name: "First Model (first-model)", exact: true })
    .click();
  await expect.poll(() => patches).toEqual([{ model_name: "first-model" }]);
  expect(preferenceRequests.filter(({ method }) => method === "PATCH")).toEqual(
    [{ method: "PATCH", owner, patch: { model_name: "first-model" } }],
  );
  expect(preferenceRequests[0]).toEqual({
    method: "GET",
    owner: "e2e-user",
    status: 409,
  });
});

test("automatic model fallback cannot overwrite a slowly loaded account preference", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const owner = "00000000-0000-0000-0000-000000000026";
  const patches: unknown[] = [];
  const preferenceRequests: Array<{
    method: string;
    owner: string | undefined;
    status?: number;
    patch?: unknown;
  }> = [];
  let requestedOwnerRead = false;
  let accountReads = 0;
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/models", (route) =>
    route.fulfill({
      json: {
        models: [
          { name: "model-a", display_name: "Model A", supports_thinking: true },
          { name: "model-b", display_name: "Model B", supports_thinking: true },
        ],
      },
    }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "00000000-0000-0000-0000-000000000026",
        email: "model@example.com",
        system_role: "admin",
        needs_setup: false,
      },
    }),
  );
  await page.route("**/api/v1/auth/preferences", async (route) => {
    const expectedUserId = route.request().headers()["x-expected-user-id"];
    if (route.request().method() === "PATCH") {
      const patch = route.request().postDataJSON();
      preferenceRequests.push({
        method: "PATCH",
        owner: expectedUserId,
        patch,
      });
      patches.push(patch);
      await route.fulfill({ status: 204 });
      return;
    }
    if (expectedUserId === "e2e-user") {
      preferenceRequests.push({
        method: "GET",
        owner: expectedUserId,
        status: 409,
      });
      await route.fulfill({ status: 409 });
      return;
    }
    if (expectedUserId !== owner) {
      preferenceRequests.push({
        method: "GET",
        owner: expectedUserId,
        status: 409,
      });
      await route.fulfill({ status: 409 });
      return;
    }
    requestedOwnerRead = true;
    accountReads++;
    await delayed;
    preferenceRequests.push({
      method: "GET",
      owner: expectedUserId,
      status: 200,
    });
    await route.fulfill({
      json: {
        model_name: "model-b",
        mode: "pro",
        reasoning_effort: "high",
        notification_enabled: true,
      },
    });
  });
  await page.goto("/workspace/chats/new");
  // Wait for actual hydration before refreshing the auth-disabled fixture's
  // AuthProvider into a session account with a deliberately slow preference GET.
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: /Settings and more/ })
    .click();
  await page.keyboard.press("Escape");
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect.poll(() => requestedOwnerRead).toBe(true);
  await expect(page.getByTestId("model-selector-trigger")).toContainText(
    "Model A",
  );
  release();
  await expect(page.getByTestId("model-selector-trigger")).toContainText(
    "Model B",
  );
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => accountReads).toBe(2);
  await expect(page.getByTestId("model-selector-trigger")).toContainText(
    "Model B",
  );
  expect(patches).toEqual([]);
  expect(preferenceRequests).toEqual([
    { method: "GET", owner: "e2e-user", status: 409 },
    { method: "GET", owner, status: 200 },
    { method: "GET", owner, status: 200 },
  ]);
});
