"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Folder } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import { BrowserTrigger } from "@/components/workspace/browser-view";
import { ContextUsageBadge } from "@/components/workspace/context-usage-badge";
import { ExportTrigger } from "@/components/workspace/export-trigger";
import { GoalStatus } from "@/components/workspace/goal-status";
import { InputBox } from "@/components/workspace/input-box";
import {
  MessageList,
  MESSAGE_LIST_DEFAULT_PADDING_BOTTOM,
} from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import {
  SidecarProvider,
  SidecarTrigger,
} from "@/components/workspace/sidecar";
import { ThreadArchiveStatus } from "@/components/workspace/thread-archive-status";
import { ThreadBackgroundTasks } from "@/components/workspace/thread-background-tasks";
import { ThreadScheduledTasksLink } from "@/components/workspace/thread-scheduled-tasks-link";
import { ThreadSubagentBatches } from "@/components/workspace/thread-subagent-batches";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { TokenUsageIndicator } from "@/components/workspace/token-usage-indicator";
import { useActiveGoal } from "@/components/workspace/use-active-goal";
import { Welcome } from "@/components/workspace/welcome";
import { useAuth } from "@/core/auth/AuthProvider";
import { hasPermission, PERMISSIONS } from "@/core/auth/permissions";
import { useBrowserControlEnabled } from "@/core/features";
import { useI18n } from "@/core/i18n/hooks";
import {
  buildHumanInputResponseText,
  hasOpenHumanInputRequest,
  type HumanInputRequest,
  type HumanInputResponse,
} from "@/core/messages/human-input";
import { isHiddenFromUIMessage } from "@/core/messages/utils";
import { useModels } from "@/core/models/hooks";
import { useProject } from "@/core/projects";
import { useLocalSettings, useThreadSettings } from "@/core/settings";
import { resolveThreadContext } from "@/core/settings/store";
import { createThread } from "@/core/threads/api";
import {
  INFINITE_THREADS_QUERY_KEY_PREFIX,
  useThreadTokenUsage,
} from "@/core/threads/hooks";
import {
  selectContextUsage,
  threadTokenUsageToTokenUsage,
} from "@/core/threads/token-usage";
import { useThreadPage } from "@/core/threads/use-thread-page";
import { pathOfThread, projectIdOfThread } from "@/core/threads/utils";
import { env } from "@/env";
import { cn } from "@/lib/utils";

import { ChatBox } from "./chat-box";
import { useSpecificChatMode } from "./use-chat-mode";
import { useThreadChat } from "./use-thread-chat";

export default function ChatPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const canStopStreaming = hasPermission(user, PERMISSIONS.RUNS_CANCEL);
  const searchParams = useSearchParams();
  const { threadId, setThreadId, isNewThread, setIsNewThread, isMock } =
    useThreadChat();
  // Project-scoped new chat: `/workspace/chats/new?project={id}` assigns the
  // thread to the project on the FIRST submit — primarily via an explicit
  // `POST /api/threads` pre-create with `project_id`, with the run-request
  // metadata seed as the fallback channel (the SDK's own threads.create
  // strips the reserved key, so the seed alone races the sidebar). Only
  // meaningful while the thread is still lazy (`isNewThread`); once
  // materialized the URL is replaced with the thread route and the param is
  // gone. Invalid ids are dropped by backend admission.
  const projectParam = isNewThread ? searchParams.get("project") : null;
  const queryClient = useQueryClient();
  const [settings, setSettings] = useThreadSettings(threadId);
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { enabled: browserControlEnabled } = useBrowserControlEnabled();
  const { tokenUsageEnabled } = useModels();
  const threadTokenUsage = useThreadTokenUsage(
    isNewThread || isMock ? undefined : threadId,
    { enabled: !isMock },
  );
  const backendTokenUsage = threadTokenUsageToTokenUsage(threadTokenUsage.data);
  const contextUsage = selectContextUsage(threadTokenUsage.data);
  const mountedRef = useRef(false);
  useSpecificChatMode();

  useEffect(() => {
    mountedRef.current = true;
  }, []);

  // Born assigned: pre-create the thread row with its project so the sidebar
  // lists it under the project immediately. Idempotent server-side on
  // `thread_id`, so retrying the same first message (same `threadId` while
  // `isNewThread`) reuses the existing row instead of double-creating. This
  // is the sole membership channel — run requests never carry the project
  // key.
  //
  // Also runs before InputBox issues a `/goal <condition>` PUT (via
  // `onPrepareThread`): the goal endpoint materializes a missing thread row
  // itself, and an unassigned row would make this later idempotent create a
  // membership no-op.
  const ensureProjectThread = useCallback(async () => {
    if (!projectParam) {
      return;
    }
    try {
      await createThread(threadId, projectParam);
      void queryClient.invalidateQueries({
        queryKey: INFINITE_THREADS_QUERY_KEY_PREFIX,
      });
    } catch (error) {
      // Any failure (e.g. the project was deleted/archived between page load
      // and submit): do NOT submit unassigned. Reject so PromptInput keeps
      // the composer's text for a retry; the send in-flight guard is never
      // engaged on this path, so retrying works immediately.
      toast.error(t.projects.projectUnavailable);
      throw error;
    }
  }, [threadId, projectParam, queryClient, t]);

  // The page-level wiring seam (stream, welcome state, redirect, stop/
  // branch/regenerate, turn-submit controller); this route contributes the
  // project pre-create as the pre-dispatch prepare step and tracks the
  // project scope so a scope change invalidates an in-flight submission.
  const {
    thread,
    pendingUsageMessages,
    sendMessage,
    isUploading,
    isHistoryLoading,
    hasMoreHistory,
    loadMoreHistory,
    isWelcomeMode,
    threadMetadata,
    branchPending,
    turnSubmit,
    handleStop,
    handleRegenerate,
    handleEditAndRegenerate,
    handleBranchTurn,
  } = useThreadPage({
    threadId,
    isNewThread,
    isMock,
    setThreadId,
    setIsNewThread,
    context: settings.context,
    threadPath: pathOfThread,
    prepare: ensureProjectThread,
    scopeKey: projectParam,
  });

  const handleSubmitHumanInput = useCallback(
    async (request: HumanInputRequest, response: HumanInputResponse) => {
      let sent = false;
      await sendMessage(
        threadId,
        {
          text: buildHumanInputResponseText(request, response),
          files: [],
        },
        undefined,
        {
          additionalKwargs: {
            hide_from_ui: true,
            human_input_response: response,
          },
          onSent: () => {
            sent = true;
          },
        },
      );
      return sent;
    },
    [sendMessage, threadId],
  );

  const tokenUsageInlineMode = tokenUsageEnabled
    ? localSettings.tokenUsage.inlineMode
    : "off";
  const hasTodos = (thread.values.todos?.length ?? 0) > 0;
  const browserEnabled = !isNewThread && !isMock && browserControlEnabled;
  const { activeGoal, hasGoal, setLocalGoal } = useActiveGoal(
    threadId,
    thread.values.goal,
  );
  const hasOpenHumanInputCard = useMemo(
    () =>
      hasOpenHumanInputRequest(
        thread.messages,
        (message) => !isHiddenFromUIMessage(message),
      ),
    [thread.messages],
  );

  // Project affiliation chip: shown once the materialized thread's metadata
  // carries `deerflow_project_id` (written by the create/move endpoints and
  // exposed here read-only).
  const affiliatedProjectId =
    !isNewThread && !isMock && threadMetadata.data
      ? projectIdOfThread(threadMetadata.data)
      : null;

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <SidecarProvider
        parentThreadId={threadId}
        context={settings.context}
        isMock={isMock}
      >
        <ChatBox threadId={threadId} browserEnabled={browserEnabled}>
          <div className="relative flex size-full min-h-0 justify-between">
            <header
              className={cn(
                "absolute top-0 right-0 left-0 flex h-12 shrink-0 items-center gap-2 px-2 sm:px-4",
                isWelcomeMode
                  ? "bg-background/0 z-40 backdrop-blur-none"
                  : "bg-background/80 z-30 shadow-xs backdrop-blur",
              )}
            >
              {!isMock && <SidebarTrigger className="md:hidden" />}
              <div className="type-supporting flex min-w-0 flex-1 items-center gap-2 font-medium">
                <ThreadTitle
                  threadId={threadId}
                  thread={thread}
                  canonicalTitle={threadMetadata.data?.values?.title}
                />
                {!isNewThread &&
                  !isMock &&
                  env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                    <ThreadArchiveStatus
                      threadId={threadId}
                      metadata={threadMetadata.data?.metadata}
                    />
                  )}
                {affiliatedProjectId && (
                  <ProjectAffiliationBadge projectId={affiliatedProjectId} />
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {!isNewThread &&
                  !isMock &&
                  env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                    <ThreadBackgroundTasks threadId={threadId} />
                  )}
                {!isNewThread &&
                  !isMock &&
                  env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" && (
                    <ThreadSubagentBatches threadId={threadId} />
                  )}
                {!isNewThread && !isMock && (
                  <ThreadScheduledTasksLink threadId={threadId} />
                )}
                {tokenUsageEnabled ? (
                  <TokenUsageIndicator
                    threadId={isNewThread ? undefined : threadId}
                    backendUsage={backendTokenUsage}
                    contextUsage={contextUsage}
                    enabled={tokenUsageEnabled}
                    messages={thread.messages}
                    pendingMessages={pendingUsageMessages}
                    preferences={localSettings.tokenUsage}
                    onPreferencesChange={(preferences) =>
                      setLocalSettings("tokenUsage", preferences)
                    }
                  />
                ) : (
                  <ContextUsageBadge contextUsage={contextUsage} />
                )}
                <SidecarTrigger />
                {browserEnabled && <BrowserTrigger />}
                <ExportTrigger threadId={threadId} />
                <ArtifactTrigger />
              </div>
            </header>
            <main className="flex min-h-0 max-w-full grow flex-col">
              <div className="flex min-h-0 flex-1 justify-center">
                <MessageList
                  archiveDownloadsEnabled={
                    isNewThread || isMock || threadMetadata.data != null
                  }
                  className={cn("size-full", !isWelcomeMode && "pt-10")}
                  testId="main-message-list"
                  threadId={threadId}
                  thread={thread}
                  enableConversationOutline
                  paddingBottom={MESSAGE_LIST_DEFAULT_PADDING_BOTTOM}
                  hasMoreHistory={hasMoreHistory}
                  loadMoreHistory={loadMoreHistory}
                  isHistoryLoading={isHistoryLoading}
                  tokenUsageInlineMode={tokenUsageInlineMode}
                  canRegenerate={
                    !isNewThread &&
                    !isMock &&
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" &&
                    !isUploading &&
                    !thread.isLoading
                  }
                  onRegenerateMessage={handleRegenerate}
                  canEdit={
                    !isNewThread &&
                    !isMock &&
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" &&
                    !isUploading &&
                    !thread.isLoading &&
                    !branchPending &&
                    !hasGoal &&
                    !hasOpenHumanInputCard
                  }
                  onEditAndRegenerateMessage={handleEditAndRegenerate}
                  onSubmitHumanInput={
                    isMock || env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"
                      ? undefined
                      : handleSubmitHumanInput
                  }
                  canBranch={
                    !isNewThread &&
                    !isMock &&
                    env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY !== "true" &&
                    !isUploading &&
                    !thread.isLoading &&
                    !branchPending
                  }
                  onBranchTurn={handleBranchTurn}
                />
              </div>
              <div
                className={cn(
                  "right-0 bottom-0 left-0 z-30 flex justify-center px-3 sm:px-4",
                  isWelcomeMode ? "absolute" : "relative shrink-0 pb-4",
                )}
              >
                <div
                  className={cn(
                    "relative w-full",
                    isWelcomeMode &&
                      "-translate-y-[calc(50vh-48px)] sm:-translate-y-[calc(50vh-96px)]",
                    isWelcomeMode
                      ? "max-w-(--container-width-sm)"
                      : "max-w-(--container-width-md)",
                  )}
                >
                  {(hasGoal || hasTodos) && (
                    <div
                      className={cn(
                        "right-0 left-0 z-0",
                        isWelcomeMode ? "absolute -top-4" : "relative",
                      )}
                    >
                      <div
                        className={cn(
                          "right-0 bottom-0 left-0 flex flex-col",
                          isWelcomeMode ? "absolute" : "relative",
                        )}
                      >
                        {activeGoal && <GoalStatus goal={activeGoal} />}
                        {hasTodos && (
                          <TodoList
                            className="bg-background/5"
                            todos={thread.values.todos ?? []}
                            hidden={false}
                          />
                        )}
                      </div>
                    </div>
                  )}
                  {mountedRef.current ? (
                    <InputBox
                      className={cn(
                        "bg-background/5 w-full",
                        isWelcomeMode && "-translate-y-2 sm:-translate-y-4",
                      )}
                      isWelcomeMode={isWelcomeMode}
                      threadId={threadId}
                      draftThreadId={isNewThread ? "new" : threadId}
                      autoFocus={isWelcomeMode}
                      status={
                        thread.error
                          ? "error"
                          : thread.isLoading
                            ? "streaming"
                            : "ready"
                      }
                      context={settings.context}
                      extraHeader={
                        isWelcomeMode &&
                        !hasGoal &&
                        !hasTodos && <Welcome mode={settings.context.mode} />
                      }
                      disabled={
                        isMock ||
                        env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ||
                        isUploading ||
                        (!isNewThread && isHistoryLoading)
                      }
                      onContextChange={(context, options) => {
                        if (options?.automatic)
                          resolveThreadContext(threadId, context);
                        else setSettings("context", context);
                      }}
                      onGoalChange={setLocalGoal}
                      onPrepareThread={ensureProjectThread}
                      turnSubmit={turnSubmit}
                      onStop={handleStop}
                      canStopStreaming={canStopStreaming}
                    />
                  ) : (
                    <div
                      aria-hidden="true"
                      className={cn(
                        "bg-background/5 h-32 w-full rounded-2xl",
                        isWelcomeMode && "-translate-y-2 sm:-translate-y-4",
                      )}
                    />
                  )}
                  {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                    <div className="text-muted-foreground/67 type-compact w-full translate-y-12 text-center">
                      {t.common.notAvailableInDemoMode}
                    </div>
                  )}
                </div>
              </div>
            </main>
          </div>
        </ChatBox>
      </SidecarProvider>
    </ThreadContext.Provider>
  );
}

/**
 * Small chip in the chat header linking to the thread's project. Hidden
 * while the project lookup is pending or when it fails (e.g. the project
 * was deleted) — an unresolvable affiliation degrades silently.
 */
function ProjectAffiliationBadge({ projectId }: { projectId: string }) {
  const { data: project } = useProject(projectId);
  if (!project) {
    return null;
  }
  return (
    <Link
      href={`/workspace/projects/${encodeURIComponent(project.id)}`}
      className="text-muted-foreground hover:text-foreground type-compact inline-flex max-w-40 shrink-0 items-center gap-1 truncate rounded-full border px-2 py-0.5 font-normal transition-colors"
    >
      <Folder className="size-3 shrink-0" />
      <span className="truncate">{project.name}</span>
    </Link>
  );
}
