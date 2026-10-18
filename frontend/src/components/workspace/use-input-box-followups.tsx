import type { Message } from "@langchain/langgraph-sdk";
import { XIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Button } from "@/components/ui/button";
import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";
import { useI18n } from "@/core/i18n/hooks";
import { isHiddenFromUIMessage } from "@/core/messages/utils";
import { textOfMessage } from "@/core/threads/utils";

/**
 * Follow-up suggestion lifecycle for the composer: the chips shown after a
 * completed turn, generated from the recent transcript unless the turn was
 * stopped by the user or suggestions are disabled.
 */
export function useInputBoxFollowups({
  threadMessages,
  disabled,
  isMock,
  status,
  threadId,
  contextModelName,
  suggestionsConfigLoaded,
  suggestionsEnabled,
  maxFollowupSuggestions,
}: {
  threadMessages: Message[];
  disabled: boolean | undefined;
  isMock: boolean | undefined;
  status: string;
  threadId: string;
  contextModelName: unknown;
  suggestionsConfigLoaded: boolean;
  suggestionsEnabled: boolean | undefined;
  maxFollowupSuggestions: number;
}) {
  const [followups, setFollowups] = useState<string[]>([]);
  const [followupsHidden, setFollowupsHidden] = useState(false);
  const [followupsLoading, setFollowupsLoading] = useState(false);
  const lastGeneratedForAiIdRef = useRef<string | null>(null);
  const wasStreamingRef = useRef(false);
  // Set when the user stops a streaming turn. Such a turn ends on a
  // half-finished response, so we must NOT generate follow-up suggestions for it.
  const stoppedByUserRef = useRef(false);
  const messagesRef = useRef(threadMessages);

  const resetFollowups = useCallback(() => {
    setFollowups([]);
    setFollowupsHidden(false);
    setFollowupsLoading(false);
  }, []);

  const dismissFollowups = useCallback(() => {
    setFollowupsHidden(true);
  }, []);

  const notifyTurnStoppedByUser = useCallback(() => {
    stoppedByUserRef.current = true;
    setFollowups([]);
    setFollowupsHidden(true);
    setFollowupsLoading(false);
  }, []);

  useEffect(() => {
    messagesRef.current = threadMessages;
  }, [threadMessages]);

  useEffect(() => {
    const streaming = status === "streaming";
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = streaming;
    if (!wasStreaming || streaming) {
      return;
    }

    // The turn was interrupted by the user, so skip generating follow-ups for
    // this half-finished response.
    if (stoppedByUserRef.current) {
      stoppedByUserRef.current = false;
      return;
    }

    if (disabled || isMock) {
      return;
    }

    const lastAi = [...messagesRef.current]
      .reverse()
      .find((m) => m.type === "ai");
    const lastAiId = lastAi?.id ?? null;
    if (!lastAiId || lastAiId === lastGeneratedForAiIdRef.current) {
      return;
    }
    if (!suggestionsConfigLoaded) {
      return;
    }
    lastGeneratedForAiIdRef.current = lastAiId;

    const recent = messagesRef.current
      .filter((m) => m.type === "human" || m.type === "ai")
      .filter((m) => !isHiddenFromUIMessage(m))
      .map((m) => {
        const role = m.type === "human" ? "user" : "assistant";
        const content = textOfMessage(m) ?? "";
        return { role, content };
      })
      .filter((m) => m.content.trim().length > 0)
      .slice(-6);

    if (recent.length === 0) {
      return;
    }

    if (!suggestionsEnabled) {
      setFollowups([]);
      return;
    }

    const controller = new AbortController();
    setFollowupsHidden(false);
    setFollowupsLoading(true);
    setFollowups([]);

    fetch(`${getBackendBaseURL()}/api/threads/${threadId}/suggestions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: recent,
        n: maxFollowupSuggestions,
        model_name: contextModelName ?? undefined,
      }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          return { suggestions: [] as string[] };
        }
        return (await res.json()) as { suggestions?: string[] };
      })
      .then((data) => {
        const suggestions = (data.suggestions ?? [])
          .map((s) => (typeof s === "string" ? s.trim() : ""))
          .filter((s) => s.length > 0)
          .slice(0, maxFollowupSuggestions);
        setFollowups(suggestions);
      })
      .catch(() => {
        setFollowups([]);
      })
      .finally(() => {
        setFollowupsLoading(false);
      });

    return () => controller.abort();
  }, [
    contextModelName,
    disabled,
    isMock,
    maxFollowupSuggestions,
    status,
    suggestionsConfigLoaded,
    suggestionsEnabled,
    threadId,
  ]);

  return {
    followups,
    followupsLoading,
    followupsHidden,
    resetFollowups,
    dismissFollowups,
    notifyTurnStoppedByUser,
  };
}

/** The centered follow-up suggestion chips with their lone close button. */
export function FollowupsBar({
  loading,
  suggestions,
  onSelect,
  onDismiss,
}: {
  loading: boolean;
  suggestions: string[];
  onSelect: (suggestion: string) => void;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="flex items-center justify-center pb-1">
      <div className="flex items-center gap-2">
        {loading ? (
          <div className="text-muted-foreground bg-background/80 type-compact rounded-full border px-4 py-1.5 backdrop-blur-sm">
            {t.inputBox.followupLoading}
          </div>
        ) : (
          <Suggestions className="w-fit items-center">
            {suggestions.map((s) => (
              <Suggestion
                key={s}
                className="py-1.5"
                suggestion={s}
                onClick={() => onSelect(s)}
              />
            ))}
            <Button
              aria-label={t.common.close}
              className="text-foreground type-compact h-auto cursor-pointer rounded-full px-2.5 py-1.5 font-normal"
              variant="outline"
              size="sm"
              type="button"
              onClick={onDismiss}
            >
              <XIcon className="size-4" />
            </Button>
          </Suggestions>
        )}
      </div>
    </div>
  );
}
