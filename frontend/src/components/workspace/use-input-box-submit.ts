import type { ChatStatus } from "ai";
import { useCallback } from "react";
import { toast } from "sonner";

import type {
  PromptInputMessage,
  TextInputContext,
} from "@/components/ai-elements/prompt-input";
import {
  buildConversationReferenceMetadata,
  type ConversationReference,
} from "@/core/conversation-references";
import type { Translations } from "@/core/i18n/locales";
import type { FileInMessage } from "@/core/messages/utils";
import type { AttachProjectDocumentResult } from "@/core/projects/types";
import { buildReferenceMessageMetadata } from "@/core/sidecar";
import {
  clearSelection,
  selectedSkillName,
  submitTextFor,
  type SkillSelection,
} from "@/core/skills/selection";
import type { AgentThreadContext } from "@/core/threads";
import type { ComposerDraft } from "@/core/threads/composer-draft";
import type {
  TurnSubmitController,
  TurnSubmitRequest,
} from "@/core/threads/turn-submit";
import {
  validateUploadLimits,
  type UploadLimitViolation,
  type UploadLimits,
} from "@/core/uploads";

import {
  MAX_GOAL_OBJECTIVE_CHARS,
  buildHiddenConversationQuoteMessage,
  findSuggestionTemplatePlaceholder,
  getInputSubmitAction,
  getResolvedMode,
  isGoalObjectiveTooLong,
  type GoalCommand,
  type GoalRequestState,
} from "./input-box-helpers";
import type { useMaybeSidecar } from "./sidecar";

/**
 * The composer's submit gate: validates upload limits and unresolved
 * suggestion placeholders, routes builtin commands (/goal, /compact, stop),
 * fences thread preparation for goal-set, and assembles the TurnSubmitRequest
 * (quote/conversation-reference metadata, staged project files, and the draft
 * ports the turn-submit lifecycle drives).
 */
export function useInputBoxSubmit({
  threadId,
  status,
  canStopStreaming,
  onStop,
  onPrepareThread,
  onContextChange,
  context,
  selectedModel,
  resolvedModelName,
  sidecar,
  textInput,
  setTextInput,
  selectedSlashSkill,
  setSelectedSlashSkill,
  draftKey,
  latestDraftRef,
  currentDraftViewRef,
  invalidateDraftSaveTimer,
  conversationReferences,
  setConversationReferences,
  projectAttachments,
  setProjectAttachments,
  reportUploadLimitViolations,
  notifyUploadError,
  textareaRef,
  turnSubmit,
  uploadLimits,
  t,
  resetHistoryBrowse,
  resetFollowups,
  setInputPolishUndo,
  notifyTurnStoppedByUser,
  abortVoiceInput,
  goalRequestStateRef,
  handleGoalCommand,
  handleCompactCommand,
}: {
  threadId: string;
  status: ChatStatus;
  canStopStreaming: boolean;
  onStop?: () => void;
  onPrepareThread?: () => void | Promise<void>;
  onContextChange?: (
    context: Partial<
      Omit<
        AgentThreadContext,
        "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
      > & {
        mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
        reasoning_effort?: "minimal" | "low" | "medium" | "high";
      }
    >,
    options?: { automatic: boolean },
  ) => void;
  context: Omit<
    AgentThreadContext,
    "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
  > & {
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
    reasoning_effort?: "minimal" | "low" | "medium" | "high";
  };
  selectedModel: { supports_thinking?: boolean; name?: string } | undefined;
  resolvedModelName: string | undefined;
  sidecar: ReturnType<typeof useMaybeSidecar>;
  textInput: TextInputContext;
  setTextInput: TextInputContext["setInput"];
  selectedSlashSkill: SkillSelection;
  setSelectedSlashSkill: (selection: SkillSelection) => void;
  draftKey: string;
  latestDraftRef: React.RefObject<{
    key: string;
    draft: { text: string; skillName: string | null };
  } | null>;
  currentDraftViewRef: React.RefObject<{
    key: string;
    text: string;
    skillName: string | null;
  }>;
  invalidateDraftSaveTimer: () => void;
  conversationReferences: ConversationReference[];
  setConversationReferences: (
    value:
      | ConversationReference[]
      | ((current: ConversationReference[]) => ConversationReference[]),
  ) => void;
  projectAttachments: AttachProjectDocumentResult[];
  setProjectAttachments: (
    value:
      | AttachProjectDocumentResult[]
      | ((
          current: AttachProjectDocumentResult[],
        ) => AttachProjectDocumentResult[]),
  ) => void;
  reportUploadLimitViolations: (violations: UploadLimitViolation[]) => void;
  notifyUploadError: (error: unknown) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  turnSubmit: TurnSubmitController;
  uploadLimits: UploadLimits | undefined;
  t: Translations;
  resetHistoryBrowse: () => void;
  resetFollowups: () => void;
  setInputPolishUndo: (value: null) => void;
  notifyTurnStoppedByUser: () => void;
  abortVoiceInput: () => void;
  goalRequestStateRef: React.RefObject<GoalRequestState>;
  handleGoalCommand: (command: GoalCommand) => Promise<boolean>;
  handleCompactCommand: () => Promise<void>;
}) {
  const submitThreadMessage = useCallback(
    async (message: PromptInputMessage) => {
      const files = message.files.flatMap((file) =>
        file.file instanceof File ? [file.file] : [],
      );
      const uploadValidation = validateUploadLimits([], files, uploadLimits);
      if (uploadValidation.violations.length > 0) {
        reportUploadLimitViolations(uploadValidation.violations);
        return Promise.reject(new Error("Attachment limits exceeded."));
      }
      const placeholder = findSuggestionTemplatePlaceholder(message.text);
      if (placeholder) {
        toast.warning(t.inputBox.suggestionPlaceholderRequired);
        requestAnimationFrame(() => {
          const textarea = textareaRef.current;
          if (!textarea) {
            return;
          }
          textarea.focus();
          textarea.setSelectionRange(placeholder.start, placeholder.end);
        });
        return Promise.reject(
          new Error("Suggestion template placeholder is unresolved."),
        );
      }
      resetHistoryBrowse();
      setInputPolishUndo(null);
      resetFollowups();
      const quotes = sidecar?.conversationQuotes ?? [];
      const quoteIds = quotes.map((quote) => quote.id);
      const quoteContexts = quotes.map((quote) => quote.context);
      const pendingDraft: ComposerDraft = {
        text: textInput.value ?? "",
        skillName: selectedSkillName(selectedSlashSkill),
      };
      const referenceIds = conversationReferences.map(
        (reference) => reference.threadId,
      );
      // Project-shelf attachments are already ingested thread-side (§9):
      // they join ``additional_kwargs.files`` as completed uploads without a
      // re-upload, and merge with any files uploaded in this send
      // (buildThreadSubmitMessages concatenates the two lists).
      const stagedFiles: FileInMessage[] = projectAttachments.map(
        (attachment) => ({
          filename: attachment.filename,
          size: attachment.size_bytes,
          path: attachment.virtual_path,
          status: "uploaded" as const,
        }),
      );
      const additionalKwargs = {
        ...(quotes.length ? buildReferenceMessageMetadata(quoteContexts) : {}),
        ...(referenceIds.length
          ? buildConversationReferenceMetadata(conversationReferences)
          : {}),
        ...(stagedFiles.length > 0 ? { files: stagedFiles } : {}),
      };
      // The duplicate-submission fence, the submit-chain draft policy
      // (hold/persist/restore/clear), and attachment pre-uploads live in the
      // turn-submit module; the composer contributes its view state (draft
      // ports) and one-time resets (lifecycle) only.
      const submitRequest: TurnSubmitRequest = {
        threadId,
        message,
        options: {
          ...(Object.keys(additionalKwargs).length ? { additionalKwargs } : {}),
          ...(quotes.length
            ? {
                additionalInputMessages: [
                  buildHiddenConversationQuoteMessage({
                    contexts: quoteContexts,
                  }),
                ],
              }
            : {}),
          ...(referenceIds.length
            ? { conversationReferences: referenceIds }
            : {}),
        },
        lifecycle: {
          // Clear one-time state only once the send genuinely proceeds. If
          // the send is dropped by the fence, `onSent` never fires.
          onSent: () => {
            sidecar?.clearConversationQuotes(quoteIds);
          },
          onSendCompleted: () => {
            sidecar?.clearConversationQuotes(quoteIds);
            setConversationReferences([]);
            setProjectAttachments([]);
          },
        },
        draft: {
          key: draftKey,
          pending: pendingDraft,
          tracked: () => latestDraftRef.current,
          visible: () => ({
            key: currentDraftViewRef.current.key,
            draft: {
              text: currentDraftViewRef.current.text,
              skillName: currentDraftViewRef.current.skillName,
            },
          }),
          track: (draft) => {
            latestDraftRef.current = { key: draftKey, draft };
          },
          forget: () => {
            invalidateDraftSaveTimer();
            latestDraftRef.current = null;
          },
          restore: (draft) => {
            setTextInput(draft.text);
            setSelectedSlashSkill(selectedSlashSkill);
          },
        },
        onPreuploadError: notifyUploadError,
      };

      // Guard against submitting before the initial model auto-selection
      // effect has flushed thread settings to storage/state.
      if (resolvedModelName && context.model_name !== resolvedModelName) {
        onContextChange?.(
          {
            ...context,
            model_name: resolvedModelName,
            mode: getResolvedMode(
              context.mode,
              selectedModel?.supports_thinking ?? false,
            ),
          },
          { automatic: true },
        );
        return new Promise<void>((resolve, reject) => {
          setTimeout(() => {
            Promise.resolve(turnSubmit.submit(submitRequest))
              .then(resolve)
              .catch(reject);
          }, 0);
        });
      }

      return turnSubmit.submit(submitRequest);
    },
    [
      context,
      conversationReferences,
      currentDraftViewRef,
      draftKey,
      invalidateDraftSaveTimer,
      latestDraftRef,
      notifyUploadError,
      onContextChange,
      projectAttachments,
      resetFollowups,
      resetHistoryBrowse,
      setConversationReferences,
      setInputPolishUndo,
      setProjectAttachments,
      setSelectedSlashSkill,
      setTextInput,
      reportUploadLimitViolations,
      resolvedModelName,
      selectedSlashSkill,
      selectedModel,
      sidecar,
      textareaRef,
      threadId,
      t.inputBox.suggestionPlaceholderRequired,
      textInput.value,
      turnSubmit,
      uploadLimits,
    ],
  );

  const handleStopStreaming = useCallback(() => {
    // Roles denied runs:cancel must not interrupt the in-progress turn —
    // the Gateway would 403 the cancel anyway. The submit-button click is
    // the only live entry point today (handleSubmit returns early with the
    // pleaseWaitStreaming toast while streaming), but gate in the handler
    // as defense-in-depth so any future stop path is covered too.
    if (!canStopStreaming) {
      return;
    }
    // Mark the in-progress turn as user-interrupted so the next
    // streaming->ready transition does not suggest follow-ups for it.
    notifyTurnStoppedByUser();
    onStop?.();
  }, [canStopStreaming, notifyTurnStoppedByUser, onStop]);

  const handleSubmit = useCallback(
    async (message: PromptInputMessage) => {
      if (status === "streaming") {
        toast.info(t.inputBox.pleaseWaitStreaming);
        return Promise.reject(new Error("streaming"));
      }
      abortVoiceInput();
      const messageWithSlashSkill = selectedSlashSkill
        ? {
            ...message,
            text: submitTextFor(message.text, selectedSlashSkill.name),
          }
        : message;
      const submitAction = getInputSubmitAction({
        text: messageWithSlashSkill.text,
        // Staged project-shelf attachments count exactly like uploaded
        // files: submitThreadMessage maps them into the outgoing message's
        // ``additional_kwargs.files``, so an attachment-only submit must not
        // read as empty, and /goal or /compact must not intercept while an
        // attach chip is present.
        fileCount:
          messageWithSlashSkill.files.length + projectAttachments.length,
        status,
      });
      if (submitAction.kind === "goal") {
        if (
          submitAction.command.kind === "set" &&
          isGoalObjectiveTooLong(submitAction.command.objective)
        ) {
          toast.error(
            t.inputBox.goalTooLong.replace("{max}", () =>
              String(MAX_GOAL_OBJECTIVE_CHARS),
            ),
          );
          // Reject so the composer keeps the user's text for editing instead of
          // clearing it (PromptInput only preserves input on a rejected submit).
          return Promise.reject(new Error("goal-too-long"));
        }
        if (submitAction.command.kind === "set") {
          // A goal-set PUT creates the thread server-side when missing, so a
          // project-scoped new chat must assign membership first. The prepare
          // callback toasts its own failure; reject so the composer keeps the
          // text for a retry instead of issuing an unassigned goal.
          //
          // Fence against conversation switches while preparation runs: the
          // goal PUT registers its AbortController only when it starts, so
          // the thread-change/unmount cleanup cannot cancel an in-flight
          // prepare. Capture the goal-request epoch before the await — the
          // cleanup bumps it via abortGoalRequest — and drop the stale
          // continuation before it can clear the new conversation's composer
          // or launch the abandoned submission.
          const requestEpoch = goalRequestStateRef.current.sequence;
          try {
            await onPrepareThread?.();
          } catch (error) {
            return Promise.reject(
              error instanceof Error
                ? error
                : new Error("thread preparation failed"),
            );
          }
          if (goalRequestStateRef.current.sequence !== requestEpoch) {
            // Reject (not resolve) so PromptInput keeps the current
            // conversation's composer text untouched.
            return Promise.reject(new Error("goal-preparation-stale"));
          }
        }
        resetHistoryBrowse();
        resetFollowups();
        const saved = await handleGoalCommand(submitAction.command);
        // Only start a run when a goal was actually saved; status/clear never run.
        if (saved && submitAction.command.kind === "set") {
          return submitThreadMessage({
            ...message,
            text: submitAction.command.objective,
            files: [],
          });
        }
        return;
      }
      if (submitAction.kind === "compact") {
        return handleCompactCommand();
      }
      if (submitAction.kind === "stop") {
        handleStopStreaming();
        return;
      }
      if (submitAction.kind === "empty") {
        return;
      }
      await submitThreadMessage(messageWithSlashSkill);
      if (selectedSlashSkill) {
        setSelectedSlashSkill(clearSelection());
      }
    },
    [
      abortVoiceInput,
      goalRequestStateRef,
      handleCompactCommand,
      handleGoalCommand,
      handleStopStreaming,
      onPrepareThread,
      projectAttachments.length,
      resetFollowups,
      resetHistoryBrowse,
      selectedSlashSkill,
      setSelectedSlashSkill,
      status,
      submitThreadMessage,
      t.inputBox.goalTooLong,
      t.inputBox.pleaseWaitStreaming,
    ],
  );

  return { submitThreadMessage, handleSubmit, handleStopStreaming };
}
