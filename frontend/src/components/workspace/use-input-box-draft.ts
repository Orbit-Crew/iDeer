import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type { TextInputContext } from "@/components/ai-elements/prompt-input";
import {
  clearSelection,
  fromDraft,
  selectedSkillName,
  type SkillSelection,
} from "@/core/skills/selection";
import type { Skill } from "@/core/skills/type";
import {
  buildComposerDraftKey,
  getSessionComposerDraftStorage,
  readComposerDraft,
  writeComposerDraft,
  type ComposerDraft,
} from "@/core/threads/composer-draft";

const COMPOSER_DRAFT_SAVE_DELAY_MS = 300;

/**
 * Composer draft persistence: debounced saves keyed per user/agent/thread,
 * hydration of a restored draft on thread switch, and the draft view/tracking
 * refs the turn-submit controller reads through its draft ports.
 */
export function useComposerDraftPersistence({
  userId,
  agentName,
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
}: {
  userId: string | undefined;
  agentName: unknown;
  draftAgentName: string | null | undefined;
  draftThreadId: string;
  textInput: TextInputContext;
  setTextInput: TextInputContext["setInput"];
  selectedSlashSkill: SkillSelection;
  setSelectedSlashSkill: (selection: SkillSelection) => void;
  offerable: Skill[];
  initialValue: string | undefined;
  skillsLoading: boolean;
  turnSubmit: {
    releaseDraftHold: () => void;
    shouldHoldDraftFor: (key: string) => boolean;
  };
  setInputPolishUndo: (value: null) => void;
  resetHistoryBrowse: () => void;
}) {
  const latestDraftRef = useRef<{
    key: string;
    draft: { text: string; skillName: string | null };
  } | null>(null);
  const currentDraftViewRef = useRef<{
    key: string;
    text: string;
    skillName: string | null;
  }>({ key: "", text: "", skillName: null });
  const draftSaveTimerRef = useRef<number | null>(null);
  const draftSaveGenerationRef = useRef(0);
  const [hydratedDraftKey, setHydratedDraftKey] = useState<string | null>(null);

  const draftKey = useMemo(
    () =>
      buildComposerDraftKey({
        userId: userId ?? "anonymous",
        agentName:
          draftAgentName ?? (typeof agentName === "string" ? agentName : null),
        threadId: draftThreadId,
      }),
    [agentName, draftAgentName, draftThreadId, userId],
  );
  currentDraftViewRef.current = {
    key: draftKey,
    text: textInput.value ?? "",
    skillName: selectedSkillName(selectedSlashSkill),
  };

  const cancelDraftSaveTimer = useCallback(() => {
    if (draftSaveTimerRef.current === null) {
      return;
    }
    window.clearTimeout(draftSaveTimerRef.current);
    draftSaveTimerRef.current = null;
  }, []);
  const invalidateDraftSaveTimer = useCallback(() => {
    draftSaveGenerationRef.current += 1;
    cancelDraftSaveTimer();
  }, [cancelDraftSaveTimer]);
  const scheduleDraftSave = useCallback(
    (draft: ComposerDraft, key = draftKey) => {
      // While a submission holds this key's draft, an emptied composer must
      // not overwrite the preserved draft (the turn-submit lifecycle
      // restores/clears it instead).
      if (
        !draft.text &&
        !draft.skillName &&
        turnSubmit.shouldHoldDraftFor(key)
      ) {
        return null;
      }
      if (draft.text || draft.skillName) {
        // A newly typed draft releases the hold.
        turnSubmit.releaseDraftHold();
      }

      latestDraftRef.current = { key, draft };
      cancelDraftSaveTimer();
      draftSaveGenerationRef.current += 1;
      const generation = draftSaveGenerationRef.current;
      const timer = window.setTimeout(() => {
        if (
          draftSaveGenerationRef.current !== generation ||
          draftSaveTimerRef.current !== timer
        ) {
          return;
        }
        draftSaveTimerRef.current = null;
        writeComposerDraft(getSessionComposerDraftStorage(), key, draft);
      }, COMPOSER_DRAFT_SAVE_DELAY_MS);
      draftSaveTimerRef.current = timer;
      return timer;
    },
    [cancelDraftSaveTimer, draftKey, turnSubmit],
  );
  const flushLatestDraft = useCallback(
    (expectedKey?: string) => {
      const latest = latestDraftRef.current;
      if (!latest || (expectedKey && latest.key !== expectedKey)) {
        return;
      }
      cancelDraftSaveTimer();
      writeComposerDraft(
        getSessionComposerDraftStorage(),
        latest.key,
        latest.draft,
      );
    },
    [cancelDraftSaveTimer],
  );

  useLayoutEffect(() => {
    resetHistoryBrowse();
    setTextInput("");
    setSelectedSlashSkill(clearSelection());
    setInputPolishUndo(null);
    setHydratedDraftKey(null);
    turnSubmit.releaseDraftHold();
    latestDraftRef.current = null;
    invalidateDraftSaveTimer();
    return () => flushLatestDraft(draftKey);
  }, [
    draftKey,
    flushLatestDraft,
    invalidateDraftSaveTimer,
    resetHistoryBrowse,
    setInputPolishUndo,
    setSelectedSlashSkill,
    setTextInput,
    turnSubmit,
  ]);

  useLayoutEffect(() => {
    const handlePageHide = () => flushLatestDraft();
    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, [flushLatestDraft]);

  useEffect(() => {
    if (skillsLoading || hydratedDraftKey === draftKey) {
      return;
    }

    const savedDraft = readComposerDraft(
      getSessionComposerDraftStorage(),
      draftKey,
    );
    if (!savedDraft) {
      if (!textInput.value && initialValue) {
        setTextInput(initialValue);
      }
      setHydratedDraftKey(draftKey);
      return;
    }

    const restored = fromDraft(savedDraft.skillName, {
      text: savedDraft.text,
      skills: offerable,
    });
    setTextInput(restored.text);
    setSelectedSlashSkill(restored.selected);
    setHydratedDraftKey(draftKey);
  }, [
    draftKey,
    hydratedDraftKey,
    initialValue,
    offerable,
    setSelectedSlashSkill,
    setTextInput,
    skillsLoading,
    textInput.value,
  ]);

  useEffect(() => {
    if (hydratedDraftKey !== draftKey) {
      return;
    }

    const draft: ComposerDraft = {
      text: textInput.value ?? "",
      skillName: selectedSkillName(selectedSlashSkill),
    };
    const timer = scheduleDraftSave(draft, draftKey);
    return () => {
      if (timer === null) {
        return;
      }
      window.clearTimeout(timer);
      if (draftSaveTimerRef.current === timer) {
        draftSaveTimerRef.current = null;
      }
    };
  }, [
    draftKey,
    hydratedDraftKey,
    scheduleDraftSave,
    selectedSlashSkill,
    textInput.value,
  ]);

  return {
    draftKey,
    latestDraftRef,
    currentDraftViewRef,
    invalidateDraftSaveTimer,
    scheduleDraftSave,
    flushLatestDraft,
  };
}
