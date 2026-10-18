import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { TextInputContext } from "@/components/ai-elements/prompt-input";
import type { Translations } from "@/core/i18n/locales";
import { polishInputDraft } from "@/core/input-polish/api";

import { canPolishInput, isAbortError } from "./input-box-helpers";

/**
 * The AI input-polish flow: request lifecycle with abort/sequence fencing,
 * the polishing flag the composer overlay renders, and the one-shot undo that
 * restores the original text.
 */
export function useInputBoxPolish({
  textInput,
  locale,
  threadId,
  status,
  isComposerDisabled,
  isMockThread,
  slashSkillQuery,
  t,
  setPromptHistoryValue,
  resetHistoryBrowse,
}: {
  textInput: TextInputContext;
  locale: string;
  threadId: string;
  status: string;
  isComposerDisabled: boolean;
  isMockThread: boolean;
  slashSkillQuery: string | null;
  t: Translations;
  setPromptHistoryValue: (value: string) => void;
  resetHistoryBrowse: () => void;
}) {
  const inputPolishRequestRef = useRef<{
    controller: AbortController | null;
    sequence: number;
  }>({
    controller: null,
    sequence: 0,
  });
  const [polishingInput, setPolishingInput] = useState(false);
  const [inputPolishUndo, setInputPolishUndo] = useState<{
    originalText: string;
    rewrittenText: string;
  } | null>(null);

  const abortInputPolishRequest = useCallback(() => {
    inputPolishRequestRef.current.controller?.abort();
    inputPolishRequestRef.current.controller = null;
    inputPolishRequestRef.current.sequence += 1;
    setPolishingInput(false);
  }, []);

  useEffect(() => {
    return () => abortInputPolishRequest();
  }, [abortInputPolishRequest, threadId]);

  const inputPolishUndoAvailable =
    !polishingInput &&
    inputPolishUndo !== null &&
    (textInput.value ?? "") === inputPolishUndo.rewrittenText;
  const inputPolishDisabled =
    isComposerDisabled ||
    isMockThread ||
    polishingInput ||
    (!inputPolishUndoAvailable &&
      (status === "streaming" ||
        slashSkillQuery !== null ||
        !canPolishInput(textInput.value ?? "")));

  const handlePolishInput = useCallback(async () => {
    if (inputPolishDisabled) {
      return;
    }

    const originalText = textInput.value ?? "";
    const controller = new AbortController();
    inputPolishRequestRef.current.controller?.abort();
    const sequence = inputPolishRequestRef.current.sequence + 1;
    inputPolishRequestRef.current = {
      controller,
      sequence,
    };
    setPolishingInput(true);

    try {
      const result = await polishInputDraft(
        {
          text: originalText,
          locale,
          thread_id: threadId,
        },
        { signal: controller.signal },
      );

      const isCurrentRequest =
        inputPolishRequestRef.current.controller === controller &&
        inputPolishRequestRef.current.sequence === sequence &&
        !controller.signal.aborted;
      if (!isCurrentRequest || (textInput.value ?? "") !== originalText) {
        return;
      }

      const rewrittenText = result.rewritten_text.trim();
      if (!rewrittenText || !result.changed) {
        toast.info(t.inputBox.inputPolishNoChanges);
        return;
      }

      // Applying the rewrite replaces the draft outside the textarea change
      // handler, so clear any in-progress history browse state; otherwise a
      // stale index would let the next ArrowDown overwrite the rewrite.
      resetHistoryBrowse();
      setPromptHistoryValue(rewrittenText);
      setInputPolishUndo({
        originalText,
        rewrittenText,
      });
    } catch (error) {
      const isCurrentRequest =
        inputPolishRequestRef.current.controller === controller &&
        inputPolishRequestRef.current.sequence === sequence;
      if (isAbortError(error) || !isCurrentRequest) {
        return;
      }
      toast.error(
        error instanceof Error ? error.message : t.inputBox.inputPolishFailed,
      );
    } finally {
      if (
        inputPolishRequestRef.current.controller === controller &&
        inputPolishRequestRef.current.sequence === sequence
      ) {
        inputPolishRequestRef.current.controller = null;
        setPolishingInput(false);
      }
    }
  }, [
    inputPolishDisabled,
    locale,
    resetHistoryBrowse,
    setPromptHistoryValue,
    t.inputBox.inputPolishFailed,
    t.inputBox.inputPolishNoChanges,
    textInput,
    threadId,
  ]);

  const handleUndoInputPolish = useCallback(() => {
    if (!inputPolishUndoAvailable || inputPolishUndo === null) {
      return;
    }
    resetHistoryBrowse();
    setPromptHistoryValue(inputPolishUndo.originalText);
    setInputPolishUndo(null);
  }, [
    inputPolishUndo,
    inputPolishUndoAvailable,
    resetHistoryBrowse,
    setPromptHistoryValue,
  ]);

  return {
    polishingInput,
    inputPolishUndo,
    inputPolishUndoAvailable,
    inputPolishDisabled,
    abortInputPolishRequest,
    handlePolishInput,
    handleUndoInputPolish,
    setInputPolishUndo,
  };
}
