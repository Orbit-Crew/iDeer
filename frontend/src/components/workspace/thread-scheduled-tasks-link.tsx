"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Clock3 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useI18n } from "@/core/i18n/hooks";
import { fetchScheduledTaskRuns } from "@/core/scheduled-tasks/api";
import { useThreadScheduledTasks } from "@/core/scheduled-tasks/hooks";
import type { ScheduledTask } from "@/core/scheduled-tasks/types";
import { isStaticWebsiteOnly } from "@/core/static-mode";

function LocalTimestamp({ value }: { value: string | null }) {
  const { locale } = useI18n();
  if (!value || Number.isNaN(new Date(value).getTime())) return <span>—</span>;
  return (
    <time dateTime={value}>
      {new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))}
    </time>
  );
}

function ScheduledTaskSummary({ task }: { task: ScheduledTask }) {
  const { t } = useI18n();
  const labels = t.scheduledTasks;
  const history = useQuery({
    queryKey: ["scheduled-tasks", "runs", task.id, "summary"],
    queryFn: ({ signal }) =>
      fetchScheduledTaskRuns(task.id, { limit: 1, offset: 0, signal }),
    refetchInterval: 15000,
    refetchIntervalInBackground: false,
  });
  const latest = history.data?.[0];
  const cron =
    typeof task.schedule_spec.cron === "string" ? task.schedule_spec.cron : "—";
  const interval =
    typeof task.schedule_spec.every_seconds === "number"
      ? task.schedule_spec.every_seconds
      : "—";
  const schedule =
    task.schedule_type === "cron"
      ? cron
      : task.schedule_type === "interval"
        ? `${interval} ${labels.fields.intervalUnitSeconds}`
        : labels.scheduleType.once;

  return (
    <article className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">{task.title}</h3>
        <Badge variant="secondary">{labels.status[task.status]}</Badge>
      </div>
      <dl className="type-supporting space-y-2">
        <div>
          <dt className="text-muted-foreground">{labels.detail.schedule}</dt>
          <dd className="break-words">
            {schedule} ({task.timezone})
          </dd>
          {task.schedule_type === "once" &&
            typeof task.schedule_spec.run_at === "string" && (
              <dd>
                <LocalTimestamp value={task.schedule_spec.run_at} />
              </dd>
            )}
        </div>
        <div>
          <dt className="text-muted-foreground">{labels.detail.nextRun}</dt>
          <dd>
            <LocalTimestamp
              value={task.status === "paused" ? null : task.next_run_at}
            />
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">
            {labels.threadSummary.latestResult}
          </dt>
          <dd>
            {history.isError ? (
              <span role="alert">
                {labels.history.loadFailed}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void history.refetch()}
                >
                  {labels.threadSummary.retry}
                </Button>
              </span>
            ) : history.isPending ? (
              labels.history.loading
            ) : latest ? (
              <>
                <span>{labels.runStatus[latest.status]}</span>
                {" · "}
                {labels.runTrigger[latest.trigger]}
                {" · "}
                <LocalTimestamp
                  value={
                    latest.finished_at ??
                    latest.started_at ??
                    latest.scheduled_for
                  }
                />
                {latest.error && (
                  <p className="text-destructive break-words">{latest.error}</p>
                )}
              </>
            ) : (
              labels.detail.noRuns
            )}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function ThreadScheduledTasksLink({ threadId }: { threadId: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const enabled = threadId !== "new" && !isStaticWebsiteOnly();
  const query = useThreadScheduledTasks(enabled ? threadId : null);
  const tasks = query.data ?? [];
  const labels = t.scheduledTasks.threadSummary;
  if (!enabled) return null;

  return (
    <div className="flex items-center gap-1">
      <Button variant="outline" size="sm" asChild>
        <Link
          aria-label={t.sidebar.scheduledTasks}
          href={`/workspace/scheduled-tasks?thread_id=${encodeURIComponent(threadId)}`}
        >
          <CalendarClock />
          <span className="hidden sm:inline">{t.sidebar.scheduledTasks}</span>
        </Link>
      </Button>
      {(tasks.length > 0 || query.isError || open) && (
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button
              variant="secondary"
              size="sm"
              aria-label={labels.title}
              title={labels.title}
            >
              <Clock3 />
              <span>{query.isError ? "!" : tasks.length}</span>
            </Button>
          </SheetTrigger>
          <SheetContent className="w-[min(92vw,460px)] overflow-y-auto sm:max-w-[460px]">
            <SheetHeader>
              <SheetTitle>{labels.title}</SheetTitle>
              <SheetDescription>{labels.description}</SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4 pb-4">
              <Button variant="outline" size="sm" asChild>
                <Link
                  href={`/workspace/scheduled-tasks?thread_id=${encodeURIComponent(threadId)}`}
                >
                  {t.sidebar.scheduledTasks}
                </Link>
              </Button>
              <p className="text-muted-foreground type-supporting">
                {labels.localTime}
              </p>
              {query.isError && (
                <div role="alert">
                  <p>{t.scheduledTasks.detail.loadFailed}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void query.refetch()}
                  >
                    {labels.retry}
                  </Button>
                </div>
              )}
              {query.isSuccess && tasks.length === 0 && <p>{labels.empty}</p>}
              {open &&
                tasks.map((task) => (
                  <ScheduledTaskSummary key={task.id} task={task} />
                ))}
            </div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
