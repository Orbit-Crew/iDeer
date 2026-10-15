"use client";

import type { ChatStatus } from "ai";
import {
  Loader2Icon,
  PaperclipIcon,
  SparklesIcon,
  Undo2Icon,
  XIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type ComponentProps,
  type KeyboardEvent,
} from "react";

import {
  PromptInput,
  PromptInputAttachment,
  PromptInputAttachments,
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputController,
} from "@/components/ai-elements/prompt-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/core/auth/AuthProvider";
import type { ConversationReference } from "@/core/conversation-references";
import { useI18n } from "@/core/i18n/hooks";
import { useModels } from "@/core/models/hooks";
import { useStagedProjectAttachments } from "@/core/projects/composer-attach";
import { useSkills } from "@/core/skills/hooks";
import {
  matchSkills,
  offerableSkills,
  selectedSkillName,
  type SkillSelection,
  type SkillSuggestion,
} from "@/core/skills/selection";
import { DEFAULT_MAX_SUGGESTIONS } from "@/core/suggestions/api";
import { useSuggestionsConfig } from "@/core/suggestions/hooks";
import type { AgentThreadContext, GoalState } from "@/core/threads";
import { prepareTaskInputInsertion } from "@/core/threads/task-input";
import type { TurnSubmitController } from "@/core/threads/turn-submit";
import { useUploadLimits } from "@/core/uploads";
import { cn } from "@/lib/utils";

import { ConversationReferenceChip } from "./conversation-references/conversation-reference-chip";
import { ReferenceConversationsButton } from "./conversation-references/reference-conversations-button";
import { highlightPlaceholder, focusContentEditableEnd } from "./input-box-dom";
import {
  getGoalObjectiveCounter,
  getLeadingSlashSkillQuery,
  getResolvedMode,
  MAX_SKILL_SUGGESTIONS,
  type InputMode,
} from "./input-box-helpers";
import {
  ComposerModeMenu,
  ComposerReasoningEffortMenu,
} from "./input-box-model-menus";
import { SlashSkillSuggestions } from "./input-box-skill-suggestions";
import {
  AddAttachmentsButton,
  VoiceInputButton,
} from "./input-box-tool-buttons";
import { useThread } from "./messages/context";
import {
  ModelPicker,
  ModelPickerContent,
  ModelPickerTrigger,
} from "./model-picker-content";
import { InlineSelectedTag, type SelectedTag } from "./scenario/selected-tags";
import { ReferenceAttachmentSummary, useMaybeSidecar } from "./sidecar";
import { SkillPicker } from "./slash-overlay";
import { SlashSkillChip } from "./slash-skill-chip";
import { Tooltip } from "./tooltip";
import { useInputBoxAttachments } from "./use-input-box-attachments";
import { useInputBoxCommands } from "./use-input-box-commands";
import { useComposerDraftPersistence } from "./use-input-box-draft";
import { FollowupsBar, useInputBoxFollowups } from "./use-input-box-followups";
import { useInputBoxPolish } from "./use-input-box-polish";
import { useInputBoxPromptHistory } from "./use-input-box-prompt-history";
import { useInputBoxSkillFlow } from "./use-input-box-skill-flow";
import { useInputBoxSubmit } from "./use-input-box-submit";
import { useInputBoxVoiceInput } from "./use-input-box-voice-input";

export function InputBox({
  className,
  disabled,
  autoFocus,
  status = "ready",
  context,
  extraHeader,
  isWelcomeMode,
  showDisclaimer = true,
  threadId,
  draftThreadId = threadId,
  draftAgentName,
  defaultModelName,
  initialValue,
  pendingTemplate,
  clearInjectedTemplateKey,
  onPendingTemplateConsumed,
  allowedSkillNames,
  skillInvocationEnabled = true,
  selectedTags = [],
  onRemoveTag,
  onContextChange,
  onFollowupsVisibilityChange,
  onGoalChange,
  onPrepareThread,
  turnSubmit,
  onStop,
  canStopStreaming = true,
  ...props
}: Omit<ComponentProps<typeof PromptInput>, "onSubmit"> & {
  assistantId?: string | null;
  status?: ChatStatus;
  disabled?: boolean;
  context: Omit<
    AgentThreadContext,
    "thread_id" | "is_plan_mode" | "thinking_enabled" | "subagent_enabled"
  > & {
    mode: "flash" | "thinking" | "pro" | "ultra" | undefined;
    reasoning_effort?: "minimal" | "low" | "medium" | "high";
  };
  extraHeader?: React.ReactNode;
  showDisclaimer?: boolean;
  /**
   * Whether to render the input in welcome layout (vertically centered,
   * with hero + quick action suggestions).  This is purely a visual flag,
   * decoupled from "the backend has created the thread" — see issue #2746.
   */
  isWelcomeMode?: boolean;
  threadId: string;
  draftThreadId?: string;
  draftAgentName?: string | null;
  /**
   * The active custom agent's configured default model, if any. Used as the
   * auto-selection fallback so an agent chat honors the agent's own default
   * model instead of silently snapping to the first configured model
   * (issue #4336). ``null`` / undefined = no agent default → use models[0].
   */
  defaultModelName?: string | null;
  initialValue?: string;
  /** Scenario/task template awaiting injection into the composer. */
  pendingTemplate?: string | null;
  /** Bump to clear a previously injected template from the composer. */
  clearInjectedTemplateKey?: number;
  onPendingTemplateConsumed?: () => void;
  /**
   * Enterprise skill gating: when the chat is scoped to an agent, only these
   * skill names (name/slug/resource id, case-insensitive) can be invoked.
   */
  allowedSkillNames?: readonly string[];
  /**
   * Whether the composer offers skill invocation at all (the "/" picker and
   * the Skill trigger). On by default: agent (Agent-scoped) sessions keep the
   * entry available and limit what it offers through `allowedSkillNames`, so
   * this only remains as an explicit opt-out for callers that must hide the
   * entry entirely.
   */
  skillInvocationEnabled?: boolean;
  /** Scenario/agent tags pinned to the composer (inline agent tag). */
  selectedTags?: SelectedTag[];
  onRemoveTag?: (id: string) => void;
  onContextChange?: (
    // Explicit selections contain only the fields changed by that action,
    // never the whole thread-resolved context (which may override the account).
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
  onFollowupsVisibilityChange?: (visible: boolean) => void;
  onGoalChange?: (goal: GoalState | null) => void;
  /**
   * Prepare a not-yet-materialized thread before a builtin command creates
   * it server-side. The `/goal <condition>` PUT endpoint materializes a
   * missing thread row itself, so a project-scoped new chat uses this to
   * assign membership first — the later idempotent thread create would
   * otherwise return that unassigned row without the project. Only runs for
   * goal-set: status/clear never create a thread server-side. Rejecting
   * aborts the command and keeps the composer's text for a retry.
   */
  onPrepareThread?: () => void | Promise<void>;
  /**
   * The turn-submit controller owning the message submit chain (duplicate
   * fence, draft policy, attachment pre-uploads, lifecycle). Built by the
   * chat page on top of the shared `useThreadStream` gate; the composer is
   * a view over it.
   */
  turnSubmit: TurnSubmitController;
  onStop?: () => void;
  /**
   * Whether the caller's role holds `runs:cancel` (RFC #4063 Phase 4).
   * Defaults to true so callers that don't resolve permissions (pre-Phase-4
   * backends, storybook) keep today's behavior; the Gateway route guard
   * stays the enforcement point.
   */
  canStopStreaming?: boolean;
}) {
  const { locale, t } = useI18n();
  const [modelDialogOpen, setModelDialogOpen] = useState(false);
  const { models } = useModels();
  const { user } = useAuth();
  const { thread, isMock } = useThread();
  const { attachments, textInput } = usePromptInputController();
  const setTextInput = textInput.setInput;
  const sidecar = useMaybeSidecar();
  const attachmentParts = attachments.files;
  // Conversations attached for the next message only. Not persisted with the
  // draft; cleared once a send proceeds or the composer moves to another thread.
  const [conversationReferences, setConversationReferences] = useState<
    ConversationReference[]
  >([]);
  useEffect(() => {
    setConversationReferences([]);
  }, [threadId]);
  const removeAttachment = attachments.remove;
  // Project documents attached from the shelf arrive already ingested
  // thread-side (spec §9): the composer shows them as completed attachments
  // and includes them in the next send without a re-upload. Staged only on
  // attach success; the hook consumes the staged entry once per thread and
  // keeps it across a Strict-Mode effect replay.
  const [projectAttachments, setProjectAttachments] =
    useStagedProjectAttachments(threadId);
  const { skills, isLoading: skillsLoading } = useSkills();
  const { data: uploadLimits } = useUploadLimits(threadId);
  const promptRootRef = useRef<HTMLDivElement | null>(null);
  const injectedTemplateRef = useRef<string | null>(null);
  const lastTemplateResetKeyRef = useRef(clearInjectedTemplateKey);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const inlineSkillTextRef = useRef<HTMLSpanElement | null>(null);
  const [textareaFocused, setTextareaFocused] = useState(false);
  const [selectedSlashSkill, setSelectedSlashSkill] =
    useState<SkillSelection>(null);
  // Picker opened from the Skill trigger button (anchored SkillPicker
  // overlay, independent of the "/" typing flow below).
  const [dismissedSkillSuggestionValue, setDismissedSkillSuggestionValue] =
    useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingSuggestion, setPendingSuggestion] = useState<string | null>(
    null,
  );

  const isComposerDisabled = disabled === true;
  const isMockThread = isMock === true;

  const { notifyUploadError, reportUploadLimitViolations } =
    useInputBoxAttachments({
      threadId,
      attachmentParts,
      removeAttachment,
      uploadLimits,
      turnSubmit,
      t,
    });

  // The single gate: which skills this composer may offer at all (the active
  // agent's closure when `allowedSkillNames` is set, otherwise the catalog).
  const offerable = useMemo(
    () => offerableSkills(skills, allowedSkillNames),
    [allowedSkillNames, skills],
  );
  const builtinSlashCommands = useMemo<SkillSuggestion[]>(
    () => [
      {
        name: "goal",
        description: t.inputBox.goalCommandDescription,
        kind: "builtin",
      },
      {
        name: "compact",
        description: t.inputBox.compactCommandDescription,
        kind: "builtin",
      },
    ],
    [t.inputBox.compactCommandDescription, t.inputBox.goalCommandDescription],
  );
  const slashSkillQuery = useMemo(
    () => getLeadingSlashSkillQuery(textInput.value ?? ""),
    [textInput.value],
  );
  const goalObjectiveCounter = useMemo(
    () => getGoalObjectiveCounter(textInput.value ?? ""),
    [textInput.value],
  );
  const skillSuggestions = useMemo(() => {
    if (slashSkillQuery === null) {
      return [];
    }
    const matches = matchSkills(
      {
        skills: offerable,
        builtins: builtinSlashCommands,
        limit: MAX_SKILL_SUGGESTIONS,
      },
      slashSkillQuery,
      builtinSlashCommands.map(({ name }) => name),
    );
    // Builtin commands own the whole composer line, so they cannot be combined
    // with a skill activation: `/goal` behind a selected skill would submit as
    // chat text instead of running the command. Drop them from the result
    // rather than withholding them from the helper, which needs the list to
    // reserve their names — a skill named after a builtin is unusable for the
    // mirrored reason, its submitted text runs the command, not the skill.
    return selectedSlashSkill
      ? matches.filter(({ kind }) => kind === "skill")
      : matches;
  }, [builtinSlashCommands, offerable, selectedSlashSkill, slashSkillQuery]);
  // A selected skill does not close the catalog: `/` reopens it so a skill can
  // be found by browsing and swapped without first clearing the chip.
  const showSkillSuggestions =
    skillInvocationEnabled &&
    !disabled &&
    textareaFocused &&
    slashSkillQuery !== null &&
    skillSuggestions.length > 0 &&
    dismissedSkillSuggestionValue !== textInput.value;
  // Skill catalog offered by the Skill trigger button, using the shared
  // anchored SkillPicker (same overlay as the "/" typing flow in the pre-
  // composer position). Kept separate from `skillSuggestions` so the typing
  // flow keeps its builtin-command entries and chip activation behavior.
  const { data: suggestionsConfig } = useSuggestionsConfig();
  const suggestionsConfigLoaded = suggestionsConfig !== undefined;
  const suggestionsEnabled = suggestionsConfig?.enabled;
  const maxFollowupSuggestions =
    suggestionsConfig?.max_suggestions ?? DEFAULT_MAX_SUGGESTIONS;
  const {
    followups,
    followupsLoading,
    followupsHidden,
    resetFollowups,
    dismissFollowups,
    notifyTurnStoppedByUser,
  } = useInputBoxFollowups({
    threadMessages: thread.messages,
    disabled,
    isMock,
    status,
    threadId,
    contextModelName: context.model_name,
    suggestionsConfigLoaded,
    suggestionsEnabled,
    maxFollowupSuggestions,
  });

  // Scenario/task template injection: empty composer takes the template
  // directly; a conflicting draft asks before replacing (pre-merge behavior).
  useEffect(() => {
    if (!pendingTemplate) return;
    onPendingTemplateConsumed?.();
    const insertion = prepareTaskInputInsertion(
      textInput.value ?? "",
      pendingTemplate,
    );
    if (insertion.kind === "conflict") {
      setPendingSuggestion(pendingTemplate);
      setConfirmOpen(true);
      return;
    }
    textInput.setInput(insertion.text);
    injectedTemplateRef.current = insertion.text;
    setTimeout(
      () => highlightPlaceholder(insertion.text, promptRootRef.current),
      50,
    );
  }, [pendingTemplate, onPendingTemplateConsumed, textInput]);

  useEffect(() => {
    if (clearInjectedTemplateKey === undefined) return;
    if (lastTemplateResetKeyRef.current === clearInjectedTemplateKey) return;
    lastTemplateResetKeyRef.current = clearInjectedTemplateKey;
    if (injectedTemplateRef.current === textInput.value) {
      textInput.clear();
    }
    injectedTemplateRef.current = null;
  }, [clearInjectedTemplateKey, textInput]);

  useEffect(() => {
    if (models.length === 0) {
      return;
    }
    const currentModel = models.find((m) => m.name === context.model_name);
    // Prefer the active agent's configured default model over models[0] as the
    // auto-selection fallback, so an agent chat respects the agent's own
    // default instead of snapping to the first model (issue #4336).
    const agentDefaultModel = defaultModelName
      ? models.find((m) => m.name === defaultModelName)
      : undefined;
    const fallbackModel = currentModel ?? agentDefaultModel ?? models[0]!;
    const supportsThinking = fallbackModel.supports_thinking ?? false;
    const nextModelName = fallbackModel.name;
    const nextMode = getResolvedMode(context.mode, supportsThinking);

    if (context.model_name === nextModelName && context.mode === nextMode) {
      return;
    }

    onContextChange?.(
      {
        ...context,
        model_name: nextModelName,
        mode: nextMode,
      },
      { automatic: true },
    );
  }, [context, models, defaultModelName, onContextChange]);

  const {
    resetHistoryBrowse,
    setPromptHistoryValue,
    handlePromptHistoryKeyDown,
  } = useInputBoxPromptHistory({
    threadMessages: thread.messages,
    textInput,
    selectedSlashSkill,
    textareaRef,
  });

  const {
    polishingInput,
    inputPolishUndoAvailable,
    inputPolishDisabled,
    abortInputPolishRequest,
    handlePolishInput,
    handleUndoInputPolish,
    setInputPolishUndo,
  } = useInputBoxPolish({
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
  });

  const {
    draftKey,
    latestDraftRef,
    currentDraftViewRef,
    invalidateDraftSaveTimer,
    scheduleDraftSave,
  } = useComposerDraftPersistence({
    userId: user?.id,
    agentName: context.agent_name,
    draftAgentName,
    draftThreadId,
    textInput,
    setTextInput,
    selectedSlashSkill,
    setSelectedSlashSkill,
    offerable,
    initialValue,
    skillsLoading,
    turnSubmit,
    setInputPolishUndo,
    resetHistoryBrowse,
  });

  const { goalRequestStateRef, handleGoalCommand, handleCompactCommand } =
    useInputBoxCommands({
      threadId,
      isWelcomeMode: isWelcomeMode === true,
      agentName: context.agent_name,
      modelName: context.model_name,
      textInput,
      t,
      onGoalChange,
      resetHistoryBrowse,
      resetFollowups,
    });

  const composerLocked = isComposerDisabled || polishingInput;
  // A denied runs:cancel role sees a disabled stop affordance, not a removed
  // one — the composer must still show that a turn is in flight.
  const stopDenied = status === "streaming" && !canStopStreaming;

  const interruptForVoiceStart = useCallback(() => {
    abortInputPolishRequest();
    setInputPolishUndo(null);
    resetHistoryBrowse();
  }, [abortInputPolishRequest, resetHistoryBrowse, setInputPolishUndo]);

  const {
    voiceListening,
    voiceInputSupported,
    toggleVoiceInput,
    abortVoiceInput,
  } = useInputBoxVoiceInput({
    threadId,
    composerLocked,
    locale,
    textInput,
    selectedSlashSkill,
    inlineSkillTextRef,
    textareaRef,
    t,
    onVoiceStartInterruption: interruptForVoiceStart,
  });

  const {
    skillSuggestionIndex,
    setSkillSuggestionIndex,
    skillPickerOpen,
    skillPickerIndex,
    inlineSkillComposingRef,
    activateSkill,
    applySkillSuggestion,
    handleSkillSuggestionKeyDown,
    closeSkillPicker,
    handleSkillPickerOpen,
    handleSkillPickerKeyDown,
    handleSelectedSlashSkillKeyDown,
    handleInlineSkillInput,
    handleInlineSkillPaste,
    handleInlineSkillKeyDown,
    clearSelectedSlashSkill,
  } = useInputBoxSkillFlow({
    textInput,
    attachments,
    selectedSlashSkill,
    setSelectedSlashSkill,
    setDismissedSkillSuggestionValue,
    textareaRef,
    inlineSkillTextRef,
    skillInvocationEnabled: skillInvocationEnabled === true,
    voiceListening,
    abortVoiceInput,
    resetHistoryBrowse,
    scheduleDraftSave,
    offerable,
    slashSkillQuery,
    skillSuggestions,
    showSkillSuggestions,
  });

  const selectedModel = useMemo(() => {
    if (models.length === 0) {
      return undefined;
    }
    return models.find((m) => m.name === context.model_name) ?? models[0];
  }, [context.model_name, models]);

  const resolvedModelName = selectedModel?.name;

  const supportThinking = useMemo(
    () => selectedModel?.supports_thinking ?? false,
    [selectedModel],
  );

  const supportReasoningEffort = useMemo(
    () => selectedModel?.supports_reasoning_effort ?? false,
    [selectedModel],
  );

  const { handleSubmit, handleStopStreaming } = useInputBoxSubmit({
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
  });

  const handleModelSelect = useCallback(
    (model_name: string) => {
      if (disabled || polishingInput) {
        return;
      }
      const model = models.find((m) => m.name === model_name);
      if (!model) {
        return;
      }
      const mode = getResolvedMode(
        context.mode,
        model.supports_thinking ?? false,
      );
      onContextChange?.({
        model_name,
        ...(mode !== context.mode ? { mode } : {}),
      });
      setModelDialogOpen(false);
    },
    [disabled, onContextChange, context, models, polishingInput],
  );

  const handleModeSelect = useCallback(
    (mode: InputMode) => {
      if (disabled || polishingInput) {
        return;
      }
      onContextChange?.({
        mode: getResolvedMode(mode, supportThinking),
        reasoning_effort:
          mode === "ultra"
            ? "high"
            : mode === "pro"
              ? "medium"
              : mode === "thinking"
                ? "low"
                : "minimal",
      });
    },
    [disabled, onContextChange, polishingInput, supportThinking],
  );

  const handleReasoningEffortSelect = useCallback(
    (effort: "minimal" | "low" | "medium" | "high") => {
      if (disabled || polishingInput) {
        return;
      }
      onContextChange?.({
        reasoning_effort: effort,
      });
    },
    [disabled, onContextChange, polishingInput],
  );

  const requestFormSubmit = useCallback(() => {
    const form = promptRootRef.current?.querySelector("form");
    form?.requestSubmit();
  }, []);

  const handleFollowupClick = useCallback(
    (suggestion: string) => {
      if (status === "streaming") {
        return;
      }
      const current = (textInput.value ?? "").trim();
      if (current) {
        setPendingSuggestion(suggestion);
        setConfirmOpen(true);
        return;
      }
      textInput.setInput(suggestion);
      dismissFollowups();
      setTimeout(() => requestFormSubmit(), 0);
    },
    [dismissFollowups, requestFormSubmit, status, textInput],
  );

  const confirmReplaceAndSend = useCallback(() => {
    if (!pendingSuggestion) {
      setConfirmOpen(false);
      return;
    }
    textInput.setInput(pendingSuggestion);
    dismissFollowups();
    setConfirmOpen(false);
    setPendingSuggestion(null);
    setTimeout(() => requestFormSubmit(), 0);
  }, [dismissFollowups, pendingSuggestion, requestFormSubmit, textInput]);

  const confirmAppendAndSend = useCallback(() => {
    if (!pendingSuggestion) {
      setConfirmOpen(false);
      return;
    }
    const current = (textInput.value ?? "").trim();
    const next = current
      ? `${current}\n${pendingSuggestion}`
      : pendingSuggestion;
    textInput.setInput(next);
    dismissFollowups();
    setConfirmOpen(false);
    setPendingSuggestion(null);
    setTimeout(() => requestFormSubmit(), 0);
  }, [dismissFollowups, pendingSuggestion, requestFormSubmit, textInput]);

  // Clicking the empty composer surface moves focus to the textarea (welcome
  // screen affordance): buttons, inputs and popups keep their own behavior.
  const handlePromptSurfaceClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement;
      if (
        target.closest(
          "button, textarea, input, a, [role='dialog'], [role='listbox'], [role='menu']",
        )
      ) {
        return;
      }
      textareaRef.current?.focus();
    },
    [],
  );

  const handlePromptTextareaKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      handleSkillPickerKeyDown(event);
      if (event.defaultPrevented) {
        return;
      }
      handleSkillSuggestionKeyDown(event);
      if (event.defaultPrevented) {
        return;
      }
      handleSelectedSlashSkillKeyDown(event);
      if (event.defaultPrevented) {
        return;
      }
      handlePromptHistoryKeyDown(event);
    },
    [
      handlePromptHistoryKeyDown,
      handleSelectedSlashSkillKeyDown,
      handleSkillPickerKeyDown,
      handleSkillSuggestionKeyDown,
    ],
  );

  const handlePromptTextareaChange = useCallback(
    (event: ChangeEvent<HTMLTextAreaElement>) => {
      if (voiceListening) {
        abortVoiceInput();
      }
      abortInputPolishRequest();
      setInputPolishUndo(null);
      resetHistoryBrowse();
      scheduleDraftSave({
        text: event.currentTarget.value,
        skillName: selectedSkillName(selectedSlashSkill),
      });
    },
    [
      abortInputPolishRequest,
      abortVoiceInput,
      resetHistoryBrowse,
      scheduleDraftSave,
      selectedSlashSkill,
      setInputPolishUndo,
      voiceListening,
    ],
  );

  const showFollowups =
    !disabled &&
    !isWelcomeMode &&
    !showSkillSuggestions &&
    !selectedSlashSkill &&
    !followupsHidden &&
    // Never show stale follow-up chips while a turn is streaming: a message
    // sent before the previous response finished would otherwise leave the
    // old chips (and the lone close button) overlapping the input box.
    status !== "streaming" &&
    (followupsLoading || followups.length > 0);

  useEffect(() => {
    onFollowupsVisibilityChange?.(showFollowups);
  }, [onFollowupsVisibilityChange, showFollowups]);

  useEffect(() => {
    return () => onFollowupsVisibilityChange?.(false);
  }, [onFollowupsVisibilityChange]);

  return (
    <div
      ref={promptRootRef}
      data-testid="input-box"
      onClick={handlePromptSurfaceClick}
      className={cn(
        "relative flex min-w-0 flex-col",
        isWelcomeMode ? "gap-5" : "gap-2",
      )}
    >
      {showFollowups && (
        <FollowupsBar
          loading={followupsLoading}
          suggestions={followups}
          onSelect={handleFollowupClick}
          onDismiss={dismissFollowups}
        />
      )}
      {showSkillSuggestions && (
        <SlashSkillSuggestions
          suggestions={skillSuggestions}
          activeIndex={skillSuggestionIndex}
          onSelect={applySkillSuggestion}
          onHover={setSkillSuggestionIndex}
        />
      )}
      <PromptInput
        className={cn(
          "bg-background/85 relative z-10 rounded-2xl backdrop-blur-sm transition-all duration-300 ease-out *:data-[slot='input-group']:rounded-2xl",
          polishingInput &&
            "shadow-primary/10 ring-primary/25 shadow-lg ring-1",
          className,
        )}
        disabled={composerLocked}
        globalDrop
        multiple
        onSubmit={handleSubmit}
        {...props}
      >
        {polishingInput && (
          <div
            aria-hidden="true"
            className="border-primary/30 bg-primary/5 pointer-events-auto absolute inset-0 z-20 animate-pulse cursor-wait rounded-2xl border opacity-80"
          />
        )}
        {extraHeader && (
          <div className="absolute top-0 right-0 left-0 z-10">
            <div className="absolute right-0 bottom-0 left-0 flex items-center justify-center">
              {extraHeader}
            </div>
          </div>
        )}
        <PromptInputHeader className="flex-wrap px-3 pt-3 pb-0 empty:hidden">
          {isWelcomeMode && selectedTags.length === 0 && (
            <div aria-hidden="true" className="h-8 w-full" />
          )}
          {selectedTags.length > 0 && onRemoveTag && (
            <div
              className="flex flex-wrap items-center gap-1"
              data-testid="inline-selected-tags"
            >
              {selectedTags.map((tag) => (
                <InlineSelectedTag
                  key={tag.id}
                  tag={tag}
                  onRemove={onRemoveTag}
                />
              ))}
            </div>
          )}
          <PromptInputAttachments className="contents p-0">
            {(attachment) => (
              <div className="max-w-60">
                <PromptInputAttachment data={attachment} />
              </div>
            )}
          </PromptInputAttachments>
          {projectAttachments.map((attachment) => (
            <div
              key={attachment.virtual_path}
              className="bg-muted text-muted-foreground type-compact flex h-7 items-center gap-1.5 rounded-full border py-0 pr-1 pl-2.5 font-medium"
              data-testid="project-attachment-chip"
            >
              <PaperclipIcon className="size-3" />
              <span className="max-w-40 truncate">{attachment.filename}</span>
              <button
                aria-label={t.inputBox.removeProjectAttachment}
                className="hover:bg-primary/20 focus-visible:ring-primary/40 -mr-0.5 ml-0.5 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none"
                type="button"
                onClick={() =>
                  setProjectAttachments((previous) =>
                    previous.filter(
                      (candidate) =>
                        candidate.virtual_path !== attachment.virtual_path,
                    ),
                  )
                }
              >
                <XIcon className="size-3" />
              </button>
            </div>
          ))}
          {conversationReferences.map((reference) => (
            <ConversationReferenceChip
              key={reference.threadId}
              onRemove={() =>
                setConversationReferences((current) =>
                  current.filter(
                    (item) => item.threadId !== reference.threadId,
                  ),
                )
              }
              removeLabel={t.inputBox.referenceConversationsRemove(
                reference.title,
              )}
              title={reference.title}
            />
          ))}
          {polishingInput && (
            <div
              aria-live="polite"
              className="text-primary bg-primary/10 border-primary/20 type-compact relative z-30 flex h-7 items-center gap-1.5 rounded-full border py-0 pr-1 pl-2.5 font-medium"
              role="status"
            >
              <Loader2Icon className="size-3 animate-spin" />
              {t.inputBox.inputPolishing}
              <button
                aria-label={t.inputBox.inputPolishCancel}
                className="hover:bg-primary/20 focus-visible:ring-primary/40 -mr-0.5 ml-0.5 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors focus-visible:ring-2 focus-visible:outline-none"
                data-testid="cancel-polish-input-button"
                onClick={abortInputPolishRequest}
                type="button"
              >
                <XIcon className="size-3" />
              </button>
            </div>
          )}
          {sidecar && sidecar.conversationQuotes.length > 0 && (
            <ReferenceAttachmentSummary
              references={sidecar.conversationQuotes}
              testId="conversation-quote-attachment"
              onClear={() => sidecar.clearConversationQuotes()}
            />
          )}
        </PromptInputHeader>
        <div className="relative min-h-16 w-full min-w-0 px-3 py-3">
          {selectedSlashSkill ? (
            <div
              className={cn(
                "type-body max-h-48 w-full min-w-0 cursor-text overflow-y-auto leading-6 break-all whitespace-pre-wrap md:text-[length:var(--text-supporting)]",
                isWelcomeMode ? "min-h-40" : "min-h-6",
              )}
              onClick={(event) => {
                if (event.target === event.currentTarget) {
                  focusContentEditableEnd(inlineSkillTextRef.current);
                }
              }}
            >
              <SlashSkillChip
                name={selectedSlashSkill.name}
                className="mr-2 max-w-[min(11rem,45%)] align-top"
                onRemove={clearSelectedSlashSkill}
              />
              <span
                aria-label={t.inputBox.placeholder}
                aria-multiline="true"
                contentEditable={!composerLocked}
                data-empty={textInput.value.length === 0}
                data-placeholder={t.inputBox.placeholder}
                data-slot="input-group-control"
                onBlur={() => setTextareaFocused(false)}
                onCompositionEnd={() => {
                  inlineSkillComposingRef.current = false;
                }}
                onCompositionStart={() => {
                  inlineSkillComposingRef.current = true;
                }}
                onFocus={() => setTextareaFocused(true)}
                onInput={handleInlineSkillInput}
                onKeyDown={handleInlineSkillKeyDown}
                onPaste={handleInlineSkillPaste}
                aria-placeholder={t.inputBox.placeholder}
                ref={inlineSkillTextRef}
                role="textbox"
                suppressContentEditableWarning
                className={cn(
                  "outline-none",
                  "before:text-muted-foreground before:pointer-events-none",
                  "data-[empty=true]:before:content-[attr(data-placeholder)]",
                  composerLocked && "cursor-not-allowed opacity-50",
                )}
                tabIndex={composerLocked ? -1 : 0}
              />
            </div>
          ) : (
            <PromptInputTextarea
              className={cn(
                "w-full min-w-0 p-0! text-left",
                isWelcomeMode
                  ? "type-body min-h-40 leading-7"
                  : "min-h-6! leading-6!",
              )}
              data-testid="chat-input"
              disabled={composerLocked}
              placeholder={t.inputBox.placeholder}
              autoFocus={autoFocus}
              defaultValue={initialValue}
              onBlur={() => setTextareaFocused(false)}
              onChange={handlePromptTextareaChange}
              onFocus={() => setTextareaFocused(true)}
              onKeyDown={handlePromptTextareaKeyDown}
              ref={textareaRef}
            />
          )}
          {skillInvocationEnabled && skillPickerOpen && (
            <SkillPicker
              skills={skills}
              allowedSkillNames={allowedSkillNames}
              query=""
              activeIndex={skillPickerIndex}
              title={t.inputBox.skill}
              onSelect={(skill) => {
                activateSkill(skill, false);
                closeSkillPicker();
              }}
              onClose={closeSkillPicker}
            />
          )}
        </div>
        <PromptInputFooter className="flex flex-wrap gap-2 sm:flex-nowrap">
          <PromptInputTools className="min-w-0 flex-1 flex-wrap">
            <AddAttachmentsButton
              disabled={composerLocked}
              uploadLimits={uploadLimits}
            />
            <ReferenceConversationsButton
              className="px-2!"
              currentThreadId={threadId}
              disabled={composerLocked}
              onChange={setConversationReferences}
              references={conversationReferences}
            />
            {voiceInputSupported && (
              <VoiceInputButton
                disabled={composerLocked}
                listening={voiceListening}
                supported={voiceInputSupported}
                onToggle={toggleVoiceInput}
              />
            )}
            <Tooltip
              content={
                polishingInput
                  ? t.inputBox.inputPolishing
                  : inputPolishUndoAvailable
                    ? t.inputBox.inputPolishUndo
                    : t.inputBox.inputPolish
              }
            >
              <PromptInputButton
                aria-label={
                  inputPolishUndoAvailable
                    ? t.inputBox.inputPolishUndo
                    : t.inputBox.inputPolish
                }
                className="min-h-10 min-w-10 px-0!"
                data-testid="polish-input-button"
                disabled={inputPolishDisabled}
                onClick={
                  inputPolishUndoAvailable
                    ? handleUndoInputPolish
                    : handlePolishInput
                }
              >
                {polishingInput ? (
                  <Loader2Icon className="size-4 animate-spin" />
                ) : inputPolishUndoAvailable ? (
                  <Undo2Icon className="size-4" />
                ) : (
                  <SparklesIcon className="size-4" />
                )}
              </PromptInputButton>
            </Tooltip>
            <ComposerModeMenu
              mode={
                context.mode === "flash" ||
                context.mode === "thinking" ||
                context.mode === "pro" ||
                context.mode === "ultra"
                  ? context.mode
                  : "flash"
              }
              supportThinking={supportThinking}
              disabled={composerLocked}
              onSelect={handleModeSelect}
            />
            {supportReasoningEffort && context.mode !== "flash" && (
              <ComposerReasoningEffortMenu
                effort={context.reasoning_effort}
                onSelect={handleReasoningEffortSelect}
              />
            )}
          </PromptInputTools>
          <PromptInputTools className="min-w-0 justify-end">
            {goalObjectiveCounter && (
              <span
                aria-label={t.inputBox.goalLengthCounter
                  .replace("{length}", () =>
                    String(goalObjectiveCounter.length),
                  )
                  .replace("{max}", () => String(goalObjectiveCounter.max))}
                className={cn(
                  "type-compact shrink-0 tabular-nums",
                  goalObjectiveCounter.overLimit
                    ? "text-destructive font-medium"
                    : "text-muted-foreground",
                )}
                data-testid="goal-length-counter"
              >
                {goalObjectiveCounter.length}/{goalObjectiveCounter.max}
              </span>
            )}
            <ModelPicker
              open={modelDialogOpen}
              onOpenChange={setModelDialogOpen}
            >
              <ModelPickerTrigger asChild>
                <PromptInputButton
                  aria-label={t.inputBox.selectModel}
                  className="max-w-40 min-w-0 sm:max-w-56"
                  data-testid="model-selector-trigger"
                  disabled={composerLocked}
                >
                  <div className="flex min-w-0 flex-col text-left">
                    <span className="type-body flex-1 truncate text-left font-normal">
                      {selectedModel?.display_name}
                    </span>
                  </div>
                </PromptInputButton>
              </ModelPickerTrigger>
              <ModelPickerContent
                open={modelDialogOpen}
                models={models}
                selectedModelName={selectedModel?.name}
                onModelSelect={handleModelSelect}
              />
            </ModelPicker>
            {skillInvocationEnabled && (
              <Tooltip content={t.inputBox.invokeSkill}>
                <PromptInputButton
                  aria-label={t.inputBox.invokeSkill}
                  data-testid="skill-selector-trigger"
                  disabled={composerLocked}
                  onClick={handleSkillPickerOpen}
                >
                  <SparklesIcon className="size-4" />
                  <span className="type-body font-normal">
                    {t.inputBox.skill}
                  </span>
                </PromptInputButton>
              </Tooltip>
            )}
            {isWelcomeMode && !skillInvocationEnabled && (
              <PromptInputButton
                aria-hidden="true"
                className="pointer-events-none invisible"
                disabled
                tabIndex={-1}
              >
                <SparklesIcon className="size-4" />
                <span className="type-body font-normal">
                  {t.inputBox.skill}
                </span>
              </PromptInputButton>
            )}
            <PromptInputSubmit
              className="rounded-full"
              disabled={composerLocked || stopDenied}
              variant="outline"
              status={status}
              // A bare disabled stop square reads as a broken composer;
              // explain the permission boundary (native title, since a
              // Radix tooltip won't fire on a disabled button). Spread
              // conditionally: an explicitly-undefined aria-label would
              // clobber PromptInputSubmit's default aria-label="Submit"
              // and strip the submit control's accessible name.
              {...(stopDenied
                ? {
                    "aria-label": t.inputBox.stopStreamingUnavailable,
                    title: t.inputBox.stopStreamingUnavailable,
                  }
                : {})}
              onClick={(e) => {
                if (status === "streaming") {
                  e.preventDefault();
                  handleStopStreaming();
                }
              }}
            />
          </PromptInputTools>
        </PromptInputFooter>
      </PromptInput>
      {!isWelcomeMode && (
        <div className="bg-background absolute right-0 -bottom-[17px] left-0 z-0 h-4"></div>
      )}

      {showDisclaimer && (
        <p
          className={cn(
            "text-muted-foreground type-compact z-10 px-4 text-center leading-4",
            !isWelcomeMode && "absolute top-full right-0 left-0",
          )}
        >
          {t.inputBox.disclaimer}
        </p>
      )}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t.inputBox.followupConfirmTitle}</DialogTitle>
            <DialogDescription>
              {t.inputBox.followupConfirmDescription}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              {t.common.cancel}
            </Button>
            <Button variant="secondary" onClick={confirmAppendAndSend}>
              {t.inputBox.followupConfirmAppend}
            </Button>
            <Button onClick={confirmReplaceAndSend}>
              {t.inputBox.followupConfirmReplace}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
