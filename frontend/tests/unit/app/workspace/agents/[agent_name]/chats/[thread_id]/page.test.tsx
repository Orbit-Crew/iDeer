import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const { mockEnvValues, mockResolveThreadContext } = vi.hoisted(() => ({
  mockEnvValues: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" },
  mockResolveThreadContext: vi.fn(),
}));

const mockStopFn = vi.fn();
const mockSendMessage = vi.fn();
const mockSetThreadId = vi.fn();
const mockSetIsNewThread = vi.fn();
const mockSetLocalSettings = vi.fn();
const mockSetSettings = vi.fn();
const mockRouterPush = vi.fn();
const mockRouterReplace = vi.fn();
let agentNameParam = "test-agent";

const { mockUseAgent, mockUseThreadChat, mockUseThreadPage } = vi.hoisted(
  () => ({
    mockUseAgent: vi.fn(),
    mockUseThreadChat: vi.fn(),
    mockUseThreadPage: vi.fn(),
  }),
);

let lastInputBoxProps: any = {};
let lastMessageListProps: any = {};
let tokenUsageEnabledFlag = false;

// The page seam (core/threads/use-thread-page) owns the stream wiring,
// welcome state, empty-thread redirect, and stop/regenerate behavior; those
// assertions live in tests/unit/core/threads/use-thread-page.test.tsx. This
// file asserts the page is a correct view over the hook: the fixture it
// returns reaches the right props, and the page contributes its agent
// binding through the seam's ports.
function threadPageFixture(overrides: Record<string, any> = {}) {
  return {
    thread: {
      messages: [],
      isLoading: false,
      isThreadLoading: false,
      error: null,
      values: {},
      stop: mockStopFn,
      getMessagesMetadata: vi.fn(),
    },
    pendingUsageMessages: [],
    sendMessage: mockSendMessage,
    isUploading: false,
    isHistoryLoading: false,
    hasMoreHistory: false,
    loadMoreHistory: vi.fn(),
    isWelcomeMode: false,
    threadMetadata: {
      data: { values: { title: "Existing" } },
      isLoading: false,
      isFetching: false,
    },
    branchPending: false,
    turnSubmit: {
      submit: vi.fn().mockResolvedValue(undefined),
      hasPendingSubmission: vi.fn().mockReturnValue(false),
    },
    handleStop: vi.fn().mockResolvedValue(undefined),
    handleRegenerate: vi.fn(),
    handleEditAndRegenerate: vi.fn(),
    handleBranchTurn: vi.fn(),
    ...overrides,
  };
}

vi.mock("next/navigation", () => ({
  useParams: () => ({ agent_name: agentNameParam }),
  useRouter: () => ({ push: mockRouterPush, replace: mockRouterReplace }),
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      common: {
        loading: "Loading...",
        notAvailableInDemoMode: "Not available in demo",
      },
      agents: {
        newChat: "New Chat",
        skilledAt: (skills: string[]) => `擅长：${skills.join("、")}`,
      },
      projects: { projectUnavailable: "会话创建失败，请稍后重试" },
      chats: {
        archiveDescription: "该会话已归档",
        archivedChats: "已归档",
        restoreChat: "恢复会话",
      },
    },
  }),
}));

vi.mock("@/core/settings/store", () => ({
  resolveThreadContext: (...args: unknown[]) =>
    mockResolveThreadContext(...args),
}));

vi.mock("@/core/agents", () => ({
  useAgent: (...args: any[]) => mockUseAgent(...args),
}));

vi.mock("@/components/workspace/chats", () => ({
  ChatBox: ({ children }: any) => <div data-testid="chat-box">{children}</div>,
  useThreadChat: () => mockUseThreadChat(),
  useSpecificChatMode: () => {},
}));

vi.mock("@/components/ai-elements/prompt-input", () => ({
  PromptInputProvider: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("@/components/workspace/artifacts", () => ({
  ArtifactTrigger: () => <div data-testid="artifact-trigger" />,
}));

vi.mock("@/components/workspace/export-trigger", () => ({
  ExportTrigger: () => <div data-testid="export-trigger" />,
}));

vi.mock("@/components/workspace/input-box", () => ({
  InputBox: (props: any) => {
    lastInputBoxProps = props;
    return (
      <div
        data-testid="input-box"
        data-welcome-mode={String(props.isWelcomeMode)}
        data-disabled={String(!!props.disabled)}
        data-status={props.status}
      />
    );
  },
}));

vi.mock("@/components/workspace/messages", () => ({
  MessageList: (props: any) => {
    lastMessageListProps = props;
    return <div data-testid="message-list">Messages</div>;
  },
  MESSAGE_LIST_DEFAULT_PADDING_BOTTOM: 24,
}));

vi.mock("@/components/workspace/messages/context", () => ({
  ThreadContext: { Provider: ({ children }: any) => <div>{children}</div> },
}));

vi.mock("@/components/workspace/thread-title", () => ({
  ThreadTitle: () => <div data-testid="thread-title">Thread Title</div>,
}));

vi.mock("@/components/workspace/todo-list", () => ({
  TodoList: (props: any) => <div data-testid="todo-list" />,
}));

let lastTokenUsageProps: any = {};
vi.mock("@/components/workspace/token-usage-indicator", () => ({
  TokenUsageIndicator: (props: any) => {
    lastTokenUsageProps = props;
    return <div data-testid="token-usage" />;
  },
}));

vi.mock("@/components/workspace/tooltip", () => ({
  Tooltip: ({ children }: any) => <div>{children}</div>,
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));

vi.mock("@/core/models/hooks", () => ({
  useModels: () => ({ tokenUsageEnabled: tokenUsageEnabledFlag }),
}));

vi.mock("@/core/settings", () => ({
  useLocalSettings: () => [
    { tokenUsage: { inlineMode: "off" } },
    mockSetLocalSettings,
  ],
  useThreadSettings: () => [{ context: { mode: "flash" } }, mockSetSettings],
}));

vi.mock("@/core/threads/hooks", () => ({
  useThreadTokenUsage: () => ({ data: null }),
}));

vi.mock("@/core/threads/token-usage", () => ({
  threadTokenUsageToTokenUsage: () => ({}),
  selectContextUsage: () => null,
}));

vi.mock("@/core/features", () => ({
  useBrowserControlEnabled: () => ({ enabled: false }),
}));

vi.mock("@/components/workspace/sidecar", () => ({
  SidecarProvider: ({ children }: any) => (
    <div data-testid="sidecar-provider">{children}</div>
  ),
  SidecarTrigger: () => <div data-testid="sidecar-trigger" />,
}));

vi.mock("@/components/workspace/thread-background-tasks", () => ({
  ThreadBackgroundTasks: () => <div data-testid="thread-background-tasks" />,
}));

vi.mock("@/components/workspace/thread-subagent-batches", () => ({
  ThreadSubagentBatches: () => <div data-testid="thread-subagent-batches" />,
}));

vi.mock("@/components/workspace/goal-status", () => ({
  GoalStatus: () => <div data-testid="goal-status" />,
}));

vi.mock("@/components/workspace/use-active-goal", () => ({
  useActiveGoal: () => ({
    activeGoal: null,
    hasGoal: false,
    setLocalGoal: vi.fn(),
  }),
}));

vi.mock("@/components/workspace/context-usage-badge", () => ({
  ContextUsageBadge: () => <div data-testid="context-usage-badge" />,
}));

vi.mock("@/components/ui/sidebar", () => ({
  SidebarTrigger: () => <div data-testid="sidebar-trigger" />,
}));

vi.mock("@/env", () => ({
  env: mockEnvValues,
}));

vi.mock("@/lib/utils", () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(" "),
}));

vi.mock("@/core/threads/use-thread-page", () => ({
  useThreadPage: (...args: any[]) => mockUseThreadPage(...args),
}));

import AgentChatPage from "@/app/workspace/agents/[agent_name]/chats/[thread_id]/page";

// The ported archive header (ThreadArchiveStatus → useArchiveThread) mounts a
// react-query mutation, so every render needs a QueryClientProvider like the
// real workspace layout provides.
function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AgentChatPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AgentChatPage", () => {
  beforeEach(() => {
    lastInputBoxProps = {};
    lastTokenUsageProps = {};
    lastMessageListProps = {};
    tokenUsageEnabledFlag = false;
    agentNameParam = "test-agent";
    mockStopFn.mockReset();
    mockSendMessage.mockReset().mockReturnValue(Promise.resolve());
    mockSetThreadId.mockReset();
    mockSetIsNewThread.mockReset();
    mockSetSettings.mockReset();
    mockResolveThreadContext.mockReset();
    mockRouterPush.mockReset();
    mockRouterReplace.mockReset();
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "false";

    mockUseAgent.mockReturnValue({
      agent: { name: "test-agent", description: "A test agent" },
    });
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: mockSetThreadId,
      isNewThread: false,
      setIsNewThread: mockSetIsNewThread,
      isMock: false,
    });
    mockUseThreadPage.mockReturnValue(threadPageFixture());
  });

  test("renders chat box", () => {
    renderPage();
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  test("renders message list", () => {
    renderPage();
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
  });

  test("renders agent name badge", () => {
    renderPage();
    expect(screen.getByText("test-agent")).toBeInTheDocument();
  });

  test("renders new chat button", () => {
    renderPage();
    expect(screen.getByText("New Chat")).toBeInTheDocument();
  });

  test("renders input box", () => {
    renderPage();
    expect(screen.getByTestId("input-box")).toBeInTheDocument();
  });

  test("filters the slash skill panel to the agent's closure skills", () => {
    mockUseAgent.mockReturnValue({
      agent: {
        name: "test-agent",
        skills: ["docx-helper", "skill-resource-id"],
      },
    });
    renderPage();
    expect(lastInputBoxProps.allowedSkillNames).toEqual([
      "docx-helper",
      "skill-resource-id",
    ]);
  });

  test("treats an agent without skills as an empty skill closure", () => {
    mockUseAgent.mockReturnValue({
      agent: { name: "test-agent", skills: null },
    });
    renderPage();
    expect(lastInputBoxProps.allowedSkillNames).toEqual([]);
  });

  test("leaves skills unfiltered while agent details are loading", () => {
    mockUseAgent.mockReturnValue({ agent: null });
    renderPage();
    expect(lastInputBoxProps.allowedSkillNames).toBeUndefined();
  });

  test("renders thread title", () => {
    renderPage();
    expect(screen.getByTestId("thread-title")).toBeInTheDocument();
  });

  test("renders token usage indicator when token usage is enabled", () => {
    tokenUsageEnabledFlag = true;
    renderPage();
    expect(screen.getByTestId("token-usage")).toBeInTheDocument();
  });

  test("renders the context usage badge when token usage is disabled", () => {
    renderPage();
    expect(screen.getByTestId("context-usage-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("token-usage")).not.toBeInTheDocument();
  });

  test("renders export trigger", () => {
    renderPage();
    expect(screen.getByTestId("export-trigger")).toBeInTheDocument();
  });

  test("renders artifact trigger", () => {
    renderPage();
    expect(screen.getByTestId("artifact-trigger")).toBeInTheDocument();
  });

  test("shows agent name when agent data is available", () => {
    mockUseAgent.mockReturnValue({
      agent: { name: "My Custom Agent", description: "Custom" },
    });
    renderPage();
    expect(screen.getByText("My Custom Agent")).toBeInTheDocument();
  });

  test("shows agent_name param when agent data is null", () => {
    mockUseAgent.mockReturnValue({ agent: null });
    renderPage();
    expect(screen.getByText("test-agent")).toBeInTheDocument();
  });

  test("renders the hook's welcome layout on a new thread", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );
    mockUseThreadChat.mockReturnValue({
      threadId: "new",
      setThreadId: mockSetThreadId,
      isNewThread: true,
      setIsNewThread: mockSetIsNewThread,
      isMock: false,
    });

    renderPage();
    expect(
      screen.getByTestId("input-box").getAttribute("data-welcome-mode"),
    ).toBe("true");
  });

  test("renders conversation layout on an existing thread", () => {
    renderPage();
    expect(
      screen.getByTestId("input-box").getAttribute("data-welcome-mode"),
    ).toBe("false");
  });

  test("renders todo list when todos exist", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: false,
          isThreadLoading: false,
          error: null,
          values: { todos: [{ id: "1", text: "Task 1", done: false }] },
          stop: mockStopFn,
          getMessagesMetadata: vi.fn(),
        },
      }),
    );

    renderPage();
    expect(screen.getByTestId("todo-list")).toBeInTheDocument();
  });

  test("does not render todo list when no todos", () => {
    renderPage();
    expect(screen.queryByTestId("todo-list")).not.toBeInTheDocument();
  });

  // --- seam contract: the page contributes its agent binding ---
  test("scopes the thread URL policy to the agent route with encoded segments", () => {
    agentNameParam = "ops/team";
    renderPage();

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.threadPath("thread/#1")).toBe(
      "/workspace/agents/ops%2Fteam/chats/thread%2F%231",
    );
  });

  test("passes the agent binding as run context and lazy-thread pre-create", () => {
    renderPage();

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.context).toEqual({
      mode: "flash",
      agent_name: "test-agent",
    });
    expect(seamArgs.extraContext!()).toEqual({ agent_name: "test-agent" });
    expect(seamArgs.prepareSubmit).toBeDefined();
    expect(seamArgs.isMock).toBe(false);
  });

  test("forwards the hook's turn-submit controller and stop handler to the composer", () => {
    const fixture = threadPageFixture();
    mockUseThreadPage.mockReturnValue(fixture);
    renderPage();

    expect(lastInputBoxProps.turnSubmit).toBe(fixture.turnSubmit);
    expect(lastInputBoxProps.onStop).toBe(fixture.handleStop);
  });

  test("forwards regenerate handlers to the message list", () => {
    const fixture = threadPageFixture();
    mockUseThreadPage.mockReturnValue(fixture);
    renderPage();

    expect(lastMessageListProps.onRegenerateMessage).toBe(
      fixture.handleRegenerate,
    );
    expect(lastMessageListProps.onEditAndRegenerateMessage).toBe(
      fixture.handleEditAndRegenerate,
    );
  });

  test("input box is disabled when isUploading is true", () => {
    mockUseThreadPage.mockReturnValue(threadPageFixture({ isUploading: true }));

    renderPage();
    expect(screen.getByTestId("input-box").getAttribute("data-disabled")).toBe(
      "true",
    );
  });

  // --- Input not disabled when not uploading ---
  test("input box is not disabled when isUploading is false", () => {
    renderPage();
    expect(screen.getByTestId("input-box").getAttribute("data-disabled")).toBe(
      "false",
    );
  });

  // --- tokenUsageInlineMode when tokenUsageEnabled is false ---
  test("token usage indicator receives inline mode preference", () => {
    tokenUsageEnabledFlag = true;
    renderPage();
    expect(screen.getByTestId("token-usage")).toBeInTheDocument();
    expect(lastTokenUsageProps.preferences).toEqual({
      inlineMode: "off",
    });
  });

  test("renders with isMock=true thread identity", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: mockSetThreadId,
      isNewThread: false,
      setIsNewThread: mockSetIsNewThread,
      isMock: true,
    });

    renderPage();
    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.isMock).toBe(true);
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  test("forwards a new-thread identity to the seam", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "new",
      setThreadId: mockSetThreadId,
      isNewThread: true,
      setIsNewThread: mockSetIsNewThread,
      isMock: false,
    });

    renderPage();
    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.threadId).toBe("new");
    expect(seamArgs.isNewThread).toBe(true);
  });

  // --- thread.isLoading status ---
  test("passes 'streaming' status when thread is loading", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: true,
          isThreadLoading: false,
          error: null,
          values: {},
          stop: mockStopFn,
          getMessagesMetadata: vi.fn(),
        },
      }),
    );

    renderPage();
    expect(screen.getByTestId("input-box").getAttribute("data-status")).toBe(
      "streaming",
    );
  });

  // --- thread.error status ---
  test("passes 'error' status when thread has error", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: false,
          isThreadLoading: false,
          error: new Error("test error"),
          values: {},
          stop: mockStopFn,
          getMessagesMetadata: vi.fn(),
        },
      }),
    );

    renderPage();
    expect(screen.getByTestId("input-box").getAttribute("data-status")).toBe(
      "error",
    );
  });

  // --- normal status ---
  test("passes 'ready' status when not loading and no error", () => {
    renderPage();
    expect(screen.getByTestId("input-box").getAttribute("data-status")).toBe(
      "ready",
    );
  });

  // --- new chat button onClick ---
  test("new chat button navigates to new chat page", () => {
    renderPage();
    const newChatButton = screen.getByText("New Chat").closest("button");
    newChatButton?.click();

    expect(mockRouterPush).toHaveBeenCalledWith(
      "/workspace/agents/test-agent/chats/new",
    );
  });

  // --- onContextChange handler ---
  test("onContextChange updates settings context", () => {
    renderPage();
    lastInputBoxProps.onContextChange({ mode: "deep" });
    expect(mockSetSettings).toHaveBeenCalledWith("context", { mode: "deep" });
  });

  // --- 03-B1: automatic context fallback must not write the account preference ---
  test("routes automatic context changes to the thread fallback resolver, not the settings write", () => {
    renderPage();
    act(() => {
      lastInputBoxProps.onContextChange({ mode: "deep" }, { automatic: true });
    });
    expect(mockResolveThreadContext).toHaveBeenCalledWith("test-thread", {
      mode: "deep",
    });
    expect(mockSetSettings).not.toHaveBeenCalled();
  });

  // --- 03-D2: archived-thread status and restore entry in the page header ---
  const archivedThreadPageFixture = () =>
    threadPageFixture({
      threadMetadata: {
        data: {
          values: { title: "Existing" },
          metadata: { deerflow_archived: true },
        },
        isLoading: false,
        isFetching: false,
      },
    });

  test("mounts the archive status header for a persisted archived thread", () => {
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    renderPage();
    expect(screen.getByRole("button", { name: "恢复会话" })).toBeInTheDocument();
  });

  test("does not mount the archive header for a new thread", () => {
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    mockUseThreadChat.mockReturnValue({
      threadId: "new",
      setThreadId: mockSetThreadId,
      isNewThread: true,
      setIsNewThread: mockSetIsNewThread,
      isMock: false,
    });
    renderPage();
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
  });

  test("does not mount the archive header in mock mode", () => {
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: mockSetThreadId,
      isNewThread: false,
      setIsNewThread: mockSetIsNewThread,
      isMock: true,
    });
    renderPage();
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
  });

  test("does not mount the archive header in static website only mode", () => {
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "true";
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    renderPage();
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
  });

  // --- clarification cards stay answerable in expert chats ---
  test("passes a clarification submit handler that sends a hidden reply", async () => {
    mockSendMessage.mockImplementation(async (...args: unknown[]) => {
      (args[3] as { onSent?: () => void } | undefined)?.onSent?.();
    });
    renderPage();

    expect(typeof lastMessageListProps.onSubmitHumanInput).toBe("function");
    const sent = await lastMessageListProps.onSubmitHumanInput(
      { question: "Which files?" },
      { value: "All reports" },
    );

    expect(sent).toBe(true);
    const [, message, context, options] = mockSendMessage.mock.calls.at(-1)!;
    expect(message).toEqual({
      text: 'For your clarification "Which files?", my answer is: All reports',
      files: [],
    });
    expect(context).toEqual({ agent_name: "test-agent" });
    expect(options.additionalKwargs).toMatchObject({
      hide_from_ui: true,
      human_input_response: { value: "All reports" },
    });
  });

  // --- onPreferencesChange handler ---
  test("onPreferencesChange updates local settings for token usage", () => {
    tokenUsageEnabledFlag = true;
    renderPage();
    lastTokenUsageProps.onPreferencesChange({ inlineMode: "compact" });
    expect(mockSetLocalSettings).toHaveBeenCalledWith("tokenUsage", {
      inlineMode: "compact",
    });
  });
});
