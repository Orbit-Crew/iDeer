/**
 * Thread page — the shared wiring of the three chat routes (spec: 2026-10-03
 * architecture deepening, candidate 4).
 *
 * One hook owns what the showcase chat, the workspace chat, and the agent
 * chat routes each assembled: the stream wiring (identity gating, thread
 * adoption, finish notifications), the welcome-mode state, the empty-thread
 * redirect, and the stop/branch/regenerate handlers, plus the view's
 * turn-submit controller on the shared fence. The routes keep their own JSX
 * and hero differences and consume this hook as their single page seam;
 * the upstream route files see only call-site replacement.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/core/i18n/hooks";
import { useNotification } from "@/core/notification/hooks";
import { env } from "@/env";

import { useBranchThread, useThreadMetadata, useThreadStream } from "./hooks";
import { createTurnSubmitGate, useViewTurnSubmit } from "./turn-submit";
import { textOfMessage } from "./utils";

/** The page-incremental inputs a chat route contributes to the shared wiring. */
export type UseThreadPageArgs = {
  /** Thread identity from the route's chat-mode hook. */
  threadId: string;
  isNewThread: boolean;
  isMock: boolean;
  setThreadId: (threadId: string) => void;
  setIsNewThread: (isNewThread: boolean) => void;
  /** Run context for the stream (settings or the page's selection binding). */
  context: Parameters<typeof useThreadStream>[0]["context"];
  /**
   * Route path for a thread id — the one URL policy this page uses for
   * thread adoption (`history.replaceState`), the empty-thread redirect,
   * and branch navigation.
   */
  threadPath: (threadId: string) => string;
  /** Lazy-thread pre-create on the stream module (workbench/agent routes). */
  prepareSubmit?: Parameters<typeof useThreadStream>[0]["prepareSubmit"];
  /** Turn-submit port: pre-dispatch preparation (project thread pre-create). */
  prepare?: () => Promise<void>;
  /** Turn-submit port: page admission guard (false drops the send). */
  admit?: () => boolean;
  /** Turn-submit port: run-request context (selection/agent binding). */
  extraContext?: () => Record<string, unknown> | undefined;
  /**
   * Extra invalidation scope for the submission fence cleanup (e.g. the
   * new-chat project param, which can change without a thread-id change).
   */
  scopeKey?: string | null;
};

export function useThreadPage({
  threadId,
  isNewThread,
  isMock,
  setThreadId,
  setIsNewThread,
  context,
  threadPath,
  prepareSubmit,
  prepare,
  admit,
  extraContext,
  scopeKey,
}: UseThreadPageArgs) {
  const router = useRouter();
  const { t } = useI18n();
  const { showNotification } = useNotification();

  // `isNewThread` tracks whether the backend has the thread yet — gates the
  // SDK's history fetch (see issue #2746).  `isWelcomeMode` is the visual
  // welcome layout (centered input, hero, quick actions); we flip it to false
  // the moment the user submits so the UI animates immediately, even though
  // `isNewThread` stays true until the backend actually creates the thread.
  const [isWelcomeMode, setIsWelcomeMode] = useState(isNewThread);
  // Keep the welcome layout in sync when navigating between threads (sidebar
  // clicks, "new chat" button).  Submitting flips the layout via the stream's
  // onSend below — `isNewThread` stays true until onStart, so this effect is
  // harmless during the submit transition.
  useEffect(() => {
    setIsWelcomeMode(isNewThread);
  }, [isNewThread]);

  // The shared turn-submit fence of this view: opened by the controller
  // below (composer submit chain) and joined by useThreadStream's send
  // paths, so duplicate submissions are fenced in exactly one place.
  const turnSubmitGate = useMemo(() => createTurnSubmitGate(), []);

  const stream = useThreadStream({
    threadId: isNewThread ? undefined : threadId,
    // Keep the client-visible thread id flowing into the stream hooks so
    // optimistic messages and live-message attribution stay attached to the
    // view while `threadId` itself is gated on backend thread creation.
    displayThreadId: threadId,
    context,
    isMock,
    turnSubmitGate,
    prepareSubmit,
    onThreadCreated: (createdThreadId) => {
      setThreadId(createdThreadId);
      setIsNewThread(false);
      history.replaceState(null, "", threadPath(createdThreadId));
    },
    // onSend only animates the UI; do NOT flip `isNewThread` here — the
    // LangGraph SDK eagerly fetches /history the moment it receives a
    // thread id and assumes the thread exists on the backend (issue #2746).
    onSend: () => {
      setIsWelcomeMode(false);
    },
    onStart: (createdThreadId) => {
      setThreadId(createdThreadId);
      setIsNewThread(false);
      // ! Important: Never use next.js router for navigation in this case,
      // otherwise it will cause the thread to re-mount and lose all states.
      // Use native history API instead.
      history.replaceState(null, "", threadPath(createdThreadId));
    },
    onFinish: (state) => {
      if (document.hidden || !document.hasFocus()) {
        let body = "Conversation finished";
        const lastMessage = state.messages.at(-1);
        if (lastMessage) {
          const textContent = textOfMessage(lastMessage);
          if (textContent) {
            body =
              textContent.length > 200
                ? textContent.substring(0, 200) + "..."
                : textContent;
          }
        }
        showNotification(state.title, { body });
      }
    },
  });

  // The canonical-title metadata query; keeping it on in mock mode is what
  // lets a rename reach the header (the mock implements the single-thread
  // GET and the rename's updateState write-back).
  const threadMetadata = useThreadMetadata(threadId, {
    enabled: !isNewThread,
    isMock,
  });

  // A bookmarked/expired thread id has no metadata; fall back to a fresh
  // chat instead of an eternal empty transcript.
  const hasThreadMessages = stream.thread.messages.length > 0;
  useEffect(() => {
    if (
      !isNewThread &&
      !isMock &&
      threadMetadata.data == null &&
      !threadMetadata.isLoading &&
      !threadMetadata.isFetching &&
      !stream.isHistoryLoading &&
      !stream.hasMoreHistory &&
      !hasThreadMessages
    ) {
      router.replace(threadPath("new"));
    }
  }, [
    hasThreadMessages,
    isNewThread,
    isMock,
    router,
    stream.hasMoreHistory,
    stream.isHistoryLoading,
    threadMetadata.data,
    threadMetadata.isFetching,
    threadMetadata.isLoading,
    threadPath,
  ]);

  // Turn-submit controller: owns the message submit chain (duplicate fence,
  // draft policy, attachment pre-uploads, lifecycle) on top of the stream
  // module's send; the page contributes its admission/prepare/context ports.
  const turnSubmit = useViewTurnSubmit({
    gate: turnSubmitGate,
    sendMessage: stream.sendMessage,
    prepare,
    admit,
    extraContext,
  });

  // The cleanup runs when the conversation switches on a persisted route
  // (sidebar navigation keeps the page mounted), when the view's scope
  // changes, or on unmount: a navigation during the pre-dispatch await must
  // not let the stale continuation start a run for the abandoned
  // conversation.
  useEffect(() => {
    return () => {
      turnSubmit.invalidate();
    };
  }, [turnSubmit, threadId, scopeKey]);

  const handleStop = useCallback(async () => {
    await stream.thread.stop();
  }, [stream.thread]);

  const handleRegenerate = useCallback(
    (messageId: string, supersededMessageIds: string[]) =>
      stream.regenerateMessage(threadId, messageId, supersededMessageIds),
    [stream, threadId],
  );

  const handleEditAndRegenerate = useCallback(
    (messageId: string, replacementText: string) =>
      stream.editAndRegenerateMessage(threadId, messageId, replacementText),
    [stream, threadId],
  );

  const branchThread = useBranchThread();
  const handleBranchTurn = useCallback(
    async (messageId: string, messageIds: string[]) => {
      if (
        isNewThread ||
        isMock ||
        env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY === "true"
      ) {
        return;
      }

      try {
        const response = await branchThread.mutateAsync({
          threadId,
          messageId,
          messageIds,
        });
        toast.success(t.conversation.branchCreated);
        router.push(threadPath(response.thread_id));
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : t.conversation.branchFailed,
        );
      }
    },
    [branchThread, isMock, isNewThread, router, t, threadId, threadPath],
  );

  return {
    ...stream,
    isWelcomeMode,
    threadMetadata,
    /** Branch mutation in flight (message-list edit/branch gating). */
    branchPending: branchThread.isPending,
    turnSubmitGate,
    turnSubmit,
    handleStop,
    handleRegenerate,
    handleEditAndRegenerate,
    handleBranchTurn,
  };
}

export type ThreadPage = ReturnType<typeof useThreadPage>;
