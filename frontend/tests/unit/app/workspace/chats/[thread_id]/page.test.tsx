import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

const {
  mockUseThreadChat,
  mockUseSpecificChatMode,
  mockLastInputBoxProps,
  mockLastScenarioCascadeProps,
  mockUseAgents,
  mockUseAgent,
  mockUseSkills,
  mockUseThreads,
  mockUseThreadPage,
  mockLastMessageListProps,
  mockEnvValues,
  mockSetSettings,
  mockResolveThreadContext,
  mockCreateThread,
  mockToastError,
  mockInfiniteThreadsQueryKey,
} = vi.hoisted(() => ({
  mockUseThreadChat: vi.fn().mockReturnValue({
    threadId: "test-thread",
    setThreadId: vi.fn(),
    isNewThread: false,
    setIsNewThread: vi.fn(),
    isMock: false,
  }),
  mockUseSpecificChatMode: vi.fn(),
  mockLastInputBoxProps: { current: null as any },
  mockLastScenarioCascadeProps: { current: null as any },
  mockUseAgents: vi.fn().mockReturnValue({ agents: [] }),
  mockUseAgent: vi.fn().mockReturnValue({ agent: null }),
  mockUseSkills: vi.fn().mockReturnValue({ skills: [] }),
  mockUseThreads: vi.fn().mockReturnValue({ data: [] }),
  mockUseThreadPage: vi.fn(),
  mockLastMessageListProps: { current: null as any },
  mockEnvValues: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" },
  mockSetSettings: vi.fn(),
  mockResolveThreadContext: vi.fn(),
  mockCreateThread: vi.fn(),
  mockToastError: vi.fn(),
  mockInfiniteThreadsQueryKey: ["threads", "infinite-test-prefix"],
}));

let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
  useParams: () => ({ thread_id: "test-thread" }),
  usePathname: () => "/workspace/chats/test-thread",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      common: {
        loading: "Loading...",
        notAvailableInDemoMode: "Not available in demo",
      },
      workbench: {
        recentTasks: "最近任务",
        reviewQuestion: "工作复盘？",
        reviewAnswer: "iDeer带你回到过去",
        defaultTaskType: "对话任务",
        defaultStatus: "进行中",
        exploreQuestion: "方向不明？",
        exploreAnswer: "iDeer帮你找对帮手",
        focusQuestion: "目标明确？",
        focusAnswer: "iDeer帮你落地实现",
      },
      inputBox: { disclaimer: "内容由AI生成，重要信息请务必核查" },
      sidebar: { scheduledTasks: "Scheduled tasks" },
      projects: { projectUnavailable: "会话创建失败，请稍后重试" },
      chats: {
        archiveDescription: "该会话已归档",
        archivedChats: "已归档",
        restoreChat: "恢复会话",
      },
      scenarios: {
        daily: "日常办公",
        creative: "创意设计",
        professional: "专业任务",
      },
    },
  }),
}));

vi.mock("@/components/workspace/chats", () => ({
  ChatBox: ({ children }: any) => <div data-testid="chat-box">{children}</div>,
  useSpecificChatMode: () => mockUseSpecificChatMode(),
  useThreadChat: () => mockUseThreadChat(),
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

vi.mock("@/components/ui/sidebar", () => ({
  SidebarTrigger: (props: any) => (
    <button data-testid="sidebar-trigger" {...props} />
  ),
}));

vi.mock("@/components/workspace/input-box", () => ({
  InputBox: (props: any) => {
    mockLastInputBoxProps.current = props;
    return (
      <div>
        <div
          data-testid="input-box"
          data-welcome-mode={String(props.isWelcomeMode)}
          data-disabled={String(props.disabled)}
        />
        {props.showDisclaimer !== false && (
          <p data-testid="input-disclaimer">内容由AI生成，重要信息请务必核查</p>
        )}
      </div>
    );
  },
}));

vi.mock("@/components/workspace/messages", () => ({
  MessageList: (props: any) => {
    mockLastMessageListProps.current = props;
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

vi.mock("@/components/workspace/token-usage-indicator", () => ({
  TokenUsageIndicator: () => <div data-testid="token-usage" />,
}));

vi.mock("@/components/workspace/welcome", () => ({
  Welcome: (props: any) => <div data-testid="welcome" />,
}));

vi.mock("@/components/workspace/scenario", () => ({
  ScenarioCascadeBar: (props: any) => {
    mockLastScenarioCascadeProps.current = props;
    return (
      <button
        data-testid="scenario-cascade-bar"
        onClick={() => props.onTogglePill("office-docs")}
      />
    );
  },
}));

vi.mock("@/core/models/hooks", () => ({
  useModels: () => ({ tokenUsageEnabled: false }),
}));

vi.mock("@/core/agents/hooks", () => ({
  useAgents: () => mockUseAgents(),
  useAgent: (...args: unknown[]) => mockUseAgent(...args),
}));

vi.mock("@/core/skills/hooks", () => ({
  useSkills: () => mockUseSkills(),
}));

vi.mock("@/core/settings", () => ({
  useLocalSettings: () => [{ tokenUsage: { inlineMode: "off" } }, vi.fn()],
  useThreadSettings: () => [{ context: { mode: "flash" } }, mockSetSettings],
}));

vi.mock("@/core/settings/store", () => ({
  resolveThreadContext: (...args: unknown[]) =>
    mockResolveThreadContext(...args),
}));

vi.mock("sonner", async (importOriginal) => {
  const original = await importOriginal<typeof import("sonner")>();
  return {
    ...original,
    toast: {
      ...original.toast,
      error: (...args: Parameters<typeof original.toast.error>) =>
        mockToastError(...args),
    },
  };
});

vi.mock("@/core/threads/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/core/threads/api")>()),
  createThread: (...args: unknown[]) => mockCreateThread(...args),
}));

vi.mock("@/core/threads/hooks", () => ({
  useThreadTokenUsage: () => ({ data: null }),
  useThreads: () => mockUseThreads(),
  INFINITE_THREADS_QUERY_KEY_PREFIX: mockInfiniteThreadsQueryKey,
}));

vi.mock("@/core/threads/token-usage", () => ({
  threadTokenUsageToTokenUsage: () => ({}),
}));

vi.mock("@/core/threads/utils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/core/threads/utils")>()),
  textOfMessage: (message: any) =>
    typeof message?.content === "string" ? message.content : null,
  pathOfThread: (thread: string | { thread_id: string }) =>
    `/workspace/chats/${typeof thread === "string" ? thread : thread.thread_id}`,
  titleOfThread: (thread: { thread_id: string }) => thread.thread_id,
}));

vi.mock("@/env", () => ({
  env: mockEnvValues,
}));

vi.mock("@/lib/utils", () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(" "),
}));

// The page seam (core/threads/use-thread-page) owns the stream wiring,
// welcome state, empty-thread redirect, stop/branch/regenerate, and the
// turn-submit controller; those assertions live in
// tests/unit/core/threads/use-thread-page.test.tsx. This file asserts the
// page is a correct view over the hook: the fixture reaches the right props,
// and the page contributes its scenario selection through the seam's ports.
function threadPageFixture(overrides: Record<string, any> = {}) {
  return {
    thread: {
      messages: [],
      isLoading: false,
      isThreadLoading: false,
      error: null,
      values: {},
      stop: vi.fn().mockResolvedValue(undefined),
      getMessagesMetadata: vi.fn(),
    },
    pendingUsageMessages: [],
    sendMessage: vi.fn().mockResolvedValue(undefined),
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

vi.mock("@/core/threads/use-thread-page", () => ({
  useThreadPage: (...args: any[]) => mockUseThreadPage(...args),
}));

// A relative import: vite's resolver mangles the "@" alias for paths
// containing bracketed (glob-special) segments like [thread_id].
import ChatPage from "../../../../../../src/app/workspace/chats/[thread_id]/page";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatPage", () => {
  beforeEach(() => {
    mockSearchParams = new URLSearchParams();
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: false,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseThreadPage.mockReturnValue(threadPageFixture());
    mockLastInputBoxProps.current = null;
    mockLastScenarioCascadeProps.current = null;
    mockLastMessageListProps.current = null;
    mockUseSkills.mockReturnValue({ skills: [] });
    mockUseThreads.mockReturnValue({ data: [] });
  });

  test("renders chat box", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  test("renders message list", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
  });

  test("renders thread title", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("thread-title")).toBeInTheDocument();
  });

  test("renders input box placeholder", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    const placeholder = document.querySelector('[aria-hidden="true"]');
    expect(placeholder).toBeInTheDocument();
  });

  test("renders token usage indicator", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("token-usage")).toBeInTheDocument();
  });

  test("renders export trigger", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("export-trigger")).toBeInTheDocument();
  });

  test("renders artifact trigger", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("artifact-trigger")).toBeInTheDocument();
  });

  test("does not render todo list when no todos", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("todo-list")).not.toBeInTheDocument();
  });

  test("renders todo list when todos exist", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: false,
          error: null,
          values: { todos: [{ id: "1", text: "Task 1", done: false }] },
          stop: vi.fn(),
        },
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("todo-list")).toBeInTheDocument();
  });

  test("renders with mock thread", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "mock-thread",
      setThreadId: vi.fn(),
      isNewThread: false,
      setIsNewThread: vi.fn(),
      isMock: true,
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
    expect(screen.getByTestId("message-list")).toBeInTheDocument();
  });

  test("renders with thread error state", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: false,
          error: "Connection failed",
          values: {},
          stop: vi.fn(),
        },
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  test("renders with loading thread state", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({
        thread: {
          messages: [],
          isLoading: true,
          error: null,
          values: {},
          stop: vi.fn(),
        },
      }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("chat-box")).toBeInTheDocument();
  });

  test("renders InputBox after re-render when mounted", () => {
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("input-box")).not.toBeInTheDocument();
    expect(
      document.querySelector('div[aria-hidden="true"]'),
    ).toBeInTheDocument();
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("input-box")).toBeInTheDocument();
    expect(
      document.querySelector('div[aria-hidden="true"]'),
    ).not.toBeInTheDocument();
  });

  test("calls useSpecificChatMode on render", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(mockUseSpecificChatMode).toHaveBeenCalled();
  });

  test("new chat defaults the task workbench to the creative scenario", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastScenarioCascadeProps.current.selectedScenario).toBe(
      "creative",
    );
  });

  test("preselects the configured Agent from the new-chat URL", () => {
    mockSearchParams = new URLSearchParams("agent=fault-zeroing");
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [{ slug: "fault-zeroing", resource_id: "fault-resource-id" }],
    });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastScenarioCascadeProps.current.selectedScenario).toBe(
      "professional",
    );
    expect(mockLastInputBoxProps.current.selectedTags).toEqual([
      { id: "agent:fault-zeroing", label: "故障归零" },
    ]);
  });

  test("resolves a legacy resource UUID and selects its configured Agent", () => {
    mockSearchParams = new URLSearchParams("agent=fault-resource-id");
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [
        {
          slug: "fault-zeroing",
          name: "故障归零专家",
          resource_id: "fault-resource-id",
        },
      ],
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastInputBoxProps.current.selectedTags).toEqual([
      { id: "agent:fault-zeroing", label: "故障归零" },
    ]);
  });

  test("resolves a legacy display name and selects its configured Agent", () => {
    mockSearchParams = new URLSearchParams("agent=故障归零专家");
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [
        {
          slug: "fault-zeroing",
          name: "故障归零专家",
          resource_id: "fault-resource-id",
        },
      ],
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastInputBoxProps.current.selectedTags).toEqual([
      { id: "agent:fault-zeroing", label: "故障归零" },
    ]);
  });

  test("does not overwrite a manual Agent selection after URL initialization", () => {
    mockSearchParams = new URLSearchParams("agent=fault-zeroing");
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [{ slug: "fault-zeroing", resource_id: "fault-resource-id" }],
    });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => {
      mockLastScenarioCascadeProps.current.onTogglePill("code-dev");
    });

    expect(mockLastInputBoxProps.current.selectedTags).toEqual([
      { id: "agent:code-dev", label: "代码开发" },
    ]);
  });

  test("uses the selected Agent pill label inside the input", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole("tab", { name: "日常办公" }).click());
    act(() => screen.getByTestId("scenario-cascade-bar").click());

    act(() => {
      mockLastScenarioCascadeProps.current.onToggleChip("word-editor");
    });

    expect(mockLastInputBoxProps.current.selectedTags).toEqual([
      { id: "agent:office-docs", label: "办公文档" },
      { id: "task:word-editor", label: "Word 创建编辑" },
    ]);
  });

  test("uses the skill display name for a selected task tag", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseSkills.mockReturnValue({
      skills: [
        {
          slug: "anthropic-docx",
          name: "Word 文档助手",
          enabled: true,
        },
      ],
    });
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole("tab", { name: "日常办公" }).click());
    act(() => screen.getByTestId("scenario-cascade-bar").click());
    act(() => {
      mockLastScenarioCascadeProps.current.onToggleChip("word-editor");
    });

    expect(mockLastInputBoxProps.current.selectedTags).toContainEqual({
      id: "task:word-editor",
      label: "Word 文档助手",
    });
  });

  test("does not render the retired quick-entry row", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(
      screen.queryByTestId("workbench-quick-entries"),
    ).not.toBeInTheDocument();
  });

  test("loads selected Agent details after the selection hook initializes", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [{ slug: "office-docs", resource_id: "agent-resource-id" }],
    });
    mockUseAgent.mockReturnValue({
      agent: { skills: ["skill-resource-id"] },
    });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole("tab", { name: "日常办公" }).click());
    act(() => screen.getByTestId("scenario-cascade-bar").click());

    expect(mockUseAgent).toHaveBeenLastCalledWith("agent-resource-id");
    expect(mockLastInputBoxProps.current.allowedSkillNames).toEqual([
      "skill-resource-id",
    ]);
    // The expert session keeps the slash skill entry available; the Agent
    // closure in `allowedSkillNames` is what limits which skills are offered.
    expect(
      mockLastInputBoxProps.current.skillInvocationEnabled,
    ).toBeUndefined();
  });

  test("treats a selected Agent without skills as an empty skill closure", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [{ slug: "office-docs", resource_id: "agent-resource-id" }],
    });
    mockUseAgent.mockReturnValue({ agent: { skills: null } });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole("tab", { name: "日常办公" }).click());
    act(() => screen.getByTestId("scenario-cascade-bar").click());

    // A loaded Agent with no Skill dependencies owns an empty closure: the
    // backend rejects any skill invocation (skill_outside_agent_closure).
    expect(mockLastInputBoxProps.current.allowedSkillNames).toEqual([]);
  });

  test("passes canonical Agent and Skill resource IDs in the selection context", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseAgents.mockReturnValue({
      agents: [{ slug: "office-docs", resource_id: "agent-resource-id" }],
    });
    mockUseSkills.mockReturnValue({
      skills: [
        {
          slug: "anthropic-docx",
          name: "anthropic-docx",
          resource_id: "skill-resource-id",
        },
      ],
    });
    mockUseAgent.mockReturnValue({ agent: { skills: ["skill-resource-id"] } });

    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => screen.getByRole("tab", { name: "日常办公" }).click());
    act(() => screen.getByTestId("scenario-cascade-bar").click());
    act(() => {
      mockLastScenarioCascadeProps.current.onToggleChip("word-editor");
    });

    expect(mockLastInputBoxProps.current.context).toMatchObject({
      agent_resource_id: "agent-resource-id",
      skill_resource_id: "skill-resource-id",
    });
  });

  test("preserves a connector selected from the capability center", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
      selectedConnector: "server-1",
    });

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastInputBoxProps.current.context).toMatchObject({
      connector_name: "server-1",
    });
  });

  // --- seam contract: the page forwards identity and its scenario binding ---
  test("forwards the thread identity to the page seam", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "client-thread-id",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.threadId).toBe("client-thread-id");
    expect(seamArgs.isNewThread).toBe(true);
    expect(seamArgs.isMock).toBe(false);
  });

  test("hands the scenario selection binding to the seam's submit ports", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.threadPath("created-1")).toBe("/workspace/chats/created-1");
    expect(seamArgs.prepareSubmit).toBeDefined();
    // The default (no selection) binding is valid and contributes the base
    // context; the admission guard accepts it.
    expect(seamArgs.admit!()).toBe(true);
    expect(seamArgs.extraContext!()).toMatchObject({ mode: "flash" });
  });

  test("forwards the hook's controller and handlers to the composer and list", () => {
    const fixture = threadPageFixture();
    mockUseThreadPage.mockReturnValue(fixture);
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    // The composer mounts after the first paint (mountedRef hydration guard).
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastInputBoxProps.current.turnSubmit).toBe(fixture.turnSubmit);
    expect(mockLastInputBoxProps.current.onStop).toBe(fixture.handleStop);
    expect(mockLastMessageListProps.current.onEditAndRegenerateMessage).toBe(
      fixture.handleEditAndRegenerate,
    );
    expect(mockLastMessageListProps.current.onBranchTurn).toBe(
      fixture.handleBranchTurn,
    );
    // The page renders the welcome layout the seam owns.
    expect(mockLastInputBoxProps.current.isWelcomeMode).toBe(false);
  });

  test("gates message-list editing while a branch mutation is in flight", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ branchPending: true }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    expect(mockLastMessageListProps.current.canEdit).toBe(false);
    expect(mockLastMessageListProps.current.canBranch).toBe(false);
  });

  test("static website only mode shows demo message and disables input", () => {
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "true";
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Not available in demo")).toBeInTheDocument();
    expect(mockLastInputBoxProps.current.disabled).toBe(true);
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "false";
  });

  test("input is disabled when isMock is true", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: false,
      setIsNewThread: vi.fn(),
      isMock: true,
    });

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(mockLastInputBoxProps.current.disabled).toBe(true);
  });

  test("input is disabled when isUploading is true", () => {
    mockUseThreadPage.mockReturnValue(threadPageFixture({ isUploading: true }));

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(mockLastInputBoxProps.current.disabled).toBe(true);
  });

  test("renders the task-first workbench content in welcome mode", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("workbench-home")).toBeInTheDocument();
    const quickEntry = screen.getByTestId("workbench-quick-entry-module");
    expect(quickEntry).toContainElement(screen.getByTestId("scenario-tabs"));
    expect(quickEntry).toContainElement(
      screen.getByTestId("scenario-cascade-bar"),
    );
  });

  test("does not render retired workbench content after send", () => {
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("workbench-home")).not.toBeInTheDocument();
  });

  test("renders Welcome component in welcome mode", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("welcome")).toBeInTheDocument();
    expect(mockLastInputBoxProps.current.isWelcomeMode).toBe(true);
  });

  test("does not render Welcome component when not in welcome mode", () => {
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("welcome")).not.toBeInTheDocument();
    expect(mockLastInputBoxProps.current.isWelcomeMode).toBe(false);
  });

  test("places the welcome disclaimer after recent tasks and keeps it without history", () => {
    mockUseThreadPage.mockReturnValue(
      threadPageFixture({ isWelcomeMode: true }),
    );
    mockUseThreadChat.mockReturnValue({
      threadId: "test-thread",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseThreads.mockReturnValue({
      data: [
        {
          thread_id: "recent-thread",
          values: { messages: [] },
          metadata: { title: "Recent task" },
          context: {},
        },
      ],
    });

    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const recentTasks = screen.getByRole("region", { name: "最近任务" });
    const disclaimer = screen.getByText("内容由AI生成，重要信息请务必核查");
    expect(recentTasks.compareDocumentPosition(disclaimer)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(
      screen.getByTestId("workbench-home").closest("main")?.lastElementChild,
    ).toBe(screen.getByTestId("workbench-disclaimer"));
    expect(screen.getByRole("link", { name: /recent-thread/ })).toHaveAttribute(
      "href",
      "/workspace/chats/recent-thread",
    );
    expect(
      screen.queryByTestId("workbench-recent-chats"),
    ).not.toBeInTheDocument();

    mockUseThreads.mockReturnValue({ data: [] });
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole("region", { name: "最近任务" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("内容由AI生成，重要信息请务必核查"),
    ).toBeInTheDocument();
  });

  // --- 03-B1: automatic context fallback must not write the account preference ---
  test("routes automatic context changes to the thread fallback resolver, not the settings write", () => {
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => {
      mockLastInputBoxProps.current.onContextChange(
        { mode: "deep" },
        { automatic: true },
      );
    });
    expect(mockResolveThreadContext).toHaveBeenCalledWith("test-thread", {
      mode: "deep",
    });
    expect(mockSetSettings).not.toHaveBeenCalled();
  });

  test("writes explicit context selections to the thread settings", () => {
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    act(() => {
      mockLastInputBoxProps.current.onContextChange({ mode: "deep" });
    });
    expect(mockSetSettings).toHaveBeenCalledWith("context", { mode: "deep" });
    expect(mockResolveThreadContext).not.toHaveBeenCalled();
  });

  // --- 03-D1: project-scoped pre-create wired through the seam's prepare port ---
  test("wires the project pre-create as the seam prepare port scoped to the project param", () => {
    mockSearchParams = new URLSearchParams("project=proj-1");
    mockUseThreadChat.mockReturnValue({
      threadId: "client-thread-id",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    const client = new QueryClient();
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );
    rerender(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    expect(seamArgs.scopeKey).toBe("proj-1");
    expect(seamArgs.prepare).toBeDefined();
    // The goal path pre-creates through the same callback as the seam port.
    expect(mockLastInputBoxProps.current.onPrepareThread).toBe(
      seamArgs.prepare,
    );
  });

  test("prepare pre-creates the thread with the project and invalidates the threads cache", async () => {
    mockSearchParams = new URLSearchParams("project=proj-1");
    mockUseThreadChat.mockReturnValue({
      threadId: "client-thread-id",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockCreateThread.mockResolvedValue({ thread_id: "client-thread-id" });
    const client = new QueryClient();
    const invalidateSpy = vi
      .spyOn(client, "invalidateQueries")
      .mockResolvedValue(undefined as never);
    render(
      <QueryClientProvider client={client}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    await act(async () => {
      await seamArgs.prepare();
    });
    expect(mockCreateThread).toHaveBeenCalledWith(
      "client-thread-id",
      "proj-1",
    );
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: mockInfiniteThreadsQueryKey,
    });
  });

  test("prepare is a no-op without a project scope", async () => {
    mockSearchParams = new URLSearchParams();
    mockUseThreadChat.mockReturnValue({
      threadId: "client-thread-id",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    await act(async () => {
      await seamArgs.prepare();
    });
    expect(mockCreateThread).not.toHaveBeenCalled();
  });

  test("prepare failure reports the project as unavailable and rethrows", async () => {
    mockSearchParams = new URLSearchParams("project=proj-1");
    mockUseThreadChat.mockReturnValue({
      threadId: "client-thread-id",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockCreateThread.mockRejectedValueOnce(new Error("backend down"));
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );

    const seamArgs = mockUseThreadPage.mock.calls.at(-1)![0];
    await expect(seamArgs.prepare()).rejects.toThrow("backend down");
    expect(mockToastError).toHaveBeenCalledWith("会话创建失败，请稍后重试");
    expect(mockCreateThread).toHaveBeenCalledWith(
      "client-thread-id",
      "proj-1",
    );
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
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: "恢复会话" })).toBeInTheDocument();
  });

  test("does not mount the archive header for a new thread", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "new",
      setThreadId: vi.fn(),
      isNewThread: true,
      setIsNewThread: vi.fn(),
      isMock: false,
    });
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
  });

  test("does not mount the archive header in mock mode", () => {
    mockUseThreadChat.mockReturnValue({
      threadId: "mock-thread",
      setThreadId: vi.fn(),
      isNewThread: false,
      setIsNewThread: vi.fn(),
      isMock: true,
    });
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
  });

  test("does not mount the archive header in static website only mode", () => {
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "true";
    mockUseThreadPage.mockReturnValue(archivedThreadPageFixture());
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ChatPage />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole("button", { name: "恢复会话" }),
    ).not.toBeInTheDocument();
    mockEnvValues.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "false";
  });
});
