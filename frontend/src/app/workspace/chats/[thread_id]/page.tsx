"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { ArtifactTrigger } from "@/components/workspace/artifacts";
import { BrowserTrigger } from "@/components/workspace/browser-view";
import {
  ChatBox,
  useSpecificChatMode,
  useThreadChat,
} from "@/components/workspace/chats";
import { KnowledgeScopeSelector } from "@/components/workspace/chats/knowledge-scope-selector";
import { ExportTrigger } from "@/components/workspace/export-trigger";
import { GoalStatus } from "@/components/workspace/goal-status";
import { InputBox } from "@/components/workspace/input-box";
import {
  MessageList,
  MESSAGE_LIST_DEFAULT_PADDING_BOTTOM,
} from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { ScenarioCascadeBar } from "@/components/workspace/scenario";
import { ScenarioTabs } from "@/components/workspace/scenario/scenario-tabs";
import type { SelectedTag } from "@/components/workspace/scenario/selected-tags";
import {
  SidecarProvider,
  SidecarTrigger,
} from "@/components/workspace/sidecar";
import { ThreadArchiveStatus } from "@/components/workspace/thread-archive-status";
import { ThreadBackgroundTasks } from "@/components/workspace/thread-background-tasks";
import { ThreadScheduledTasksLink } from "@/components/workspace/thread-scheduled-tasks-link";
import { ThreadTitle } from "@/components/workspace/thread-title";
import { TodoList } from "@/components/workspace/todo-list";
import { TokenUsageIndicator } from "@/components/workspace/token-usage-indicator";
import { useActiveGoal } from "@/components/workspace/use-active-goal";
import { Welcome } from "@/components/workspace/welcome";
import { useAgent, useAgents } from "@/core/agents/hooks";
import { getAPIClient } from "@/core/api";
import { useBrowserControlEnabled } from "@/core/features";
import { useI18n } from "@/core/i18n/hooks";
import { useAgentKnowledgeScope } from "@/core/library";
import { hasOpenHumanInputRequest } from "@/core/messages/human-input";
import { isHiddenFromUIMessage } from "@/core/messages/utils";
import { useModels } from "@/core/models/hooks";
import {
  buildScenarioSubmissionBinding,
  useScenarioBinding,
} from "@/core/scenarios/binding";
import { getChipsByPill } from "@/core/scenarios/config";
import type { ScenarioId } from "@/core/scenarios/types";
import { useLocalSettings, useThreadSettings } from "@/core/settings";
import { resolveThreadContext } from "@/core/settings/store";
import { useSkills } from "@/core/skills/hooks";
import { createThread } from "@/core/threads/api";
import {
  INFINITE_THREADS_QUERY_KEY_PREFIX,
  useThreadTokenUsage,
  useThreads,
} from "@/core/threads/hooks";
import { threadTokenUsageToTokenUsage } from "@/core/threads/token-usage";
import { useThreadPage } from "@/core/threads/use-thread-page";
import {
  pathOfThread,
  textOfMessage,
  titleOfThread,
} from "@/core/threads/utils";
import { env } from "@/env";
import { cn } from "@/lib/utils";

function RecentTaskCards({
  threads,
}: {
  threads: Array<Parameters<typeof titleOfThread>[0]>;
}) {
  const { t } = useI18n();
  if (threads.length === 0) return null;
  return (
    <section
      className="workbench-recent-tasks"
      aria-label={t.workbench.recentTasks}
    >
      <p className="workbench-module-guide">
        <span className="workbench-guide-question">
          {t.workbench.reviewQuestion}
        </span>
        <span className="workbench-guide-answer">
          {t.workbench.reviewAnswer}
        </span>
      </p>
      <div className="workbench-recent-grid">
        {threads.slice(0, 3).map((thread) => {
          const values = thread.values as Record<string, unknown> | undefined;
          const metadata = thread.metadata as
            | Record<string, unknown>
            | undefined;
          const context = thread.context;
          const messages = Array.isArray(values?.messages)
            ? values.messages
            : [];
          const latestSummary = [...messages]
            .reverse()
            .map((message) =>
              textOfMessage(message as Parameters<typeof textOfMessage>[0]),
            )
            .find((text): text is string => Boolean(text?.trim()));
          const taskType: string =
            (typeof context?.task_label === "string"
              ? context.task_label
              : undefined) ??
            (typeof metadata?.task_type === "string"
              ? metadata.task_type
              : undefined) ??
            t.workbench.defaultTaskType;
          const status =
            (typeof metadata?.status === "string"
              ? metadata.status
              : undefined) ??
            (typeof values?.status === "string" ? values.status : undefined) ??
            t.workbench.defaultStatus;

          return (
            <Link
              key={thread.thread_id}
              href={pathOfThread(thread)}
              className="workbench-recent-card"
            >
              <span className="workbench-recent-summary">
                {titleOfThread(thread)}
              </span>
              <span className="workbench-recent-meta">
                {taskType} · {status}
                {thread.updated_at ? ` · ${thread.updated_at}` : ""}
              </span>
              {latestSummary && (
                <span className="workbench-recent-detail">{latestSummary}</span>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}

export default function ChatPage() {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const requestedAgent = searchParams.get("agent");
  const {
    threadId,
    setThreadId,
    isNewThread,
    setIsNewThread,
    isMock,
    selectedConnector,
  } = useThreadChat();
  // Project-scoped new chat: `/workspace/chats/new?project={id}` assigns the
  // thread to the project on the FIRST submit — via an explicit
  // `POST /api/threads` pre-create with `project_id` before the run. Only
  // meaningful while the thread is still lazy (`isNewThread`); once
  // materialized the URL is replaced with the thread route and the param is
  // gone. Invalid ids are dropped by backend admission.
  const projectParam = isNewThread ? searchParams.get("project") : null;
  const queryClient = useQueryClient();
  const [settings, setSettings] = useThreadSettings(threadId);
  const [localSettings, setLocalSettings] = useLocalSettings();
  const { tokenUsageEnabled } = useModels();
  const {
    selectedScenario,
    selectedPill,
    selectedChip,
    selectScenario,
    selectAgent,
    togglePill,
    toggleChip,
    activeBinding,
    resetSelection,
  } = useScenarioBinding();
  const { agents } = useAgents();
  const { data: recentThreads = [] } = useThreads();
  const selectedAgent = agents.find(
    (item) => (item.slug ?? item.name) === selectedPill?.agentSlug,
  );
  const { skills } = useSkills();
  const selectedTask = selectedChip
    ? getChipsByPill(selectedChip.scenarioId, selectedChip.agentSlug).find(
        (item) => item.taskId === selectedChip.taskId,
      )
    : undefined;
  const selectedSkill = selectedChip
    ? skills.find(
        (skill) => (skill.slug ?? skill.name) === selectedTask?.skillName,
      )
    : undefined;
  const { agent: selectedAgentDetails } = useAgent(selectedAgent?.resource_id);
  const [pendingTemplate, setPendingTemplate] = useState<string | null>(null);
  const [templateResetKey, setTemplateResetKey] = useState(0);
  // Issue 114: the caller's own device KBs and the Agent's server KBs are
  // selectable per chat. The selection is a narrowing of the Server-authorized
  // scope only — it rides `runtime_knowledge_scope` and the frozen closure
  // still decides what a Run may search.
  const { data: agentKnowledgeScope, isError: knowledgeScopeError } =
    useAgentKnowledgeScope(selectedAgent?.resource_id);
  const [narrowedKnowledge, setNarrowedKnowledge] = useState<string[] | null>(
    null,
  );
  const knowledgeScopeSources = agentKnowledgeScope?.sources ?? [];
  useEffect(() => {
    // A scope change (different Agent, new revision) resets the narrowing.
    setNarrowedKnowledge(null);
  }, [selectedAgent?.resource_id, knowledgeScopeSources.length]);
  const knowledgeScopeContext = useMemo(() => {
    if (knowledgeScopeSources.length === 0) return {};
    if (!narrowedKnowledge) return {};
    if (narrowedKnowledge.length >= knowledgeScopeSources.length) return {};
    return { runtime_knowledge_scope: [...narrowedKnowledge] };
  }, [knowledgeScopeSources.length, narrowedKnowledge]);

  const activeScenario = selectedScenario;
  const handleSelectScenario = useCallback(
    (scenario: ScenarioId) => {
      selectScenario(scenario);
      setTemplateResetKey((key) => key + 1);
    },
    [selectScenario],
  );

  const selectedTags: SelectedTag[] = activeBinding.tags.map((tag) => ({
    id: tag.id,
    label:
      tag.kind === "task"
        ? (selectedSkill?.name ?? selectedTask?.label ?? tag.text)
        : tag.text,
  }));

  useEffect(() => {
    setPendingTemplate(activeBinding?.promptTemplate ?? null);
  }, [activeBinding?.promptTemplate]);

  const allowedSkillNames = useMemo(() => {
    if (!selectedPill) return undefined;
    // The selected Agent's dependency closure: the published config lists its
    // Skill dependencies (name/slug/resource id all match). While the details
    // are still loading, fall back to the scenario chips; a loaded Agent with
    // no Skill dependencies owns an empty closure — the backend rejects any
    // other skill with skill_outside_agent_closure.
    if (selectedAgentDetails) return selectedAgentDetails.skills ?? [];
    return getChipsByPill(selectedPill.scenarioId, selectedPill.agentSlug).map(
      (chip) => chip.skillName,
    );
  }, [selectedAgentDetails, selectedPill]);

  const selectionBinding = useMemo(
    () =>
      buildScenarioSubmissionBinding({
        baseContext: settings.context,
        selectedPill,
        selectedChip,
        agent: selectedAgent,
        agentDetails: selectedAgentDetails,
        skills,
        connectorName: selectedConnector,
      }),
    [
      selectedAgent,
      selectedAgentDetails,
      settings.context,
      selectedPill,
      selectedChip,
      selectedConnector,
      skills,
    ],
  );
  const selectionContext = selectionBinding.valid
    ? selectionBinding.context
    : { ...settings.context };

  // Keep the identity current during render so pending preparation can detect
  // thread switches and project-scope changes immediately.
  const submissionIdentityRef = useRef({ threadId, projectParam });
  submissionIdentityRef.current = { threadId, projectParam };

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
  const prepareProjectThread = useCallback(async () => {
    if (!isNewThread || !projectParam) {
      return;
    }
    const submissionIdentity = { threadId, projectParam };
    try {
      await createThread(threadId, projectParam);
      void queryClient.invalidateQueries({
        queryKey: INFINITE_THREADS_QUERY_KEY_PREFIX,
      });
    } catch (error) {
      // Any failure (e.g. the project was deleted/archived between page load
      // and submit): do NOT submit unassigned. Reject so the composer keeps
      // the text for a retry.
      toast.error(t.projects.projectUnavailable);
      throw error;
    }
    // Stricter than the shared fence: an identity change between prepare and
    // dispatch drops the continuation even when no navigation unmounted the
    // view.
    const currentIdentity = submissionIdentityRef.current;
    if (
      currentIdentity.threadId !== submissionIdentity.threadId ||
      currentIdentity.projectParam !== submissionIdentity.projectParam
    ) {
      throw new Error("thread-submission-stale");
    }
  }, [isNewThread, projectParam, queryClient, t, threadId]);

  const handleRemoveTag = useCallback(
    (id: string) => {
      if (id === `agent:${selectedPill?.agentSlug}` && selectedPill) {
        togglePill(selectedPill.agentSlug);
        setPendingTemplate(null);
      } else if (id === `task:${selectedChip?.taskId}` && selectedChip) {
        toggleChip(selectedChip.taskId);
        setPendingTemplate(null);
      }
    },
    [selectedChip, selectedPill, toggleChip, togglePill],
  );

  useEffect(() => {
    resetSelection();
    setPendingTemplate(null);
  }, [threadId, resetSelection]);

  const initializedAgentRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isNewThread || !requestedAgent || agents.length === 0) return;
    const initializationKey = `${threadId}:${requestedAgent}`;
    if (initializedAgentRef.current === initializationKey) return;

    const agent = agents.find(
      (item) =>
        item.resource_id === requestedAgent ||
        item.slug === requestedAgent ||
        item.name === requestedAgent,
    );
    const agentSlug = agent?.slug ?? agent?.name ?? requestedAgent;
    const isConfiguredAgent =
      getChipsByPill("daily", agentSlug).length > 0 ||
      getChipsByPill("creative", agentSlug).length > 0 ||
      getChipsByPill("professional", agentSlug).length > 0;
    if (!isConfiguredAgent) return;

    selectAgent(agentSlug);
    initializedAgentRef.current = initializationKey;
  }, [agents, isNewThread, requestedAgent, selectAgent, threadId]);
  const threadTokenUsage = useThreadTokenUsage(
    isNewThread || isMock ? undefined : threadId,
    { enabled: tokenUsageEnabled && !isMock },
  );
  const backendTokenUsage = threadTokenUsageToTokenUsage(threadTokenUsage.data);
  const mountedRef = useRef(false);
  useSpecificChatMode();

  useEffect(() => {
    mountedRef.current = true;
  }, []);

  // The page-level wiring seam (stream, welcome state, redirect, stop/
  // branch/regenerate, turn-submit controller); this route contributes the
  // scenario selection as the lazy-thread pre-create, the admission guard,
  // and the run-request context.
  const {
    thread,
    pendingUsageMessages,
    isUploading,
    isHistoryLoading,
    hasMoreHistory,
    loadMoreHistory,
    isWelcomeMode,
    threadMetadata,
    branchPending,
    turnSubmit,
    handleStop,
    handleEditAndRegenerate,
    handleBranchTurn,
  } = useThreadPage({
    threadId,
    isNewThread,
    isMock,
    setThreadId,
    setIsNewThread,
    context: selectionContext,
    threadPath: pathOfThread,
    prepareSubmit: async () => {
      const created = await getAPIClient().threads.create({
        metadata: {
          agent_name: selectedPill?.agentSlug,
        },
      });
      return { threadId: created.thread_id };
    },
    admit: () => {
      if (selectionBinding.valid) {
        return true;
      }
      toast.error(selectionBinding.reason);
      return false;
    },
    extraContext: () =>
      selectionBinding.valid
        ? { ...selectionBinding.context, ...knowledgeScopeContext }
        : undefined,
    // Project-scoped pre-create on the turn-submit fence; the project param
    // is the scope so a scope change invalidates an in-flight submission.
    prepare: prepareProjectThread,
    scopeKey: projectParam,
  });

  const tokenUsageInlineMode = tokenUsageEnabled
    ? localSettings.tokenUsage.inlineMode
    : "off";
  const hasTodos = (thread.values.todos?.length ?? 0) > 0;
  const { enabled: browserControlEnabled } = useBrowserControlEnabled();
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

  return (
    <ThreadContext.Provider value={{ thread, isMock }}>
      <SidecarProvider
        parentThreadId={threadId}
        context={settings.context}
        isMock={isMock}
      >
        <ChatBox threadId={threadId} browserEnabled={browserEnabled}>
          <div className="workbench-conversation relative flex size-full min-h-0 justify-between">
            <header
              className={cn(
                "workbench-conversation-header absolute top-0 right-0 left-0 flex h-12 shrink-0 items-center px-4",
                isWelcomeMode
                  ? "bg-background/0 z-40 backdrop-blur-none"
                  : "bg-background/80 z-30 shadow-xs backdrop-blur",
              )}
            >
              {!isMock && <SidebarTrigger className="md:hidden" />}
              <div className="type-body flex w-full min-w-0 items-center font-medium">
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
              </div>
              <div className="flex items-center gap-2">
                <TokenUsageIndicator
                  threadId={isNewThread ? undefined : threadId}
                  backendUsage={backendTokenUsage}
                  enabled={tokenUsageEnabled}
                  messages={thread.messages}
                  pendingMessages={pendingUsageMessages}
                  preferences={localSettings.tokenUsage}
                  onPreferencesChange={(preferences) =>
                    setLocalSettings("tokenUsage", preferences)
                  }
                />
                {!isNewThread && !isMock && (
                  <ThreadBackgroundTasks threadId={threadId} />
                )}
                {!isNewThread && !isMock && (
                  <ThreadScheduledTasksLink threadId={threadId} />
                )}
                <SidecarTrigger />
                {browserEnabled && <BrowserTrigger />}
                <ExportTrigger threadId={threadId} />
                <ArtifactTrigger />
              </div>
            </header>
            <main
              className={cn(
                "workbench-conversation-main flex min-h-0 max-w-full grow flex-col",
                isWelcomeMode && "overflow-y-auto",
              )}
            >
              {!isWelcomeMode && (
                <div className="flex min-h-0 flex-1 justify-center">
                  <MessageList
                    className="size-full pt-10"
                    testId="main-message-list"
                    threadId={threadId}
                    thread={thread}
                    enableConversationOutline
                    paddingBottom={MESSAGE_LIST_DEFAULT_PADDING_BOTTOM}
                    hasMoreHistory={hasMoreHistory}
                    loadMoreHistory={loadMoreHistory}
                    isHistoryLoading={isHistoryLoading}
                    tokenUsageInlineMode={tokenUsageInlineMode}
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
              )}
              <div
                className={cn(
                  "relative z-30 flex shrink-0 justify-center px-4",
                  // Keep welcome content clear of the fixed header and center
                  // its inner stack in the flex-growing composer row.
                  isWelcomeMode ? "flex-1 pt-12 pb-0" : "pb-4",
                )}
              >
                <div
                  className={cn(
                    "relative w-full max-w-(--container-width-md)",
                    isWelcomeMode && "my-auto",
                  )}
                >
                  {isWelcomeMode && (
                    <div
                      className="workbench-home flex flex-col items-center"
                      data-testid="workbench-home"
                    >
                      <Welcome mode={settings.context.mode} />
                      <div
                        className="workbench-quick-entry-module"
                        data-testid="workbench-quick-entry-module"
                      >
                        <p className="workbench-module-guide workbench-scenario-guide">
                          <span className="workbench-guide-question">
                            {t.workbench.exploreQuestion}
                          </span>
                          <span className="workbench-guide-answer">
                            {t.workbench.exploreAnswer}
                          </span>
                        </p>
                        <ScenarioTabs
                          selected={activeScenario}
                          onSelect={handleSelectScenario}
                        />
                        <div className="workbench-scenario-cascade">
                          <ScenarioCascadeBar
                            selectedScenario={activeScenario}
                            selectedPill={selectedPill}
                            selectedChip={selectedChip}
                            onTogglePill={togglePill}
                            onToggleChip={toggleChip}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                  {(hasGoal || hasTodos) && (
                    <div className="relative z-0 flex flex-col">
                      {activeGoal && <GoalStatus goal={activeGoal} />}
                      {hasTodos && (
                        <TodoList
                          className="bg-background/5"
                          todos={thread.values.todos ?? []}
                          hidden={false}
                        />
                      )}
                    </div>
                  )}
                  {mountedRef.current ? (
                    <>
                      {isWelcomeMode && (
                        <p className="workbench-module-guide workbench-input-guide">
                          <span className="workbench-guide-question">
                            {t.workbench.focusQuestion}
                          </span>
                          <span className="workbench-guide-answer">
                            {t.workbench.focusAnswer}
                          </span>
                        </p>
                      )}
                      {knowledgeScopeSources.length > 0 && (
                        <div className="mb-2 w-full">
                          <KnowledgeScopeSelector
                            scope={agentKnowledgeScope}
                            loadError={knowledgeScopeError}
                            selected={
                              narrowedKnowledge ??
                              knowledgeScopeSources.map(
                                (source) => source.resource_id,
                              )
                            }
                            onChange={setNarrowedKnowledge}
                          />
                        </div>
                      )}
                      <InputBox
                        className="workbench-input-surface bg-background/5 w-full"
                        isWelcomeMode={isWelcomeMode}
                        showDisclaimer={!isWelcomeMode}
                        threadId={threadId}
                        autoFocus={isWelcomeMode}
                        status={
                          thread.error
                            ? "error"
                            : thread.isLoading
                              ? "streaming"
                              : "ready"
                        }
                        context={selectionContext}
                        allowedSkillNames={allowedSkillNames}
                        pendingTemplate={pendingTemplate}
                        clearInjectedTemplateKey={templateResetKey}
                        onPendingTemplateConsumed={() =>
                          setPendingTemplate(null)
                        }
                        selectedTags={selectedTags}
                        onRemoveTag={handleRemoveTag}
                        disabled={
                          isMock ||
                          env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" ||
                          isUploading
                        }
                        onContextChange={(context, options) => {
                          if (options?.automatic) {
                            resolveThreadContext(threadId, context);
                          } else {
                            setSettings("context", context);
                          }
                        }}
                        onGoalChange={setLocalGoal}
                        onPrepareThread={prepareProjectThread}
                        turnSubmit={turnSubmit}
                        onStop={handleStop}
                      />
                      {isWelcomeMode && (
                        <RecentTaskCards threads={recentThreads} />
                      )}
                    </>
                  ) : (
                    <div
                      aria-hidden="true"
                      className="bg-background/5 h-32 w-full rounded-2xl"
                    />
                  )}
                  {env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true" && (
                    <div className="text-muted-foreground/67 type-body w-full translate-y-12 text-center">
                      {t.common.notAvailableInDemoMode}
                    </div>
                  )}
                </div>
              </div>
              {isWelcomeMode && (
                <p
                  className="text-muted-foreground type-compact z-10 mt-auto px-4 pb-4 text-center leading-4"
                  data-testid="workbench-disclaimer"
                >
                  {t.inputBox.disclaimer}
                </p>
              )}
            </main>
          </div>
        </ChatBox>
      </SidecarProvider>
    </ThreadContext.Provider>
  );
}
