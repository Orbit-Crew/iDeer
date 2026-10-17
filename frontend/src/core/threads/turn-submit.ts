/**
 * Turn submission — the deep module owning the "send one message" chain
 * (spec: 2026-10-03 architecture deepening, candidate 3; term: root
 * CONTEXT.md "Turn").
 *
 * One submit entry (`TurnSubmitController.submit`) plus the turn's lifecycle
 * results; the duplicate-submission fence and the submit-chain policies are
 * implementation details behind it. The stream module (`hooks.ts`) joins the
 * same fence through `TurnSubmitGate` instead of keeping its own in-flight
 * ref and lifecycle callback refs, and the composer/chat pages shrink to
 * views over the controller.
 *
 * First version covers the message submit chain only: `/goal`, `/compact`
 * commands and suggestion fetches stay with the composer.
 */

import type { Message } from "@langchain/langgraph-sdk";
import { useMemo, useRef } from "react";

import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";

import type { CodeEvidencePackage, UploadedFileInfo } from "../uploads";
import { promptInputFilePartToFile, uploadFiles } from "../uploads";

import {
  clearComposerDraft,
  getSessionComposerDraftStorage,
  readComposerDraft,
  writeComposerDraft,
  type ComposerDraft,
} from "./composer-draft";

/** Lifecycle events fired for one submitted turn, in submission order. */
export type TurnSubmitLifecycle = {
  /**
   * The send passed the fence and is genuinely dispatched. Never fires on a
   * dropped path, so callers can safely run one-time cleanup (e.g. clearing
   * quoted references) without losing state when a concurrent send is dropped.
   */
  onSent?: () => void;
  /** The submission failed before dispatch, or the dispatched run errored. */
  onSendFailed?: () => void;
  /** The dispatched run finished. */
  onSendCompleted?: () => void;
};

/**
 * Per-send metadata riding the dispatch. Structurally the subset of the
 * stream `SendMessageOptions` the turn chain owns — the lifecycle callbacks
 * are intentionally absent: the gate owns them once the turn opens.
 */
export type TurnDispatchOptions = {
  additionalKwargs?: Record<string, unknown>;
  additionalInputMessages?: Message[];
  preuploadedFiles?: ReadonlyMap<File, UploadedFileInfo>;
  preuploadedCodePackages?: ReadonlyMap<File, CodeEvidencePackage>;
  traceId?: string;
  /**
   * Thread IDs of conversations the user attached for this run. They ride in
   * `context.conversation_references`, which the Gateway consumes at
   * admission (see `SendMessageOptions.conversationReferences`).
   */
  conversationReferences?: string[];
};

export type TurnDispatchRequest = {
  threadId: string;
  message: PromptInputMessage;
  extraContext?: Record<string, unknown>;
  options?: TurnDispatchOptions;
};

export type TurnSubmitRequest = {
  threadId: string;
  message: PromptInputMessage;
  /** Run-request context contributed by the page (selection/agent binding). */
  extraContext?: Record<string, unknown>;
  /** Per-send metadata riding the dispatch (kwargs, quotes, references). */
  options?: TurnDispatchOptions;
  /** Caller side effects fired at the corresponding lifecycle point. */
  lifecycle?: TurnSubmitLifecycle;
  /** Draft ports; omitting them disables the submit-chain draft policy. */
  draft?: TurnSubmitDraftPorts;
  /** UI surface for pre-upload failures (composer toast), per submission. */
  onPreuploadError?: (error: unknown) => void;
};

/**
 * The composer-owned draft surface the submit-chain draft policy runs
 * against. Storage reads/writes go through `composer-draft.ts` directly;
 * these ports cover the composer's live in-memory draft machine only.
 */
export type TurnSubmitDraftPorts = {
  /** Draft storage key this submission's draft is held under. */
  key: string;
  /** Draft captured at submit entry; restored when the send drops or fails. */
  pending: ComposerDraft;
  /** The composer's currently tracked draft (latest typed/kept draft). */
  tracked(): { key: string; draft: ComposerDraft } | null;
  /** The composer's currently visible draft view. */
  visible(): { key: string; draft: ComposerDraft };
  /** Point the composer's tracked draft at `draft`. */
  track(draft: ComposerDraft): void;
  /** Drop the tracked draft and cancel the composer's debounced save. */
  forget(): void;
  /** Push text and skill selection back into the composer (failure restore). */
  restore(draft: ComposerDraft): void;
};

/**
 * The single duplicate-submission fence plus the active turn's lifecycle.
 *
 * One instance is shared per thread view: the controller opens coordinated
 * turns (composer submit chain), the stream module enters the send phase
 * through `beginSend` (also covering direct senders with an anonymous turn),
 * and the stream's error/finish events terminate the turn. The lifecycle
 * callbacks ride the gate instead of third-party refs, so exactly one
 * submission's callbacks are registered at a time and a terminal stream
 * event reaches the submission that is actually in flight.
 */
export type TurnSubmitGate = {
  /**
   * Open a coordinated turn. Returns false when a turn is already open or
   * the same draft key is still held by an unsettled submission.
   */
  openTurn(lifecycle: TurnSubmitLifecycle, draftKey?: string): boolean;
  /**
   * Enter the send phase. Joins an open coordinated turn (its lifecycle
   * wins) or opens an anonymous turn for direct senders. Returns false when
   * the send phase is already running.
   */
  beginSend(lifecycle?: TurnSubmitLifecycle): boolean;
  /** Fire `onSent` exactly once; a no-op when the send was dropped. */
  markDispatched(): void;
  /** Settle the send phase and release the fence. */
  endSend(): void;
  /** Terminal failure: fire `onSendFailed` once and clear the lifecycle. */
  failTurn(): void;
  /** Terminal success: fire `onSendCompleted` once and clear the lifecycle. */
  completeTurn(): void;
  /** Abort a coordinated turn before dispatch, silently. */
  closeTurn(): void;
  /**
   * The conversation moved on (thread switch, unmount): silently clear any
   * open turn and draft hold, and bump the staleness generation.
   */
  invalidate(): void;
  /** Staleness generation; capture and compare around async preparation. */
  generation(): number;
  /** Arm the draft hold for `key` (blocks same-key re-submits until terminal). */
  armDraftHold(key: string): void;
  isDraftHeld(key: string): boolean;
  /** Release the draft hold (typing machine contract, navigation cleanup). */
  releaseDraftHold(): void;
  /** Whether a submission is open or a draft hold is armed. */
  hasActiveSubmission(): boolean;
};

export function createTurnSubmitGate(): TurnSubmitGate {
  let turnOpen = false;
  let sendEntered = false;
  let dispatched = false;
  let lifecycle: TurnSubmitLifecycle | null = null;
  let heldDraftKey: string | null = null;
  let generation = 0;

  const resetTurn = () => {
    turnOpen = false;
    sendEntered = false;
    dispatched = false;
    lifecycle = null;
    heldDraftKey = null;
  };

  return {
    openTurn(next, draftKey) {
      if (turnOpen || (draftKey != null && heldDraftKey === draftKey)) {
        return false;
      }
      turnOpen = true;
      sendEntered = false;
      dispatched = false;
      lifecycle = next;
      return true;
    },

    beginSend(next) {
      if (turnOpen) {
        if (sendEntered) {
          return false;
        }
        sendEntered = true;
        return true;
      }
      turnOpen = true;
      sendEntered = true;
      dispatched = false;
      lifecycle = next ?? null;
      return true;
    },

    markDispatched() {
      if (dispatched) {
        return;
      }
      dispatched = true;
      lifecycle?.onSent?.();
    },

    endSend() {
      if (!sendEntered) {
        return;
      }
      sendEntered = false;
      turnOpen = false;
    },

    failTurn() {
      const onSendFailed = lifecycle?.onSendFailed;
      lifecycle = null;
      heldDraftKey = null;
      onSendFailed?.();
    },

    completeTurn() {
      const onSendCompleted = lifecycle?.onSendCompleted;
      lifecycle = null;
      heldDraftKey = null;
      onSendCompleted?.();
    },

    closeTurn() {
      resetTurn();
    },

    invalidate() {
      generation += 1;
      resetTurn();
    },

    generation() {
      return generation;
    },

    armDraftHold(key) {
      heldDraftKey = key;
    },

    isDraftHeld(key) {
      return heldDraftKey === key;
    },

    releaseDraftHold() {
      heldDraftKey = null;
    },

    hasActiveSubmission() {
      return turnOpen || heldDraftKey !== null;
    },
  };
}

export type TurnSubmitPorts = {
  /** The shared fence instance also passed to `useThreadStream`. */
  gate: TurnSubmitGate;
  /** Dispatch the prepared turn through the stream module (page-bound). */
  send: (request: TurnDispatchRequest) => Promise<void>;
  /** Pre-dispatch preparation (e.g. project-scoped thread pre-create). */
  prepare?: () => Promise<void>;
  /** Page admission guard; returning false drops the submission silently. */
  admit?: () => boolean;
  /**
   * Run-request context contributed by the page (selection/agent binding);
   * applied when the submit request does not carry its own extraContext.
   */
  extraContext?: () => Record<string, unknown> | undefined;
  /** Attachment upload; defaults to the shared uploads API. */
  upload?: (
    threadId: string,
    files: File[],
    traceId?: string,
  ) => Promise<TurnUploadResult>;
};

export type TurnUploadResult = {
  files: UploadedFileInfo[];
  code_packages?: CodeEvidencePackage[];
  trace_id?: string;
};

export type TurnSubmitController = {
  /** The one submit entry for a turn's message chain. */
  submit(request: TurnSubmitRequest): Promise<void>;
  /** Invalidate in-flight submissions (thread switch / unmount cleanup). */
  invalidate(): void;
  /** Pre-upload one attachment, deduplicating concurrent calls per file. */
  preupload(file: File, threadId: string): Promise<UploadedFileInfo>;
  /**
   * Reconcile the pre-upload store with the composer's current attachments:
   * reset for a lazy new thread, prune removed files, rotate the trace id.
   */
  syncPreuploads(args: { threadId: string; files: File[] }): void;
  /** Whether a submission is open or a draft hold is armed. */
  hasPendingSubmission(): boolean;
  /** Typing machine contract: is this key's draft held by a submission? */
  shouldHoldDraftFor(key: string): boolean;
  /** Typing machine contract: a typed draft releases the hold. */
  releaseDraftHold(): void;
};

/**
 * The submit-chain draft policy: hold the composer's draft across the send,
 * persist it once the send is dispatched, restore it when the send drops or
 * fails, and clear it on completion unless a newer draft was typed meanwhile.
 */
function createTurnDraftPolicy(
  draft: TurnSubmitDraftPorts | undefined,
  gate: TurnSubmitGate,
) {
  if (!draft) {
    const noop = () => undefined;
    return {
      dispatched: noop,
      failed: noop,
      completed: noop,
      dropForFileSend: noop,
      restorePending: noop,
    };
  }
  let sendDispatched = false;
  const storage = () => getSessionComposerDraftStorage();
  const visibleIsEmptyForThisKey = () => {
    const visible = draft.visible();
    return (
      visible.key === draft.key &&
      !visible.draft.text &&
      !visible.draft.skillName
    );
  };
  return {
    dispatched() {
      sendDispatched = true;
      draft.forget();
      draft.track(draft.pending);
      writeComposerDraft(storage(), draft.key, draft.pending);
    },
    failed() {
      if (gate.isDraftHeld(draft.key)) {
        gate.releaseDraftHold();
        draft.forget();
      }
      if (visibleIsEmptyForThisKey()) {
        draft.restore(draft.pending);
      }
    },
    completed() {
      const saved = readComposerDraft(storage(), draft.key);
      const tracked = draft.tracked();
      const visible = draft.visible();
      const hasNewDraft =
        (tracked?.key === draft.key &&
          (tracked.draft.text !== draft.pending.text ||
            tracked.draft.skillName !== draft.pending.skillName)) ||
        (visible.key === draft.key &&
          Boolean(visible.draft.text || visible.draft.skillName) &&
          (visible.draft.text !== draft.pending.text ||
            visible.draft.skillName !== draft.pending.skillName));
      if (
        !hasNewDraft &&
        saved?.text === draft.pending.text &&
        saved?.skillName === draft.pending.skillName
      ) {
        clearComposerDraft(storage(), draft.key);
      }
      if (!hasNewDraft) {
        // The gate releases the draft hold before this terminal callback
        // runs, so the hold state cannot be observed here. Drop the tracked
        // pending draft whenever no newer draft took over: this is the only
        // reset that stops the composer's next flush (thread switch,
        // pagehide) from re-persisting the submitted text as a draft.
        gate.releaseDraftHold();
        draft.forget();
      }
    },
    restorePending() {
      if (sendDispatched || !gate.isDraftHeld(draft.key)) {
        return;
      }
      gate.releaseDraftHold();
      draft.track(draft.pending);
      writeComposerDraft(storage(), draft.key, draft.pending);
    },
    dropForFileSend() {
      // A file send on an existing thread drops the persisted draft at entry,
      // before the pre-upload round trips (a browser death mid-upload must
      // not resurrect a stale draft).
      draft.forget();
      clearComposerDraft(storage(), draft.key);
    },
  };
}

export function createTurnSubmitController(
  ports: TurnSubmitPorts,
): TurnSubmitController {
  const gate = ports.gate;
  const upload =
    ports.upload ??
    ((threadId: string, files: File[], traceId?: string) =>
      uploadFiles(threadId, files, traceId));

  // Attachment pre-uploads for existing threads: results are reused at
  // dispatch so upload time stays off the send-to-first-token path.
  const preuploadedFiles = new Map<File, UploadedFileInfo>();
  const preuploadedCodePackages = new Map<File, CodeEvidencePackage>();
  const preuploadPromises = new Map<File, Promise<UploadedFileInfo>>();
  let attachmentTraceId: string | null = null;

  const preupload = (file: File, threadId: string) => {
    const uploaded = preuploadedFiles.get(file);
    if (uploaded) {
      return Promise.resolve(uploaded);
    }
    const existing = preuploadPromises.get(file);
    if (existing) {
      return existing;
    }
    const promise = (async () => {
      const response = await upload(
        threadId,
        [file],
        attachmentTraceId ?? undefined,
      );
      const uploadedFile = response.files[0];
      if (!uploadedFile) {
        throw new Error(`Failed to upload attachment: ${file.name}`);
      }
      preuploadedFiles.set(file, uploadedFile);
      const codePackage = response.code_packages?.[0];
      if (codePackage) {
        preuploadedCodePackages.set(file, codePackage);
      }
      attachmentTraceId ??= response.trace_id ?? null;
      return uploadedFile;
    })();
    preuploadPromises.set(file, promise);
    void promise
      .finally(() => {
        if (preuploadPromises.get(file) === promise) {
          preuploadPromises.delete(file);
        }
      })
      .catch(() => undefined);
    return promise;
  };

  const resetPreuploads = () => {
    preuploadedFiles.clear();
    preuploadedCodePackages.clear();
    preuploadPromises.clear();
    attachmentTraceId = null;
  };

  return {
    async submit(request: TurnSubmitRequest) {
      const status = { dispatched: false };
      const policy = createTurnDraftPolicy(request.draft, gate);
      const composed: TurnSubmitLifecycle = {
        onSent: () => {
          status.dispatched = true;
          policy.dispatched();
          request.lifecycle?.onSent?.();
        },
        onSendFailed: () => {
          policy.failed();
          request.lifecycle?.onSendFailed?.();
        },
        onSendCompleted: () => {
          policy.completed();
          request.lifecycle?.onSendCompleted?.();
        },
      };
      if (!gate.openTurn(composed, request.draft?.key)) {
        throw new Error("A message is already being submitted.");
      }
      const submissionGeneration = gate.generation();

      try {
        gate.armDraftHold(request.draft?.key ?? "");
        if (ports.admit && !ports.admit()) {
          return;
        }
        const hasFiles = (request.message.files?.length ?? 0) > 0;
        const canPreupload = hasFiles && request.threadId !== "new";
        let dispatchOptions: TurnDispatchOptions | undefined = request.options;
        if (canPreupload) {
          // A file send must not resurrect a stale persisted draft if the
          // browser dies mid-upload: drop it before the network round trips.
          policy.dropForFileSend();
          try {
            const converted = await Promise.all(
              request.message.files.map((filePart) =>
                promptInputFilePartToFile(filePart),
              ),
            );
            const preuploads = new Map<File, UploadedFileInfo>();
            const codePackages = new Map<File, CodeEvidencePackage>();
            for (const file of converted) {
              if (!file) {
                throw new Error("Failed to prepare an attachment for upload.");
              }
              preuploads.set(file, await preupload(file, request.threadId));
              const codePackage = preuploadedCodePackages.get(file);
              if (codePackage) {
                codePackages.set(file, codePackage);
              }
            }
            if (codePackages.size > 1) {
              throw new Error("Upload one code ZIP per message.");
            }
            dispatchOptions = {
              ...request.options,
              preuploadedFiles: preuploads,
              preuploadedCodePackages: codePackages,
              traceId: attachmentTraceId ?? undefined,
            };
          } catch (error) {
            request.onPreuploadError?.(error);
            throw error;
          }
        }
        if (ports.prepare) {
          await ports.prepare();
        }
        if (gate.generation() !== submissionGeneration) {
          // The conversation moved on while preparation ran: drop the
          // submission so it cannot start a run for the abandoned thread.
          throw new Error("thread-submission-stale");
        }
        await ports.send({
          threadId: request.threadId,
          message: request.message,
          extraContext: request.extraContext ?? ports.extraContext?.(),
          options: dispatchOptions,
        });
      } finally {
        if (!status.dispatched) {
          // Dropped before dispatch (admission, preparation, pre-upload,
          // staleness): put the composer's draft back and release the fence
          // silently so a retry can proceed.
          policy.restorePending();
          gate.closeTurn();
        }
      }
    },

    invalidate() {
      gate.invalidate();
    },

    preupload,

    syncPreuploads({ threadId, files }) {
      if (threadId === "new") {
        resetPreuploads();
        return;
      }
      attachmentTraceId = files.length
        ? (attachmentTraceId ?? crypto.randomUUID())
        : null;
      const activeFiles = new Set(files);
      for (const file of [...preuploadedFiles.keys()]) {
        if (!activeFiles.has(file)) {
          preuploadedFiles.delete(file);
          preuploadedCodePackages.delete(file);
        }
      }
    },

    hasPendingSubmission() {
      return gate.hasActiveSubmission();
    },

    shouldHoldDraftFor(key) {
      return gate.isDraftHeld(key);
    },

    releaseDraftHold() {
      gate.releaseDraftHold();
    },
  };
}

export type ViewTurnSubmitArgs = {
  /** The view's shared fence, also passed to `useThreadStream`. */
  gate: TurnSubmitGate;
  /** The stream module's send, as returned by `useThreadStream`. */
  sendMessage: (
    threadId: string,
    message: PromptInputMessage,
    extraContext?: Record<string, unknown>,
    options?: TurnDispatchOptions,
  ) => Promise<void>;
  /** Pre-dispatch preparation (e.g. project-scoped thread pre-create). */
  prepare?: () => Promise<void>;
  /** Admission guard; returning false drops the submission silently. */
  admit?: () => boolean;
  /** Run-request context contributed by the page (selection/agent binding). */
  extraContext?: () => Record<string, unknown> | undefined;
};

/**
 * Page-side factory hook for the turn-submit controller. The page passes its
 * stream send plus its view-level prepare/admit/context closures; the hook
 * keeps the latest closures in a ref so the controller stays stable across
 * renders while the closures stay fresh at dispatch time.
 */
export function useViewTurnSubmit(
  args: ViewTurnSubmitArgs,
): TurnSubmitController {
  const latest = useRef(args);
  latest.current = args;
  const gate = args.gate;
  return useMemo(() => {
    const initial = latest.current;
    return createTurnSubmitController({
      gate,
      send: (request) =>
        latest.current.sendMessage(
          request.threadId,
          request.message,
          request.extraContext,
          request.options,
        ),
      // Ports stay conditional so a page without prepare/admit keeps the
      // stream dispatch synchronous with the submit call; each closure
      // re-reads `latest` so a fresh render's closures are honored.
      ...(initial.prepare
        ? {
            prepare: () =>
              latest.current.prepare
                ? latest.current.prepare()
                : Promise.resolve(),
          }
        : {}),
      ...(initial.admit
        ? {
            admit: () => (latest.current.admit ? latest.current.admit() : true),
          }
        : {}),
      ...(initial.extraContext
        ? { extraContext: () => latest.current.extraContext?.() }
        : {}),
    });
  }, [gate]);
}
