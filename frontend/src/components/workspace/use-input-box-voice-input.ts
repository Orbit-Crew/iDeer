import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { TextInputContext } from "@/components/ai-elements/prompt-input";
import type { Translations } from "@/core/i18n/locales";
import type { SkillSelection } from "@/core/skills/selection";
import {
  appendSpeechTranscript,
  getSpeechRecognitionConstructor,
  getSpeechRecognitionLanguage,
  mapSpeechRecognitionError,
  readSpeechRecognitionTranscript,
  shouldRestartSpeechRecognition,
  type BrowserSpeechRecognition,
  type SpeechRecognitionErrorKind,
} from "@/core/voice-input/speech-recognition";

import { focusContentEditableEnd } from "./input-box-dom";

type VoiceRecognitionStartOptions = {
  focusAfterStart?: boolean;
};

/**
 * Voice dictation for the composer: the Web Speech recognition lifecycle with
 * auto-restart, error mapping, and the listening state the mic button renders.
 * `onVoiceStartInterruption` lets the host cancel its own transient flows
 * (polish, history browsing) when a dictation session starts.
 */
export function useInputBoxVoiceInput({
  threadId,
  composerLocked,
  locale,
  textInput,
  selectedSlashSkill,
  inlineSkillTextRef,
  textareaRef,
  t,
  onVoiceStartInterruption,
}: {
  threadId: string;
  composerLocked: boolean;
  locale: string;
  textInput: TextInputContext;
  selectedSlashSkill: SkillSelection;
  inlineSkillTextRef: React.RefObject<HTMLSpanElement | null>;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  t: Translations;
  onVoiceStartInterruption: () => void;
}) {
  const voiceRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const voiceBaseTextRef = useRef("");
  const voiceLatestTextRef = useRef("");
  const voiceLastErrorKindRef = useRef<SpeechRecognitionErrorKind | null>(null);
  const voiceStopRequestedRef = useRef(false);
  const voiceRestartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const startVoiceRecognitionRef = useRef<
    ((options?: VoiceRecognitionStartOptions) => boolean) | null
  >(null);
  const [voiceListening, setVoiceListening] = useState(false);

  const clearVoiceRestartTimer = useCallback(() => {
    if (voiceRestartTimerRef.current === null) {
      return;
    }
    clearTimeout(voiceRestartTimerRef.current);
    voiceRestartTimerRef.current = null;
  }, []);

  const cleanupVoiceRecognition = useCallback(
    (
      recognition: BrowserSpeechRecognition | null,
      options: { keepListening?: boolean } = {},
    ) => {
      clearVoiceRestartTimer();
      if (!recognition) {
        if (!options.keepListening) {
          voiceLastErrorKindRef.current = null;
          voiceStopRequestedRef.current = false;
          setVoiceListening(false);
        }
        return;
      }
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;
      if (voiceRecognitionRef.current === recognition) {
        voiceRecognitionRef.current = null;
      }
      if (!options.keepListening) {
        voiceLastErrorKindRef.current = null;
        voiceStopRequestedRef.current = false;
        setVoiceListening(false);
      }
    },
    [clearVoiceRestartTimer],
  );

  const abortVoiceInput = useCallback(() => {
    const recognition = voiceRecognitionRef.current;
    voiceStopRequestedRef.current = true;
    if (!recognition) {
      cleanupVoiceRecognition(null);
      return;
    }
    cleanupVoiceRecognition(recognition);
    try {
      recognition.abort();
    } catch {
      // Browser implementations can throw when the recognizer already ended.
    }
  }, [cleanupVoiceRecognition]);

  const speechRecognitionConstructor = useMemo(
    () =>
      typeof window === "undefined"
        ? null
        : getSpeechRecognitionConstructor(window),
    [],
  );
  const voiceInputSupported = speechRecognitionConstructor !== null;

  const getVoiceInputErrorMessage = useCallback(
    (kind: SpeechRecognitionErrorKind) => {
      switch (kind) {
        case "permission_denied":
          return t.inputBox.voiceInputPermissionDenied;
        case "microphone_unavailable":
          return t.inputBox.voiceInputMicrophoneUnavailable;
        case "unsupported_language":
          return t.inputBox.voiceInputUnsupportedLanguage;
        case "network":
          return t.inputBox.voiceInputNetworkError;
        case "no_speech":
          return t.inputBox.voiceInputNoSpeech;
        case "cancelled":
          return null;
        default:
          return t.inputBox.voiceInputFailed;
      }
    },
    [t],
  );

  const startVoiceRecognition = useCallback(
    (options: VoiceRecognitionStartOptions = {}) => {
      if (composerLocked || !speechRecognitionConstructor) {
        return false;
      }

      const recognition = new speechRecognitionConstructor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = getSpeechRecognitionLanguage(locale);
      recognition.maxAlternatives = 1;
      voiceLastErrorKindRef.current = null;
      voiceLatestTextRef.current = voiceBaseTextRef.current;
      voiceRecognitionRef.current = recognition;

      recognition.onresult = (event) => {
        if (voiceRecognitionRef.current !== recognition) {
          return;
        }
        const transcript = readSpeechRecognitionTranscript(event.results).text;
        const nextValue = appendSpeechTranscript(
          voiceBaseTextRef.current,
          transcript,
        );
        voiceLatestTextRef.current = nextValue;
        textInput.setInput(nextValue);
      };
      recognition.onerror = (event) => {
        const errorKind = mapSpeechRecognitionError(event.error);
        voiceLastErrorKindRef.current = errorKind;
        if (
          !voiceStopRequestedRef.current &&
          shouldRestartSpeechRecognition(errorKind)
        ) {
          return;
        }

        const message = getVoiceInputErrorMessage(errorKind);
        if (message) {
          toast.error(message);
        }
      };
      recognition.onend = () => {
        const shouldRestart =
          voiceRecognitionRef.current === recognition &&
          !voiceStopRequestedRef.current &&
          shouldRestartSpeechRecognition(voiceLastErrorKindRef.current);
        if (shouldRestart) {
          voiceBaseTextRef.current = voiceLatestTextRef.current;
          cleanupVoiceRecognition(recognition, { keepListening: true });
          voiceRestartTimerRef.current = setTimeout(() => {
            voiceRestartTimerRef.current = null;
            if (voiceStopRequestedRef.current) {
              cleanupVoiceRecognition(null);
              return;
            }
            const restarted = startVoiceRecognitionRef.current?.() ?? false;
            if (!restarted) {
              cleanupVoiceRecognition(null);
            }
          }, 150);
          return;
        }
        cleanupVoiceRecognition(recognition);
      };

      setVoiceListening(true);
      try {
        recognition.start();
        if (options.focusAfterStart) {
          requestAnimationFrame(() => {
            if (selectedSlashSkill) {
              focusContentEditableEnd(inlineSkillTextRef.current);
            } else {
              textareaRef.current?.focus();
            }
          });
        }
        return true;
      } catch {
        cleanupVoiceRecognition(recognition);
        toast.error(t.inputBox.voiceInputFailed);
        return false;
      }
    },
    [
      cleanupVoiceRecognition,
      composerLocked,
      getVoiceInputErrorMessage,
      inlineSkillTextRef,
      locale,
      selectedSlashSkill,
      speechRecognitionConstructor,
      t.inputBox.voiceInputFailed,
      textInput,
      textareaRef,
    ],
  );

  useEffect(() => {
    startVoiceRecognitionRef.current = startVoiceRecognition;
  }, [startVoiceRecognition]);

  const stopVoiceInput = useCallback(() => {
    const recognition = voiceRecognitionRef.current;
    voiceStopRequestedRef.current = true;
    if (!recognition) {
      cleanupVoiceRecognition(null);
      return;
    }
    try {
      recognition.stop();
    } catch {
      cleanupVoiceRecognition(recognition);
    }
  }, [cleanupVoiceRecognition]);

  const toggleVoiceInput = useCallback(() => {
    if (voiceListening) {
      stopVoiceInput();
      return;
    }
    if (composerLocked) {
      return;
    }
    if (!speechRecognitionConstructor) {
      toast.error(t.inputBox.voiceInputUnsupported);
      return;
    }

    onVoiceStartInterruption();
    voiceStopRequestedRef.current = false;
    voiceBaseTextRef.current = textInput.value ?? "";
    voiceLatestTextRef.current = voiceBaseTextRef.current;
    startVoiceRecognition({ focusAfterStart: true });
  }, [
    composerLocked,
    onVoiceStartInterruption,
    speechRecognitionConstructor,
    startVoiceRecognition,
    stopVoiceInput,
    t.inputBox.voiceInputUnsupported,
    textInput,
    voiceListening,
  ]);

  useEffect(() => {
    if (composerLocked && voiceListening) {
      stopVoiceInput();
    }
  }, [composerLocked, stopVoiceInput, voiceListening]);

  useEffect(() => {
    return () => abortVoiceInput();
  }, [abortVoiceInput, threadId]);

  return {
    voiceListening,
    voiceInputSupported,
    toggleVoiceInput,
    abortVoiceInput,
  };
}
