import { expect, test } from "@playwright/test";

import { MOCK_THREAD_ID, mockLangGraphAPI } from "./utils/mock-api";

test.use({ timezoneId: "America/New_York" });

test("conversation task details show paused state and the latest outcome in local time", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "Scheduled conversation",
        updated_at: "2026-11-05T01:00:00Z",
      },
    ],
    scheduledTasks: [
      {
        id: "task-176",
        thread_id: MOCK_THREAD_ID,
        title: "Daily summary",
        prompt: "Summarize",
        schedule_type: "cron",
        schedule_spec: { cron: "0 9 * * *" },
        timezone: "Asia/Shanghai",
        status: "paused",
        next_run_at: "2026-11-06T01:00:00Z",
        last_run_at: "2026-11-05T01:00:00Z",
        last_run_id: "run-176",
        last_error: null,
        run_count: 1,
        created_at: "2026-11-01T00:00:00Z",
        updated_at: "2026-11-05T01:00:00Z",
      },
    ],
  });
  await page.route("**/api/scheduled-tasks/task-176/runs**", (route) =>
    route.fulfill({
      json: [
        {
          id: "occurrence-176",
          status: "failed",
          trigger: "scheduled",
          scheduled_for: "2026-11-05T01:00:00Z",
          error: "Model unavailable",
        },
      ],
    }),
  );
  await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
  const trigger = page.getByRole("button", {
    name: "Associated scheduled tasks",
  });
  await expect(trigger).toContainText("1");
  await trigger.click();
  const panel = page.getByRole("dialog", {
    name: "Associated scheduled tasks",
  });
  await expect(
    panel.getByRole("heading", { name: "Daily summary" }),
  ).toBeVisible();
  await expect(panel.getByText("Paused", { exact: true })).toBeVisible();
  await expect(panel.getByText("Failed", { exact: true })).toBeVisible();
  await expect(panel.getByText("Model unavailable")).toBeVisible();
  await expect(panel.locator("time")).toHaveText("Nov 4, 2026, 8:00 PM");
  await expect(
    panel.getByRole("button", { name: /pause|resume|trigger|delete/i }),
  ).toHaveCount(0);
  await panel.screenshot({
    path: "../dev-log/issue-176-scheduled-task-panel.png",
  });
  await panel
    .getByRole("link", { name: "Scheduled tasks", exact: true })
    .click();
  await page.waitForURL(
    new RegExp(`/workspace/scheduled-tasks\\?thread_id=${MOCK_THREAD_ID}$`),
  );
});
