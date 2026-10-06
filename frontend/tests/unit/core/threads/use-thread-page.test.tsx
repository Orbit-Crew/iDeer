import { act, renderHook, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  mockUseThreadStream,
  mockUseThreadMetadata,
  mockUseBranchThread,
  mockShowNotification,
  mockRouterReplace,
  mockRouterPush,
  envState,
} = vi.hoisted(() => ({
  mockUseThreadStream: vi.fn(),
  mockUseThreadMetadata: vi.fn(),
  mockUseBranchThread: vi.fn(),
  mockShowNotification: vi.fn(),
  mockRouterReplace: vi.fn(),
  mockRouterPush: vi.fn(),
  envState: { NEXT_PUBLIC_STATIC_WEBSITE_ONLY: "false" },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush, replace: mockRouterReplace }),
}));

vi.mock("@/core/i18n/hooks", () => ({
  useI18n: () => ({
    t: {
      conversation: {
        branchCreated: "Branch created",
        branchFailed: "Branch failed",
      },
    },
  }),
}));

vi.mock("@/core/notification/hooks", () => ({
  useNotification: () => ({ showNotification: mockShowNotification }),
}));

vi.mock("@/core/threads/hooks", () => ({
  useThreadStream: (...args: unknown[]) => mockUseThreadStream(...args),
  useThreadMetadata: (...args: unknown[]) => mockUseThreadMetadata(...args),
  useBranchThread: () => mockUseBranchThread(),
}));

vi.mock("@/env", () => ({
  env: envState,
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from "sonner";

import { useThreadPage } from "@/core/threads/use-thread-page";

let lastStreamArgs: Record<string, any>;
let streamThread: Record<string, any>;
let streamResult: Record<string, any>;
let metadataState: Record<string, any>;

function mockStreamDefaults() {
  streamThread = {
    messages: [],
    isLoading: false,
    isThreadLoading: false,
    error: null,
    values: {},
    stop: vi.fn().mockResolvedValue(undefined),
    getMessagesMetadata: vi.fn(),
  };
  metadataState = {
    data: { values: { title: "Existing" } },
    isLoading: false,
    isFetching: false,
  };
  mockUseThreadStream.mockImplementation((args: any) => {
    lastStreamArgs = args;
    streamResult = {
      thread: streamThread,
      pendingUsageMessages: [],
      sendMessage: vi.fn().mockResolvedValue(undefined),
      regenerateMessage: vi.fn().mockResolvedValue(undefined),
      editAndRegenerateMessage: vi.fn().mockResolvedValue(undefined),
      isUploading: false,
      isHistoryLoading: false,
      hasMoreHistory: false,
      loadMoreHistory: vi.fn(),
    };
    return streamResult;
  });
  mockUseThreadMetadata.mockImplementation(() => metadataState);
  mockUseBranchThread.mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ thread_id: "branch-thread" }),
    isPending: false,
  });
}

type HookArgs = Parameters<typeof useThreadPage>[0];

function baseArgs(overrides: Partial<HookArgs> = {}): HookArgs {
  return {
    threadId: "test-thread",
    isNewThread: false,
    isMock: false,
    setThreadId: vi.fn(),
    setIsNewThread: vi.fn(),
    context: { mode: "chat" } as any,
    threadPath: (id: string) => `/workspace/chats/${id}`,
    ...overrides,
  };
}

function renderThreadPage(overrides: Partial<HookArgs> = {}) {
  return renderHook((args: HookArgs) => useThreadPage(args), {
    initialProps: baseArgs(overrides),
  });
}

function makeVisible() {
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
}

beforeEach(() => {
  mockStreamDefaults();
  makeVisible();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useThreadPage welcome state", () => {
  it("starts in welcome mode on a new thread", () => {
    const { result } = renderThreadPage({ isNewThread: true });
    expect(result.current.isWelcomeMode).toBe(true);
  });

  it("starts in conversation mode on an existing thread", () => {
    const { result } = renderThreadPage({ isNewThread: false });
    expect(result.current.isWelcomeMode).toBe(false);
  });

  it("flips out of welcome mode when the send starts, without touching isNewThread", () => {
    const setIsNewThread = vi.fn();
    const { result } = renderThreadPage({ isNewThread: true, setIsNewThread });
    expect(result.current.isWelcomeMode).toBe(true);

    act(() => {
      lastStreamArgs.onSend("client-thread");
    });

    expect(result.current.isWelcomeMode).toBe(false);
    expect(setIsNewThread).not.toHaveBeenCalled();
  });

  it("re-syncs the welcome layout when the route switches threads", () => {
    const { result, rerender } = renderThreadPage({ isNewThread: true });
    expect(result.current.isWelcomeMode).toBe(true);

    rerender(baseArgs({ isNewThread: false }));
    expect(result.current.isWelcomeMode).toBe(false);

    rerender(baseArgs({ isNewThread: true }));
    expect(result.current.isWelcomeMode).toBe(true);
  });
});

describe("useThreadPage stream wiring", () => {
  it("gates the backend thread id and keeps the display id flowing while new", () => {
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    renderThreadPage({
      threadId: "client-thread-id",
      isNewThread: true,
      isMock: false,
    });

    expect(lastStreamArgs.threadId).toBeUndefined();
    expect(lastStreamArgs.displayThreadId).toBe("client-thread-id");
    expect(lastStreamArgs.isMock).toBe(false);
    expect(lastStreamArgs.turnSubmitGate).toBeDefined();
    replaceStateSpy.mockRestore();
  });

  it("hands the backend thread id to the stream on an existing thread", () => {
    renderThreadPage({ threadId: "existing", isNewThread: false });
    expect(lastStreamArgs.threadId).toBe("existing");
    expect(lastStreamArgs.displayThreadId).toBe("existing");
  });

  it("passes the page-composed run context and lazy-thread pre-create through", () => {
    const prepareSubmit = async () => ({ threadId: "created" });
    renderThreadPage({ context: { mode: "agent" } as any, prepareSubmit });
    expect(lastStreamArgs.context).toEqual({ mode: "agent" });
    expect(lastStreamArgs.prepareSubmit).toBe(prepareSubmit);
  });

  it("adopts the created thread on stream start through the page URL policy", () => {
    const setThreadId = vi.fn();
    const setIsNewThread = vi.fn();
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    const threadPath = (id: string) => `/workspace/chats/${id}`;
    renderThreadPage({
      isNewThread: true,
      setThreadId,
      setIsNewThread,
      threadPath,
    });

    act(() => {
      lastStreamArgs.onStart("created-thread-123");
    });

    expect(setThreadId).toHaveBeenCalledWith("created-thread-123");
    expect(setIsNewThread).toHaveBeenCalledWith(false);
    expect(replaceStateSpy).toHaveBeenCalledWith(
      null,
      "",
      "/workspace/chats/created-thread-123",
    );
    replaceStateSpy.mockRestore();
  });

  it("routes the agent-flavored thread path through the same adoption policy", () => {
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    renderThreadPage({
      isNewThread: true,
      threadPath: (id: string) => `/workspace/agents/ops/chats/${id}`,
    });

    act(() => {
      lastStreamArgs.onStart("thread/#1");
    });

    expect(replaceStateSpy).toHaveBeenCalledWith(
      null,
      "",
      "/workspace/agents/ops/chats/thread/#1",
    );
    replaceStateSpy.mockRestore();
  });

  it("adopts a lazily pre-created thread identically when creation returns first", () => {
    const setThreadId = vi.fn();
    const setIsNewThread = vi.fn();
    const replaceStateSpy = vi.spyOn(history, "replaceState");
    renderThreadPage({ isNewThread: true, setThreadId, setIsNewThread });

    act(() => {
      lastStreamArgs.onThreadCreated("created-early");
    });

    expect(setThreadId).toHaveBeenCalledWith("created-early");
    expect(setIsNewThread).toHaveBeenCalledWith(false);
    expect(replaceStateSpy).toHaveBeenCalledWith(
      null,
      "",
      "/workspace/chats/created-early",
    );
    replaceStateSpy.mockRestore();
  });
});

describe("useThreadPage finish notification", () => {
  it("stays silent while the document is visible and focused", () => {
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({
        messages: [{ content: "hello" }],
        title: "Test",
      });
    });
    expect(mockShowNotification).not.toHaveBeenCalled();
  });

  it("notifies with the default body when the document is hidden and no text exists", () => {
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({ messages: [], title: "Empty Chat" });
    });
    expect(mockShowNotification).toHaveBeenCalledWith("Empty Chat", {
      body: "Conversation finished",
    });
  });

  it("notifies when hidden even if the document keeps focus", () => {
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    vi.spyOn(document, "hasFocus").mockReturnValue(true);
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({
        messages: [{ content: "result text" }],
        title: "Finished",
      });
    });
    expect(mockShowNotification).toHaveBeenCalledWith("Finished", {
      body: "result text",
    });
  });

  it("notifies with the last message text as the body when hidden", () => {
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({
        messages: [{ content: "hello world" }],
        title: "Chat Done",
      });
    });
    expect(mockShowNotification).toHaveBeenCalledWith("Chat Done", {
      body: "hello world",
    });
  });

  it("truncates long message text in the notification body", () => {
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({
        messages: [{ content: "a".repeat(250) }],
        title: "Done",
      });
    });
    // The body carries the first 200 characters of the final message text.
    expect(mockShowNotification).toHaveBeenCalledWith("Done", {
      body: "a".repeat(200) + "...",
    });
  });

  it("uses the default body when the last message carries no text", () => {
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    renderThreadPage();
    act(() => {
      lastStreamArgs.onFinish({
        messages: [{ content: null }],
        title: "Empty",
      });
    });
    expect(mockShowNotification).toHaveBeenCalledWith("Empty", {
      body: "Conversation finished",
    });
  });
});

describe("useThreadPage empty-thread redirect", () => {
  it("falls back to a fresh chat when a bookmarked thread id resolves to nothing", () => {
    metadataState = { data: null, isLoading: false, isFetching: false };
    renderThreadPage({ threadId: "expired", isNewThread: false });
    expect(mockRouterReplace).toHaveBeenCalledWith("/workspace/chats/new");
  });

  it("redirects through the page URL policy (agent route flavor)", () => {
    metadataState = { data: null, isLoading: false, isFetching: false };
    renderThreadPage({
      threadId: "expired",
      isNewThread: false,
      threadPath: (id: string) => `/workspace/agents/ops/chats/${id}`,
    });
    expect(mockRouterReplace).toHaveBeenCalledWith(
      "/workspace/agents/ops/chats/new",
    );
  });

  it("waits while the metadata query is still resolving", () => {
    metadataState = { data: null, isLoading: true, isFetching: true };
    renderThreadPage({ threadId: "expired", isNewThread: false });
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });

  it("keeps a thread whose history still carries messages", () => {
    metadataState = { data: null, isLoading: false, isFetching: false };
    streamThread.messages = [{ id: "m1", content: "kept" }];
    renderThreadPage({ threadId: "expired", isNewThread: false });
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });

  it("never redirects a brand-new or mock conversation", () => {
    metadataState = { data: null, isLoading: false, isFetching: false };
    renderThreadPage({ threadId: "new", isNewThread: true });
    renderThreadPage({ threadId: "mock", isNewThread: false, isMock: true });
    expect(mockRouterReplace).not.toHaveBeenCalled();
  });
});

describe("useThreadPage stop and regenerate", () => {
  it("stops the active run of the view's thread", async () => {
    const { result } = renderThreadPage();
    await act(async () => {
      await result.current.handleStop();
    });
    expect(streamThread.stop).toHaveBeenCalled();
  });

  it("regenerates a message against the current thread id", async () => {
    const { result } = renderThreadPage({ threadId: "current-thread" });
    const regenerate = streamResult.regenerateMessage;
    await act(async () => {
      await result.current.handleRegenerate("msg-1", ["msg-0"]);
    });
    expect(regenerate).toHaveBeenCalledWith("current-thread", "msg-1", [
      "msg-0",
    ]);
  });

  it("edits and regenerates a message against the current thread id", async () => {
    const { result } = renderThreadPage({ threadId: "current-thread" });
    const editAndRegenerate = streamResult.editAndRegenerateMessage;
    await act(async () => {
      await result.current.handleEditAndRegenerate("msg-1", "fixed text");
    });
    expect(editAndRegenerate).toHaveBeenCalledWith(
      "current-thread",
      "msg-1",
      "fixed text",
    );
  });
});

describe("useThreadPage branch turn", () => {
  it("branches the turn and navigates to the new thread through the URL policy", async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ thread_id: "branch-9" });
    mockUseBranchThread.mockReturnValue({ mutateAsync, isPending: false });
    const { result } = renderThreadPage({ threadId: "current-thread" });

    await act(async () => {
      await result.current.handleBranchTurn("msg-1", ["msg-0", "msg-1"]);
    });

    expect(mutateAsync).toHaveBeenCalledWith({
      threadId: "current-thread",
      messageId: "msg-1",
      messageIds: ["msg-0", "msg-1"],
    });
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith("Branch created");
    expect(mockRouterPush).toHaveBeenCalledWith("/workspace/chats/branch-9");
  });

  it("reports a failed branch through the error toast", async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error("branch rejected"));
    mockUseBranchThread.mockReturnValue({ mutateAsync, isPending: false });
    const { result } = renderThreadPage({ threadId: "current-thread" });

    await act(async () => {
      await result.current.handleBranchTurn("msg-1", ["msg-1"]);
    });

    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("branch rejected");
    expect(mockRouterPush).not.toHaveBeenCalled();
  });

  it("never branches a brand-new or mock conversation", async () => {
    const mutateAsync = vi.fn();
    mockUseBranchThread.mockReturnValue({ mutateAsync, isPending: false });
    const { result: newResult } = renderThreadPage({
      threadId: "new",
      isNewThread: true,
    });
    await act(async () => {
      await newResult.current.handleBranchTurn("msg-1", ["msg-1"]);
    });
    const { result: mockResult } = renderThreadPage({
      threadId: "mock",
      isMock: true,
    });
    await act(async () => {
      await mockResult.current.handleBranchTurn("msg-1", ["msg-1"]);
    });
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("never branches in the static demo mode", async () => {
    envState.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "true";
    try {
      const mutateAsync = vi.fn();
      mockUseBranchThread.mockReturnValue({ mutateAsync, isPending: false });
      const { result } = renderThreadPage({ threadId: "current-thread" });
      await act(async () => {
        await result.current.handleBranchTurn("msg-1", ["msg-1"]);
      });
      expect(mutateAsync).not.toHaveBeenCalled();
    } finally {
      envState.NEXT_PUBLIC_STATIC_WEBSITE_ONLY = "false";
    }
  });
});

describe("useThreadPage turn-submit controller", () => {
  it("dispatches submitted messages through the stream send with the page context", async () => {
    const extraContext = () => ({ agent_name: "ops" });
    const { result } = renderThreadPage({
      threadId: "current-thread",
      extraContext,
    });

    await act(async () => {
      await result.current.turnSubmit.submit({
        threadId: "current-thread",
        message: { text: "hello", files: [] },
      });
    });

    expect(streamResult.sendMessage).toHaveBeenCalledWith(
      "current-thread",
      { text: "hello", files: [] },
      { agent_name: "ops" },
      undefined,
    );
  });

  it("forwards the submit request options so composer metadata reaches the stream send", async () => {
    const { result } = renderThreadPage({ threadId: "current-thread" });
    // The composer's per-send metadata (quotes, references, staged files)
    // must reach the stream send untouched; the lifecycle is owned by the
    // turn-submit module's shared gate instead of riding the options.
    const options = { additionalKwargs: { sidecar_visible_message: true } };

    await act(async () => {
      await result.current.turnSubmit.submit({
        threadId: "current-thread",
        message: { text: "hello", files: [] },
        options,
      });
    });

    expect(streamResult.sendMessage).toHaveBeenCalledWith(
      "current-thread",
      { text: "hello", files: [] },
      undefined,
      options,
    );
  });

  it("shares one duplicate-submission fence between the controller and the stream", () => {
    const { result } = renderThreadPage();
    const gate = result.current.turnSubmitGate;
    // The gate returned for advanced consumers is the same fence the
    // controller opens turns on.
    expect(gate.hasActiveSubmission()).toBe(false);
  });

  it("invalidates the in-flight fence when the conversation switches", async () => {
    const { result, rerender } = renderThreadPage({
      threadId: "thread-a",
    });
    const gate = result.current.turnSubmitGate;
    expect(gate.openTurn({ onSent: vi.fn() })).toBe(true);

    rerender(baseArgs({ threadId: "thread-b" }));
    // The stale turn was invalidated with the old conversation: a fresh
    // submission is accepted again.
    expect(gate.openTurn({ onSent: vi.fn() })).toBe(true);
  });

  it("runs the page's pre-dispatch prepare before the stream send", async () => {
    const order: string[] = [];
    const prepare = vi.fn(async () => {
      order.push("prepare");
    });
    // The stream mock builds a fresh result per render; keep one instrumented
    // sendMessage identity so the dispatch order is observed reliably.
    const sendMessage = vi.fn(async () => {
      order.push("send");
    });
    mockUseThreadStream.mockImplementation((args: any) => {
      lastStreamArgs = args;
      streamResult = {
        thread: streamThread,
        pendingUsageMessages: [],
        sendMessage,
        regenerateMessage: vi.fn().mockResolvedValue(undefined),
        editAndRegenerateMessage: vi.fn().mockResolvedValue(undefined),
        isUploading: false,
        isHistoryLoading: false,
        hasMoreHistory: false,
        loadMoreHistory: vi.fn(),
      };
      return streamResult;
    });
    const { result } = renderThreadPage({
      threadId: "current-thread",
      prepare,
    });

    await act(async () => {
      await result.current.turnSubmit.submit({
        threadId: "current-thread",
        message: { text: "hello", files: [] },
      });
    });

    // The project pre-create (prepare port) must complete before the run
    // request goes out — the sole membership channel for a scoped new chat.
    expect(order).toEqual(["prepare", "send"]);
  });

  it("invalidates an in-flight submission when the view's scope changes without a thread switch", () => {
    const { result, rerender } = renderThreadPage({
      threadId: "thread-a",
      scopeKey: "project-1",
    });
    const gate = result.current.turnSubmitGate;
    expect(gate.openTurn({ onSent: vi.fn() })).toBe(true);

    rerender(baseArgs({ threadId: "thread-a", scopeKey: "project-2" }));
    // The scope change (new-chat project param) invalidated the fence even
    // though the thread id is unchanged: a fresh submission is accepted.
    expect(gate.openTurn({ onSent: vi.fn() })).toBe(true);
  });
});
