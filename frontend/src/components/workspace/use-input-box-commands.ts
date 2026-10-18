import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";
import { toast } from "sonner";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
import type { Translations } from "@/core/i18n/locales";
import type { GoalState } from "@/core/threads";
import { compactThreadContext } from "@/core/threads/api";
import { threadTokenUsageQueryKey } from "@/core/threads/token-usage";

import {
  abortGoalRequest,
  beginGoalRequest,
  createGoalRequestState,
  finishGoalRequest,
  isAbortError,
  isCurrentGoalRequest,
  readGoalResponseError,
  type GoalCommand,
  type GoalRequestState,
} from "./input-box-helpers";

/**
 * The builtin slash commands that talk to the thread API: `/goal
 * <objective>|status|clear` and `/compact`. Each owns an AbortController
 * registry keyed by thread so a conversation switch cancels in-flight
 * requests; both clear the composer text on success.
 */
export function useInputBoxCommands({
  threadId,
  isWelcomeMode,
  agentName,
  modelName,
  textInput,
  t,
  onGoalChange,
  resetHistoryBrowse,
  resetFollowups,
}: {
  threadId: string;
  isWelcomeMode: boolean;
  agentName: unknown;
  modelName: unknown;
  textInput: { setInput: (value: string) => void };
  t: Translations;
  onGoalChange?: (goal: GoalState | null) => void;
  resetHistoryBrowse: () => void;
  resetFollowups: () => void;
}) {
  const queryClient = useQueryClient();
  const goalRequestStateRef = useRef<GoalRequestState>(
    createGoalRequestState(),
  );
  const compactRequestStateRef = useRef<GoalRequestState>(
    createGoalRequestState(),
  );

  useEffect(() => {
    const goalRequestState = goalRequestStateRef.current;
    const compactRequestState = compactRequestStateRef.current;
    return () => {
      abortGoalRequest(goalRequestState);
      abortGoalRequest(compactRequestState);
    };
  }, [threadId]);

  const handleGoalCommand = useCallback(
    async (command: GoalCommand): Promise<boolean> => {
      const request = beginGoalRequest(goalRequestStateRef.current, threadId);
      const signal = request.controller.signal;
      try {
        let goal: GoalState | null = null;
        if (command.kind === "status") {
          const response = await fetch(
            `${getBackendBaseURL()}/api/threads/${encodeURIComponent(
              threadId,
            )}/goal`,
            { method: "GET", signal },
          );
          if (!response.ok) {
            throw new Error(await readGoalResponseError(response));
          }
          goal =
            ((await response.json()) as { goal?: GoalState | null }).goal ??
            null;
          if (
            !isCurrentGoalRequest(
              goalRequestStateRef.current,
              request,
              threadId,
            )
          ) {
            return false;
          }
          const objective = goal?.objective;
          toast.info(
            objective !== undefined
              ? // Function replacer so a goal containing `$&`/`$1` isn't
                // interpreted as a replacement pattern.
                t.inputBox.goalActive.replace("{goal}", () => objective)
              : t.inputBox.goalNone,
          );
          onGoalChange?.(goal);
        } else if (command.kind === "clear") {
          const response = await fetch(
            `${getBackendBaseURL()}/api/threads/${encodeURIComponent(
              threadId,
            )}/goal`,
            { method: "DELETE", signal },
          );
          if (!response.ok) {
            throw new Error(await readGoalResponseError(response));
          }
          if (
            !isCurrentGoalRequest(
              goalRequestStateRef.current,
              request,
              threadId,
            )
          ) {
            return false;
          }
          toast.success(t.inputBox.goalCleared);
          onGoalChange?.(null);
        } else {
          const response = await fetch(
            `${getBackendBaseURL()}/api/threads/${encodeURIComponent(
              threadId,
            )}/goal`,
            {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ objective: command.objective }),
              signal,
            },
          );
          if (!response.ok) {
            throw new Error(await readGoalResponseError(response));
          }
          goal =
            ((await response.json()) as { goal?: GoalState | null }).goal ??
            null;
          if (
            !isCurrentGoalRequest(
              goalRequestStateRef.current,
              request,
              threadId,
            )
          ) {
            return false;
          }
          toast.success(t.inputBox.goalSet);
          onGoalChange?.(goal);
        }
        textInput.setInput("");
        return true;
      } catch (error) {
        if (
          isAbortError(error) ||
          !isCurrentGoalRequest(goalRequestStateRef.current, request, threadId)
        ) {
          return false;
        }
        toast.error(
          error instanceof Error ? error.message : t.inputBox.goalFailed,
        );
        return false;
      } finally {
        finishGoalRequest(goalRequestStateRef.current, request);
      }
    },
    [
      onGoalChange,
      t.inputBox.goalActive,
      t.inputBox.goalCleared,
      t.inputBox.goalFailed,
      t.inputBox.goalNone,
      t.inputBox.goalSet,
      textInput,
      threadId,
    ],
  );

  const handleCompactCommand = useCallback(async (): Promise<void> => {
    if (isWelcomeMode) {
      textInput.setInput("");
      toast.info(t.inputBox.compactSkipped);
      return;
    }
    const request = beginGoalRequest(compactRequestStateRef.current, threadId);
    const signal = request.controller.signal;
    try {
      const result = await compactThreadContext(threadId, {
        signal,
        agentName: typeof agentName === "string" ? agentName : null,
        modelName: typeof modelName === "string" ? modelName : null,
      });
      if (
        !isCurrentGoalRequest(compactRequestStateRef.current, request, threadId)
      ) {
        return;
      }
      textInput.setInput("");
      resetHistoryBrowse();
      resetFollowups();

      void queryClient.invalidateQueries({ queryKey: ["thread", threadId] });
      void queryClient.invalidateQueries({
        queryKey: threadTokenUsageQueryKey(threadId),
      });

      if (result.compacted) {
        toast.success(t.inputBox.compactSuccess);
      } else {
        toast.info(t.inputBox.compactSkipped);
      }
    } catch (error) {
      if (
        isAbortError(error) ||
        !isCurrentGoalRequest(compactRequestStateRef.current, request, threadId)
      ) {
        return;
      }
      toast.error(
        error instanceof Error ? error.message : t.inputBox.compactFailed,
      );
    } finally {
      finishGoalRequest(compactRequestStateRef.current, request);
    }
  }, [
    agentName,
    modelName,
    queryClient,
    resetFollowups,
    resetHistoryBrowse,
    t.inputBox.compactFailed,
    t.inputBox.compactSkipped,
    t.inputBox.compactSuccess,
    isWelcomeMode,
    textInput,
    threadId,
  ]);

  return {
    goalRequestStateRef,
    handleGoalCommand,
    handleCompactCommand,
  };
}
