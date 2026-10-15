import type { Message } from "@langchain/langgraph-sdk";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { TextInputContext } from "@/components/ai-elements/prompt-input";
import type { SkillSelection } from "@/core/skills/selection";
import { textOfMessage } from "@/core/threads/utils";
import { isIMEComposing } from "@/lib/ime";

/**
 * Prompt history browsing: the deduplicated list of the user's past messages
 * plus the Alt-free ArrowUp/ArrowDown navigation over it. The browse cursor is
 * shared mutable state — any composer mutation (send, polish, voice, template)
 * resets it through `resetHistoryBrowse` so a stale index can't overwrite the
 * newer text.
 */
export function useInputBoxPromptHistory({
  threadMessages,
  textInput,
  selectedSlashSkill,
  textareaRef,
}: {
  threadMessages: Message[];
  textInput: TextInputContext;
  selectedSlashSkill: SkillSelection;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const promptHistoryIndexRef = useRef<number | null>(null);
  const promptHistoryDraftRef = useRef("");

  const resetHistoryBrowse = useCallback(() => {
    promptHistoryIndexRef.current = null;
    promptHistoryDraftRef.current = "";
  }, []);

  const promptHistory = useMemo(() => {
    const history: string[] = [];
    for (const message of threadMessages) {
      if (message.type !== "human") {
        continue;
      }
      const additionalKwargs = message.additional_kwargs;
      if (
        additionalKwargs &&
        typeof additionalKwargs === "object" &&
        Reflect.get(additionalKwargs, "hide_from_ui") === true
      ) {
        continue;
      }
      const text = textOfMessage(message)?.trim();
      if (!text) {
        continue;
      }
      if (history.at(-1) !== text) {
        history.push(text);
      }
    }
    return history;
  }, [threadMessages]);

  useEffect(() => {
    const currentIndex = promptHistoryIndexRef.current;
    if (currentIndex !== null && currentIndex >= promptHistory.length) {
      promptHistoryIndexRef.current = null;
      promptHistoryDraftRef.current = "";
    }
  }, [promptHistory.length]);

  const setPromptHistoryValue = useCallback(
    (value: string) => {
      textInput.setInput(value);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea) {
          return;
        }
        textarea.focus();
        textarea.setSelectionRange(value.length, value.length);
      });
    },
    [textInput, textareaRef],
  );

  const handlePromptHistoryKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLElement>) => {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        isIMEComposing(event) ||
        selectedSlashSkill ||
        promptHistory.length === 0 ||
        (event.key !== "ArrowUp" && event.key !== "ArrowDown")
      ) {
        return;
      }

      const currentValue = textInput.value ?? "";
      const currentHistoryIndex = promptHistoryIndexRef.current;
      const isBrowsingHistory = currentHistoryIndex !== null;

      if (!isBrowsingHistory && currentValue.length > 0) {
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        const nextIndex = isBrowsingHistory
          ? Math.max(currentHistoryIndex - 1, 0)
          : promptHistory.length - 1;
        if (!isBrowsingHistory) {
          promptHistoryDraftRef.current = currentValue;
        }
        promptHistoryIndexRef.current = nextIndex;
        setPromptHistoryValue(promptHistory[nextIndex] ?? "");
        return;
      }

      if (!isBrowsingHistory) {
        return;
      }

      event.preventDefault();
      if (currentHistoryIndex >= promptHistory.length - 1) {
        promptHistoryIndexRef.current = null;
        setPromptHistoryValue(promptHistoryDraftRef.current);
        promptHistoryDraftRef.current = "";
        return;
      }

      const nextIndex = currentHistoryIndex + 1;
      promptHistoryIndexRef.current = nextIndex;
      setPromptHistoryValue(promptHistory[nextIndex] ?? "");
    },
    [promptHistory, selectedSlashSkill, setPromptHistoryValue, textInput.value],
  );

  return {
    promptHistory,
    resetHistoryBrowse,
    setPromptHistoryValue,
    handlePromptHistoryKeyDown,
  };
}
