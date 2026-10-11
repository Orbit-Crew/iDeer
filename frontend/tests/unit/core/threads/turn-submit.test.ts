import { act, render } from "@testing-library/react";
import { StrictMode, createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ComposerDraft } from "@/core/threads/composer-draft";
import {
  createTurnSubmitController,
  createTurnSubmitGate,
  useViewTurnSubmit,
  type TurnDispatchRequest,
  type TurnSubmitDraftPorts,
  type TurnSubmitLifecycle,
  type TurnSubmitRequest,
} from "@/core/threads/turn-submit";

const lifecycleSpy = (): TurnSubmitLifecycle => ({
  onSent: vi.fn(),
  onSendFailed: vi.fn(),
  onSendCompleted: vi.fn(),
});

describe("turn-submit gate", () => {
  it("engages the fence for one turn; a second open is rejected", () => {
    const gate = createTurnSubmitGate();
    expect(gate.openTurn(lifecycleSpy())).toBe(true);
    expect(gate.openTurn(lifecycleSpy())).toBe(false);
  });

  it("auto-opens an anonymous turn for direct senders and rejects a second send", () => {
    const gate = createTurnSubmitGate();
    expect(gate.beginSend()).toBe(true);
    expect(gate.beginSend()).toBe(false);
    gate.endSend();
    expect(gate.beginSend()).toBe(true);
  });

  it("lets a coordinated turn join the send phase once; a second join is rejected", () => {
    const gate = createTurnSubmitGate();
    gate.openTurn(lifecycleSpy());
    expect(gate.beginSend()).toBe(true);
    expect(gate.beginSend()).toBe(false);
  });

  it("fires onSent exactly once when the send is dispatched", () => {
    const gate = createTurnSubmitGate();
    const lifecycle = lifecycleSpy();
    gate.openTurn(lifecycle);
    gate.beginSend();
    gate.markDispatched();
    gate.markDispatched();
    expect(lifecycle.onSent).toHaveBeenCalledOnce();
  });

  it("never fires onSent on a dropped send", () => {
    const gate = createTurnSubmitGate();
    const lifecycle = lifecycleSpy();
    gate.openTurn(lifecycle);
    gate.closeTurn();
    expect(lifecycle.onSent).not.toHaveBeenCalled();
  });

  it("failTurn fires onSendFailed once and clears the lifecycle", () => {
    const gate = createTurnSubmitGate();
    const lifecycle = lifecycleSpy();
    gate.openTurn(lifecycle);
    gate.beginSend();
    gate.failTurn();
    gate.failTurn();
    gate.completeTurn();
    expect(lifecycle.onSendFailed).toHaveBeenCalledOnce();
    expect(lifecycle.onSendCompleted).not.toHaveBeenCalled();
  });

  it("completeTurn fires onSendCompleted once and clears the lifecycle", () => {
    const gate = createTurnSubmitGate();
    const lifecycle = lifecycleSpy();
    gate.openTurn(lifecycle);
    gate.beginSend();
    gate.completeTurn();
    gate.completeTurn();
    gate.failTurn();
    expect(lifecycle.onSendCompleted).toHaveBeenCalledOnce();
    expect(lifecycle.onSendFailed).not.toHaveBeenCalled();
  });

  it("terminal events without an active lifecycle are no-ops", () => {
    const gate = createTurnSubmitGate();
    expect(() => gate.failTurn()).not.toThrow();
    expect(() => gate.completeTurn()).not.toThrow();
    expect(() => gate.markDispatched()).not.toThrow();
    expect(() => gate.endSend()).not.toThrow();
  });

  it("invalidate clears the turn silently and re-opens the fence", () => {
    const gate = createTurnSubmitGate();
    const lifecycle = lifecycleSpy();
    gate.openTurn(lifecycle);
    gate.invalidate();
    expect(lifecycle.onSent).not.toHaveBeenCalled();
    expect(lifecycle.onSendFailed).not.toHaveBeenCalled();
    expect(gate.openTurn(lifecycleSpy())).toBe(true);
  });

  it("bumps the generation on invalidate so stale continuations can be detected", () => {
    const gate = createTurnSubmitGate();
    const before = gate.generation();
    gate.invalidate();
    expect(gate.generation()).toBe(before + 1);
  });
});

// ── Controller: one submit entry for the whole chain ────────────────

function makeRequest(
  overrides: Partial<TurnSubmitRequest> = {},
): TurnSubmitRequest {
  return {
    threadId: "thread-1",
    message: { text: "hello", files: [] },
    ...overrides,
  };
}

function makeController(
  overrides: {
    gate?: ReturnType<typeof createTurnSubmitGate>;
    send?: (request: TurnDispatchRequest) => Promise<void>;
    prepare?: () => Promise<void>;
    admit?: () => boolean;
    upload?: (
      threadId: string,
      files: File[],
      traceId?: string,
    ) => Promise<UploadResponse>;
  } = {},
) {
  const gate = overrides.gate ?? createTurnSubmitGate();
  const send =
    overrides.send ??
    vi.fn(async (request: TurnDispatchRequest) => {
      if (!gate.beginSend()) {
        return;
      }
      gate.markDispatched();
      gate.endSend();
      void request;
    });
  const controller = createTurnSubmitController({
    gate,
    send,
    ...(overrides.prepare ? { prepare: overrides.prepare } : {}),
    ...(overrides.admit ? { admit: overrides.admit } : {}),
    ...(overrides.upload ? { upload: overrides.upload } : {}),
  });
  return { gate, send, controller };
}

describe("turn-submit controller", () => {
  it("dispatches one prepared turn through the send port", async () => {
    const { send, controller } = makeController();
    await controller.submit(
      makeRequest({
        extraContext: { agent_name: "analyst" },
        options: {
          additionalKwargs: { files: [] },
          conversationReferences: ["thread-9"],
        },
      }),
    );
    expect(send).toHaveBeenCalledOnce();
    const request = (send as ReturnType<typeof vi.fn>).mock.calls[0]![0] as
      | TurnDispatchRequest
      | undefined;
    expect(request?.threadId).toBe("thread-1");
    expect(request?.extraContext).toEqual({ agent_name: "analyst" });
    expect(request?.options?.additionalKwargs).toEqual({ files: [] });
    // Attached-conversation references ride the dispatch untouched.
    expect(request?.options?.conversationReferences).toEqual(["thread-9"]);
  });

  it("rejects a duplicate submit while one is pending and never dispatches it", async () => {
    let releaseSend!: () => void;
    const gate = createTurnSubmitGate();
    const send = vi.fn(async () => {
      gate.beginSend();
      gate.markDispatched();
      // The dispatched run is in flight (the stream submit has not settled).
      await new Promise<void>((resolve) => {
        releaseSend = resolve;
      });
      gate.endSend();
    });
    const { controller } = makeController({ gate, send });
    const first = controller.submit(makeRequest());
    // The first submit reaches its dispatch synchronously; the run is in
    // flight while `first` is still pending.
    await Promise.resolve();
    await expect(
      controller.submit(
        makeRequest({ message: { text: "second", files: [] } }),
      ),
    ).rejects.toThrow("A message is already being submitted.");
    releaseSend();
    await first;
    expect(send).toHaveBeenCalledOnce();
  });

  it("drops silently when the page admission guard rejects", async () => {
    const send = vi.fn(async () => undefined);
    const { controller } = makeController({ admit: () => false, send });
    await expect(controller.submit(makeRequest())).resolves.toBeUndefined();
    expect(send).not.toHaveBeenCalled();
  });

  it("rejects with the prepare error and releases the fence", async () => {
    const prepare = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(new Error("project unavailable"))
      .mockResolvedValue(undefined);
    const send = vi.fn(async () => undefined);
    const { controller } = makeController({ prepare, send });
    await expect(controller.submit(makeRequest())).rejects.toThrow(
      "project unavailable",
    );
    expect(send).not.toHaveBeenCalled();
    // The fence is released: a retry goes through.
    await expect(controller.submit(makeRequest())).resolves.toBeUndefined();
  });

  it("rejects a stale continuation after navigation and never dispatches", async () => {
    const gate = createTurnSubmitGate();
    let invalidated = false;
    const send = vi.fn(async () => undefined);
    const { controller } = makeController({
      gate,
      send,
      prepare: () => {
        if (!invalidated) {
          invalidated = true;
          gate.invalidate();
        }
        return Promise.resolve();
      },
    });
    await expect(controller.submit(makeRequest())).rejects.toThrow(
      "thread-submission-stale",
    );
    expect(send).not.toHaveBeenCalled();
    await expect(controller.submit(makeRequest())).resolves.toBeUndefined();
  });

  it("composes caller lifecycle side effects with the submission", async () => {
    const { gate, controller } = makeController();
    const lifecycle = lifecycleSpy();
    await controller.submit(makeRequest({ lifecycle }));
    expect(lifecycle.onSent).toHaveBeenCalledOnce();
    gate.completeTurn();
    expect(lifecycle.onSendCompleted).toHaveBeenCalledOnce();
    expect(lifecycle.onSendFailed).not.toHaveBeenCalled();
  });
});

// ── Submit-chain draft policy ────────────────────────────────────────

const DRAFT_KEY = "draft-key";
const PENDING_DRAFT: ComposerDraft = { text: "pending text", skillName: null };

type RecordingDraftPorts = TurnSubmitDraftPorts & {
  trackedState: { key: string; draft: ComposerDraft } | null;
  restoredIntoComposer: ComposerDraft[];
  forgotCount: number;
  /** Simulate the user typing a new draft while the send is in flight. */
  simulateType(draft: ComposerDraft): void;
};

/**
 * Records every submit-chain draft effect the module is allowed to request
 * from the composer. Storage effects (persist/clear/read) go through the
 * real sessionStorage so the policy's storage discipline is exercised too.
 */
function makeRecordingDraftPorts(
  options: {
    visible?: { key: string; draft: ComposerDraft };
  } = {},
): RecordingDraftPorts {
  const ports: RecordingDraftPorts = {
    key: DRAFT_KEY,
    pending: PENDING_DRAFT,
    trackedState: null,
    restoredIntoComposer: [],
    forgotCount: 0,
    tracked: () => ports.trackedState,
    visible: () =>
      options.visible ?? {
        key: DRAFT_KEY,
        draft: { text: "", skillName: null },
      },
    track: (draft) => {
      ports.trackedState = { key: ports.key, draft };
    },
    forget: () => {
      ports.forgotCount += 1;
      ports.trackedState = null;
    },
    restore: (draft) => {
      ports.restoredIntoComposer.push(draft);
    },
    simulateType: (draft) => {
      // The typing machine points the tracked draft at the new text and
      // persists it through its debounced save.
      ports.trackedState = { key: ports.key, draft };
      writeDraft(ports.key, draft);
    },
  };
  return ports;
}

function writeDraft(key: string, draft: ComposerDraft) {
  window.sessionStorage.setItem(
    key,
    JSON.stringify({
      version: 1,
      text: draft.text,
      skillName: draft.skillName,
    }),
  );
}

function readDraft(key: string): ComposerDraft | null {
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  const parsed = JSON.parse(raw) as { text: string; skillName: string | null };
  return { text: parsed.text, skillName: parsed.skillName };
}

function makeStreamSendForGate(gate: ReturnType<typeof createTurnSubmitGate>) {
  return vi.fn(async () => {
    if (!gate.beginSend()) {
      return;
    }
    gate.markDispatched();
    gate.endSend();
  });
}

describe("turn-submit draft policy", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("persists the pending draft at dispatch and clears it on completion when untouched", async () => {
    const gate = createTurnSubmitGate();
    const { controller } = makeController({
      gate,
      send: makeStreamSendForGate(gate),
    });
    const draftPorts = makeRecordingDraftPorts();
    await controller.submit(makeRequest({ draft: draftPorts }));
    expect(readDraft(DRAFT_KEY)).toEqual(PENDING_DRAFT);
    expect(draftPorts.trackedState?.draft).toEqual(PENDING_DRAFT);
    // The stream finishes untouched: the stored draft is cleared again and
    // the typing machine's hold is released.
    gate.completeTurn();
    expect(readDraft(DRAFT_KEY)).toBeNull();
    expect(draftPorts.forgotCount).toBeGreaterThan(0);
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(false);
  });

  it("drops the tracked pending draft on completion so a later flush cannot resurrect it", async () => {
    const gate = createTurnSubmitGate();
    const { controller } = makeController({
      gate,
      send: makeStreamSendForGate(gate),
    });
    const draftPorts = makeRecordingDraftPorts();
    await controller.submit(makeRequest({ draft: draftPorts }));
    // In flight: the tracked draft holds the submitted text for the typing
    // machine (a mid-stream pagehide flush must persist it).
    expect(draftPorts.trackedState?.draft).toEqual(PENDING_DRAFT);
    gate.completeTurn();
    expect(readDraft(DRAFT_KEY)).toBeNull();
    // The gate releases the hold before the terminal callback runs, so the
    // policy must drop the tracked draft on its own no-newer-draft
    // observation: otherwise the composer's next flush (thread switch,
    // pagehide) re-persists the submitted text and the conversation restores
    // it as a draft (e2e: keeps text and selected skill isolated while
    // switching conversations).
    expect(draftPorts.trackedState).toBeNull();
  });

  it("keeps the tracked draft on completion when a newer draft was typed during the send", async () => {
    const gate = createTurnSubmitGate();
    const { controller } = makeController({
      gate,
      send: makeStreamSendForGate(gate),
    });
    const draftPorts = makeRecordingDraftPorts();
    await controller.submit(makeRequest({ draft: draftPorts }));
    draftPorts.simulateType({ text: "newer draft", skillName: null });
    gate.completeTurn();
    expect(readDraft(DRAFT_KEY)).toEqual({
      text: "newer draft",
      skillName: null,
    });
    // The newer draft owns the tracked slot: the completion must not clobber
    // it with a forget.
    expect(draftPorts.trackedState?.draft).toEqual({
      text: "newer draft",
      skillName: null,
    });
  });

  it("does not clear the stored draft on completion when a newer draft was typed during the send", async () => {
    const { gate, controller } = makeController();
    const draftPorts = makeRecordingDraftPorts();
    await controller.submit(makeRequest({ draft: draftPorts }));
    draftPorts.simulateType({ text: "newer draft", skillName: null });
    gate.completeTurn();
    expect(readDraft(DRAFT_KEY)).toEqual({
      text: "newer draft",
      skillName: null,
    });
  });

  it("keeps the same draft key fenced after the send settles but before a terminal event", async () => {
    const { gate, controller } = makeController();
    const draftPorts = makeRecordingDraftPorts();
    await controller.submit(makeRequest({ draft: draftPorts }));
    // Send settled; the turn has not reached a terminal stream event yet.
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(true);
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).rejects.toThrow("A message is already being submitted.");
    // A terminal event releases the hold.
    gate.completeTurn();
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(false);
  });

  it("restores the draft into an empty composer and keeps it in storage when the send fails after dispatch", async () => {
    // Pinned contract: "sends that fail keep the draft" (0f632ade-era fixes;
    // e2e: keeps a conversation draft when sending fails).
    let attempts = 0;
    const gate = createTurnSubmitGate();
    // Mimics the stream module's send-side gate protocol on the failure path:
    // failTurn fires in the catch, endSend settles the send phase.
    const send = vi.fn(async () => {
      if (!gate.beginSend()) {
        return;
      }
      gate.markDispatched();
      try {
        attempts += 1;
        if (attempts === 1) {
          gate.failTurn();
          throw new Error("stream send failed");
        }
      } finally {
        gate.endSend();
      }
    });
    const { controller } = makeController({ gate, send });
    const draftPorts = makeRecordingDraftPorts();
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).rejects.toThrow("stream send failed");
    expect(draftPorts.restoredIntoComposer).toEqual([PENDING_DRAFT]);
    expect(readDraft(DRAFT_KEY)).toEqual(PENDING_DRAFT);
    // The fence and hold are released: a retry goes through.
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(false);
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).resolves.toBeUndefined();
  });

  it("skips the composer restore on failure when the visible composer is not empty", async () => {
    const { gate } = makeController();
    const draftPorts = makeRecordingDraftPorts({
      visible: {
        key: DRAFT_KEY,
        draft: { text: "user typed", skillName: null },
      },
    });
    const send = vi.fn(async () => {
      gate.beginSend();
      gate.markDispatched();
      gate.failTurn();
      gate.endSend();
      throw new Error("stream send failed");
    });
    const { controller } = makeController({ gate, send });
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).rejects.toThrow("stream send failed");
    gate.completeTurn();
    expect(draftPorts.restoredIntoComposer).toEqual([]);
  });

  it("ignores a stale visible draft (other conversation) when restoring on failure", async () => {
    const { gate } = makeController();
    const draftPorts = makeRecordingDraftPorts({
      visible: {
        key: "another-key",
        draft: { text: "", skillName: null },
      },
    });
    const send = vi.fn(async () => {
      gate.beginSend();
      gate.markDispatched();
      gate.failTurn();
      gate.endSend();
      throw new Error("stream send failed");
    });
    const { controller } = makeController({ gate, send });
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).rejects.toThrow("stream send failed");
    gate.completeTurn();
    expect(draftPorts.restoredIntoComposer).toEqual([]);
  });

  it("restores the pending draft when the submission is dropped before dispatch", async () => {
    const send = vi.fn(async () => undefined);
    const { gate, controller } = makeController({
      admit: () => false,
      send,
    });
    const draftPorts = makeRecordingDraftPorts();
    await expect(
      controller.submit(makeRequest({ draft: draftPorts })),
    ).resolves.toBeUndefined();
    expect(send).not.toHaveBeenCalled();
    // The dropped path re-points the tracked draft and persists it for the
    // next hydration; the visible restore is reserved for a dispatched
    // send's failure.
    expect(draftPorts.trackedState?.draft).toEqual(PENDING_DRAFT);
    expect(readDraft(DRAFT_KEY)).toEqual(PENDING_DRAFT);
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(false);
  });

  it("keeps the typing machine's draft hold contract", () => {
    const { gate, controller } = makeController();
    void controller;
    gate.openTurn(lifecycleSpy());
    gate.armDraftHold(DRAFT_KEY);
    // An emptied composer while the hold is armed must not overwrite the draft.
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(true);
    expect(controller.shouldHoldDraftFor(DRAFT_KEY)).toBe(true);
    // Typing a new draft releases the hold.
    controller.releaseDraftHold();
    expect(gate.isDraftHeld(DRAFT_KEY)).toBe(false);
  });

  it("exposes the pending-submission window for the eager preupload error suppression", async () => {
    let rejectPrepare: ((error: unknown) => void) | undefined;
    const { controller } = makeController({
      prepare: () =>
        new Promise<void>((_resolve, reject) => {
          rejectPrepare = reject;
        }),
    });
    const pending = controller.submit(makeRequest());
    await Promise.resolve();
    expect(controller.hasPendingSubmission()).toBe(true);
    rejectPrepare!(new Error("prepare aborted"));
    await expect(pending).rejects.toThrow("prepare aborted");
    expect(controller.hasPendingSubmission()).toBe(false);
  });
});

// ── Attachment pre-uploads ───────────────────────────────────────────

type UploadResponse = {
  files: Array<{
    filename: string;
    size: number;
    path: string;
    virtual_path: string;
    artifact_url: string;
  }>;
  trace_id?: string;
};

function makeUploadOk(filename = "report.pdf") {
  return vi.fn().mockResolvedValue({
    files: [
      {
        filename,
        size: 4,
        path: `/uploads/${filename}`,
        virtual_path: `/mnt/${filename}`,
        artifact_url: `/artifacts/${filename}`,
      },
    ],
    trace_id: "trace-1",
  } satisfies UploadResponse);
}

describe("turn-submit pre-uploads", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("preuploads attachments for an existing thread and attaches the results to the dispatch", async () => {
    const file = new File(["data"], "report.pdf");
    const upload = makeUploadOk();
    const { send, controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });
    await controller.submit(
      makeRequest({
        message: { text: "with file", files: [{ file } as never] },
      }),
    );
    expect(upload).toHaveBeenCalledOnce();
    expect(upload).toHaveBeenCalledWith("thread-1", [file], undefined);
    const request = (send as ReturnType<typeof vi.fn>).mock.calls[0]![0] as
      | TurnDispatchRequest
      | undefined;
    expect(request?.options?.preuploadedFiles?.get(file)).toMatchObject({
      filename: "report.pdf",
    });
    expect(request?.options?.traceId).toBe("trace-1");
  });

  it("keeps a code package returned by preupload through dispatch", async () => {
    const file = new File(["zip"], "source.zip", { type: "application/zip" });
    const upload = vi.fn().mockResolvedValue({
      files: [
        {
          filename: file.name,
          size: file.size,
          virtual_path: "/uploads/source.zip",
          artifact_url: "",
        },
      ],
      code_packages: [
        {
          package_id: "pkg-preupload",
          source_virtual_path:
            "/mnt/user-data/code-evidence/pkg-preupload/source",
        },
      ],
    });
    const { send, controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });

    await controller.submit(
      makeRequest({ message: { text: "analyze", files: [{ file } as never] } }),
    );

    const request = (send as ReturnType<typeof vi.fn>).mock
      .calls[0]![0] as TurnDispatchRequest;
    expect(request.options?.preuploadedFiles?.has(file)).toBe(true);
    expect(request.options).toMatchObject({
      preuploadedCodePackages: new Map([
        [
          file,
          {
            package_id: "pkg-preupload",
            source_virtual_path:
              "/mnt/user-data/code-evidence/pkg-preupload/source",
          },
        ],
      ]),
    });
  });

  it("deduplicates concurrent preuploads of the same file", async () => {
    const file = new File(["data"], "report.pdf");
    const upload = makeUploadOk();
    const { controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });
    await Promise.all([
      controller.preupload(file, "thread-1"),
      controller.preupload(file, "thread-1"),
    ]);
    expect(upload).toHaveBeenCalledOnce();
  });

  it("reports a preupload failure, releases the fence, and restores the draft", async () => {
    const file = new File(["data"], "report.pdf");
    const upload = vi.fn().mockRejectedValue(new Error("disk full"));
    const onPreuploadError = vi.fn();
    const { send, controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });
    const draftPorts = makeRecordingDraftPorts();
    await expect(
      controller.submit(
        makeRequest({
          message: { text: "with file", files: [{ file } as never] },
          draft: draftPorts,
          onPreuploadError,
        }),
      ),
    ).rejects.toThrow("disk full");
    expect(onPreuploadError).toHaveBeenCalledOnce();
    expect(send).not.toHaveBeenCalled();
    expect(draftPorts.trackedState?.draft).toEqual(PENDING_DRAFT);
    // The fence is released: a retry goes through.
    await expect(controller.submit(makeRequest())).resolves.toBeUndefined();
  });

  it("does not preupload for a lazy new thread; the stream module uploads instead", async () => {
    const file = new File(["data"], "report.pdf");
    const upload = makeUploadOk();
    const { send, controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });
    await controller.submit(
      makeRequest({
        threadId: "new",
        message: { text: "with file", files: [{ file } as never] },
      }),
    );
    expect(upload).not.toHaveBeenCalled();
    const request = (send as ReturnType<typeof vi.fn>).mock.calls[0]![0] as
      | TurnDispatchRequest
      | undefined;
    expect(request?.options?.preuploadedFiles).toBeUndefined();
  });

  it("syncPreuploads resets the store for a lazy new thread and prunes removed attachments", async () => {
    const file = new File(["data"], "report.pdf");
    const upload = makeUploadOk();
    const { controller } = makeController({
      upload: upload as unknown as (
        threadId: string,
        files: File[],
        traceId?: string,
      ) => Promise<UploadResponse>,
    });
    await controller.preupload(file, "thread-1");
    expect(upload).toHaveBeenCalledOnce();

    // Removing the attachment prunes the store entry: the next preupload
    // uploads again.
    controller.syncPreuploads({ threadId: "thread-1", files: [] });
    await controller.preupload(file, "thread-1");
    expect(upload).toHaveBeenCalledTimes(2);

    // Moving back to a lazy new thread resets everything.
    controller.syncPreuploads({ threadId: "new", files: [] });
    await controller.preupload(file, "thread-1");
    expect(upload).toHaveBeenCalledTimes(3);
  });
});

// ── useViewTurnSubmit: the page factory hook ─────────────────────────

describe("useViewTurnSubmit", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("keeps the controller stable across renders while closures stay fresh at dispatch", async () => {
    const gate = createTurnSubmitGate();
    const sendMessage = vi.fn(async () => {
      if (!gate.beginSend()) {
        return;
      }
      gate.markDispatched();
      gate.endSend();
    });

    let controller: ReturnType<typeof useViewTurnSubmit> | null = null;
    function Page({ label }: { label: string }) {
      controller = useViewTurnSubmit({
        gate,
        sendMessage,
        extraContext: () => ({ label }),
      });
      return null;
    }

    const { rerender } = render(createElement(Page, { label: "first" }));
    rerender(createElement(Page, { label: "second" }));
    const stable = controller;
    await act(async () => {
      await controller!.submit({
        threadId: "thread-1",
        message: { text: "hello", files: [] },
      });
    });
    // The closure captured at submit time is the latest render's.
    expect(stable).toBe(controller);
    expect(sendMessage).toHaveBeenCalledWith(
      "thread-1",
      { text: "hello", files: [] },
      { label: "second" },
      undefined,
    );
  });

  it("keeps the dispatch synchronous for a page without prepare when a turn is open", async () => {
    const gate = createTurnSubmitGate();
    gate.openTurn({}); // A turn is already open: the submit must be rejected.
    const sendMessage = vi.fn(async () => undefined);

    let controller: ReturnType<typeof useViewTurnSubmit> | null = null;
    function Page() {
      controller = useViewTurnSubmit({ gate, sendMessage });
      return null;
    }

    render(createElement(Page, {}));
    await act(async () => {
      await expect(
        controller!.submit({
          threadId: "thread-1",
          message: { text: "hello", files: [] },
        }),
      ).rejects.toThrow("A message is already being submitted.");
    });
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("renders under StrictMode without breaking the fence", async () => {
    const gate = createTurnSubmitGate();
    const sendMessage = vi.fn(async () => {
      if (!gate.beginSend()) {
        return;
      }
      gate.markDispatched();
      gate.endSend();
    });

    let controller: ReturnType<typeof useViewTurnSubmit> | null = null;
    function Page() {
      controller = useViewTurnSubmit({ gate, sendMessage });
      return null;
    }

    render(createElement(StrictMode, null, createElement(Page, {})));
    await act(async () => {
      await controller!.submit({
        threadId: "thread-1",
        message: { text: "hello", files: [] },
      });
    });
    expect(sendMessage).toHaveBeenCalledOnce();
  });
});
