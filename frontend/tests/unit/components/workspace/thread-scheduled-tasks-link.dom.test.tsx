import { afterEach, expect, rs, test } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));

import { ThreadScheduledTasksLink } from "@/components/workspace/thread-scheduled-tasks-link";
import { fetch } from "@/core/api/fetcher";
import { I18nProvider } from "@/core/i18n/context";
import type { ScheduledTask } from "@/core/scheduled-tasks/types";

const task: ScheduledTask = {
  id: "task-1",
  thread_id: null,
  context_mode: "fresh_thread_per_run",
  assistant_id: "lead_agent",
  title: "Daily summary",
  prompt: "Summarize",
  schedule_type: "cron",
  schedule_spec: { cron: "0 9 * * *" },
  timezone: "Asia/Shanghai",
  status: "paused",
  next_run_at: "2026-11-06T01:00:00Z",
  last_run_at: "2026-11-05T01:00:00Z",
  last_run_id: "run-1",
  last_thread_id: "thread-later",
  last_error: null,
  run_count: 3,
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-05T01:00:00Z",
};

const clients: QueryClient[] = [];
function mount(threadId = "thread-history") {
  document.cookie = "locale=en-US";
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="en-US">
        <ThreadScheduledTasksLink threadId={threadId} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  rs.mocked(fetch).mockReset();
});

test("a historical generated conversation shows its task state, schedule and latest execution result", async () => {
  rs.mocked(fetch).mockImplementation(async (url) => {
    if (typeof url === "string" && url.includes("/runs")) {
      return Response.json([
        {
          id: "occurrence-1",
          status: "failed",
          trigger: "scheduled",
          scheduled_for: "2026-11-05T01:00:00Z",
          error: "Model unavailable",
        },
      ]);
    }
    return Response.json([task]);
  });
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: /associated scheduled tasks/i }),
  );
  expect(await screen.findByText("Daily summary")).toBeVisible();
  expect(screen.getByText("Paused")).toBeVisible();
  expect(screen.getByText("0 9 * * * (Asia/Shanghai)")).toBeVisible();
  expect(await screen.findByText("Failed")).toBeVisible();
  expect(screen.getByText("Model unavailable")).toBeVisible();
  expect(screen.getByText("Local time")).toBeVisible();
  expect(screen.getByRole("link", { name: "Scheduled tasks" })).toHaveAttribute(
    "href",
    "/workspace/scheduled-tasks?thread_id=thread-history",
  );
});

test("a failed association read can be retried without changing any task", async () => {
  rs.mocked(fetch).mockResolvedValueOnce(
    Response.json({ detail: "Unavailable" }, { status: 503 }),
  );
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: /associated scheduled tasks/i }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Failed to load scheduled tasks",
  );
  rs.mocked(fetch).mockResolvedValue(Response.json([]));
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByText("No associated scheduled tasks"),
  ).toBeVisible();
  expect(
    rs
      .mocked(fetch)
      .mock.calls.every(([, init]) => !init?.method || init.method === "GET"),
  ).toBe(true);
});

test("a new conversation does not load task associations", () => {
  mount("new");
  expect(fetch).not.toHaveBeenCalled();
  expect(screen.queryByRole("link", { name: "Scheduled tasks" })).toBeNull();
});
