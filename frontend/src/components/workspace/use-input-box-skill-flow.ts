import type { ClipboardEvent, FormEvent, KeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type {
  AttachmentsContext,
  TextInputContext,
} from "@/components/ai-elements/prompt-input";
import {
  clearSelection,
  matchSkills,
  select,
  selectedSkillName,
  type SkillSelection,
  type SkillSuggestion,
} from "@/core/skills/selection";
import type { Skill } from "@/core/skills/type";
import { splitUnsupportedUploadFiles } from "@/core/uploads";
import { isIMEComposing } from "@/lib/ime";

import {
  focusContentEditableEnd,
  insertPlainTextAtSelection,
} from "./input-box-dom";

/**
 * Skill invocation flow for the composer: the "/" typing overlay navigation,
 * the anchored SkillPicker, the selected-skill chip editing surface (a
 * contenteditable that mirrors the composer text), and their IME-aware key
 * handling.
 */
export function useInputBoxSkillFlow({
  textInput,
  attachments,
  selectedSlashSkill,
  setSelectedSlashSkill,
  setDismissedSkillSuggestionValue,
  textareaRef,
  inlineSkillTextRef,
  skillInvocationEnabled,
  voiceListening,
  abortVoiceInput,
  resetHistoryBrowse,
  scheduleDraftSave,
  offerable,
  slashSkillQuery,
  skillSuggestions,
  showSkillSuggestions,
}: {
  textInput: TextInputContext;
  attachments: AttachmentsContext;
  selectedSlashSkill: SkillSelection;
  setSelectedSlashSkill: (selection: SkillSelection) => void;
  setDismissedSkillSuggestionValue: (value: string | null) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  inlineSkillTextRef: React.RefObject<HTMLSpanElement | null>;
  skillInvocationEnabled: boolean;
  voiceListening: boolean;
  abortVoiceInput: () => void;
  resetHistoryBrowse: () => void;
  scheduleDraftSave: (
    draft: { text: string; skillName: string | null },
    key?: string,
  ) => number | null;
  offerable: Skill[];
  slashSkillQuery: string | null;
  skillSuggestions: SkillSuggestion[];
  showSkillSuggestions: boolean;
}) {
  const [skillSuggestionIndex, setSkillSuggestionIndex] = useState(0);
  const [skillPickerOpen, setSkillPickerOpen] = useState(false);
  const [skillPickerIndex, setSkillPickerIndex] = useState(0);
  const inlineSkillComposingRef = useRef(false);

  // Skill catalog offered by the Skill trigger button, using the shared
  // anchored SkillPicker (same overlay as the "/" typing flow in the pre-
  // composer position). Kept separate from `skillSuggestions` so the typing
  // flow keeps its builtin-command entries and chip activation behavior.
  const skillPickerSuggestions = useMemo(
    () => (skillPickerOpen ? matchSkills({ skills: offerable }, "") : []),
    [offerable, skillPickerOpen],
  );

  useEffect(() => {
    setSkillSuggestionIndex(0);
  }, [slashSkillQuery, skillSuggestions.length]);

  const activateSkill = useCallback(
    (suggestion: SkillSuggestion, clearInput: boolean) => {
      if (suggestion.kind === "skill") {
        setSelectedSlashSkill(select(suggestion));
        if (clearInput) {
          textInput.setInput("");
        }
        setDismissedSkillSuggestionValue(null);
        requestAnimationFrame(() => {
          focusContentEditableEnd(inlineSkillTextRef.current);
        });
        return;
      }

      const nextValue = `/${suggestion.name} `;
      textInput.setInput(nextValue);
      setDismissedSkillSuggestionValue(nextValue);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea) {
          return;
        }
        textarea.focus();
        textarea.setSelectionRange(nextValue.length, nextValue.length);
      });
    },
    [
      inlineSkillTextRef,
      setDismissedSkillSuggestionValue,
      setSelectedSlashSkill,
      textInput,
      textareaRef,
    ],
  );

  const applySkillSuggestion = useCallback(
    (suggestion: SkillSuggestion) => activateSkill(suggestion, true),
    [activateSkill],
  );

  const handleSkillSuggestionKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (!showSkillSuggestions) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSkillSuggestionIndex(
          (index) => (index + 1) % skillSuggestions.length,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSkillSuggestionIndex(
          (index) =>
            (index - 1 + skillSuggestions.length) % skillSuggestions.length,
        );
        return;
      }

      if (event.key === "Enter" || event.key === "Tab") {
        if (event.shiftKey) {
          return;
        }
        event.preventDefault();
        const selectedSkill = skillSuggestions[skillSuggestionIndex];
        if (selectedSkill) {
          applySkillSuggestion(selectedSkill);
        }
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setDismissedSkillSuggestionValue(textInput.value);
      }
    },
    [
      applySkillSuggestion,
      setDismissedSkillSuggestionValue,
      showSkillSuggestions,
      skillSuggestionIndex,
      skillSuggestions,
      textInput.value,
    ],
  );

  const closeSkillPicker = useCallback(() => {
    setSkillPickerOpen(false);
  }, []);

  const handleSkillPickerOpen = useCallback(() => {
    if (!skillInvocationEnabled) {
      return;
    }
    setSkillPickerOpen(true);
    setSkillPickerIndex(0);
    textareaRef.current?.focus();
  }, [skillInvocationEnabled, textareaRef]);

  const handleSkillPickerKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (!skillPickerOpen || skillPickerSuggestions.length === 0) {
        return;
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSkillPickerIndex(
          (index) => (index + 1) % skillPickerSuggestions.length,
        );
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSkillPickerIndex(
          (index) =>
            (index - 1 + skillPickerSuggestions.length) %
            skillPickerSuggestions.length,
        );
        return;
      }

      if (event.key === "Enter" || event.key === "Tab") {
        if (event.shiftKey) {
          return;
        }
        event.preventDefault();
        const selected =
          skillPickerSuggestions[skillPickerIndex] ?? skillPickerSuggestions[0];
        if (selected) {
          activateSkill(selected, false);
          closeSkillPicker();
        }
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        closeSkillPicker();
      }
    },
    [
      closeSkillPicker,
      activateSkill,
      skillPickerIndex,
      skillPickerOpen,
      skillPickerSuggestions,
    ],
  );

  useEffect(() => {
    if (!skillInvocationEnabled) {
      setSkillPickerOpen(false);
    }
  }, [skillInvocationEnabled]);

  const handleSelectedSlashSkillKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (
        event.key !== "Backspace" ||
        !selectedSlashSkill ||
        textInput.value.length > 0 ||
        isIMEComposing(event)
      ) {
        return;
      }

      event.preventDefault();
      setSelectedSlashSkill(clearSelection());
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
      });
    },
    [selectedSlashSkill, setSelectedSlashSkill, textInput.value, textareaRef],
  );

  const updateInlineSkillTextInput = useCallback(
    (element: HTMLElement) => {
      if (voiceListening) {
        abortVoiceInput();
      }
      resetHistoryBrowse();
      const nextText = element.textContent ?? "";
      textInput.setInput(nextText);
      scheduleDraftSave({
        text: nextText,
        skillName: selectedSkillName(selectedSlashSkill),
      });
    },
    [
      abortVoiceInput,
      resetHistoryBrowse,
      scheduleDraftSave,
      selectedSlashSkill,
      textInput,
      voiceListening,
    ],
  );

  useEffect(() => {
    if (!selectedSlashSkill) {
      return;
    }

    const element = inlineSkillTextRef.current;
    if (element && element.textContent !== textInput.value) {
      element.textContent = textInput.value;
    }
  }, [inlineSkillTextRef, selectedSlashSkill, textInput.value]);

  const handleInlineSkillInput = useCallback(
    (event: FormEvent<HTMLSpanElement>) => {
      updateInlineSkillTextInput(event.currentTarget);
    },
    [updateInlineSkillTextInput],
  );

  const handleInlineSkillPaste = useCallback(
    (event: ClipboardEvent<HTMLSpanElement>) => {
      const pastedFiles = Array.from(event.clipboardData.items)
        .filter((item) => item.kind === "file")
        .flatMap((item) => {
          const file = item.getAsFile();
          return file ? [file] : [];
        });

      if (pastedFiles.length > 0) {
        event.preventDefault();
        const { accepted, message } = splitUnsupportedUploadFiles(pastedFiles);
        if (message) {
          toast.error(message);
        }
        if (accepted.length > 0) {
          attachments.add(accepted);
        }
        return;
      }

      const text = event.clipboardData.getData("text/plain");
      if (!text) {
        return;
      }

      event.preventDefault();
      if (insertPlainTextAtSelection(event.currentTarget, text)) {
        updateInlineSkillTextInput(event.currentTarget);
      }
    },
    [attachments, updateInlineSkillTextInput],
  );

  const handleInlineSkillKeyDown = useCallback(
    (event: KeyboardEvent<HTMLSpanElement>) => {
      // The catalog can be reopened from here, so its navigation keys must win
      // over Enter-to-submit. Skip it mid-composition, where Enter belongs to
      // the IME candidate rather than the list.
      if (!isIMEComposing(event, inlineSkillComposingRef.current)) {
        handleSkillSuggestionKeyDown(event);
        if (event.defaultPrevented) {
          return;
        }
      }

      handleSelectedSlashSkillKeyDown(event);
      if (event.defaultPrevented) {
        return;
      }

      if (event.key !== "Enter") {
        return;
      }

      if (isIMEComposing(event, inlineSkillComposingRef.current)) {
        return;
      }

      event.preventDefault();

      if (event.shiftKey) {
        if (insertPlainTextAtSelection(event.currentTarget, "\n")) {
          updateInlineSkillTextInput(event.currentTarget);
        }
        return;
      }

      event.currentTarget.closest("form")?.requestSubmit();
    },
    [
      handleSelectedSlashSkillKeyDown,
      handleSkillSuggestionKeyDown,
      updateInlineSkillTextInput,
    ],
  );

  const clearSelectedSlashSkill = useCallback(() => {
    setSelectedSlashSkill(clearSelection());
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
    });
  }, [setSelectedSlashSkill, textareaRef]);

  return {
    skillSuggestionIndex,
    setSkillSuggestionIndex,
    skillPickerOpen,
    skillPickerIndex,
    skillPickerSuggestions,
    inlineSkillComposingRef,
    activateSkill,
    applySkillSuggestion,
    handleSkillSuggestionKeyDown,
    closeSkillPicker,
    handleSkillPickerOpen,
    handleSkillPickerKeyDown,
    handleSelectedSlashSkillKeyDown,
    updateInlineSkillTextInput,
    handleInlineSkillInput,
    handleInlineSkillPaste,
    handleInlineSkillKeyDown,
    clearSelectedSlashSkill,
  };
}
