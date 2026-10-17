import { expect, test } from "@playwright/test";

// Regression seam for issue #93: showcase demo-thread requests deliberately
// fall through the Playwright interceptors (tests/e2e/utils/mock-api.ts) to
// the real /mock/api routes, which the static-mode gate closes unless the
// lane sets DEER_FLOW_MOCK_API_ENABLED=1. Rendering the bundled transcript
// here — in the smoke lane PR CI already runs — keeps that gate/lane coupling
// from silently rotting again ("PR green, develop red").
test.describe("@smoke Public showcase", () => {
  test("bundled demo thread renders via the server demo routes", async ({
    page,
  }) => {
    const demoThreadId = "7cfa5f8f-a2f8-47ad-acbd-da7137baf990";

    await page.goto(`/showcase/${demoThreadId}`);

    await expect(
      page.getByText("What might be the trends and opportunities in 2026?"),
    ).toBeVisible({ timeout: 15_000 });
  });
});
