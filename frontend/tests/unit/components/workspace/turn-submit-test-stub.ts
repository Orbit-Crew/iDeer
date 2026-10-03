import type {
  TurnSubmitController,
  TurnSubmitRequest,
} from "@/core/threads/turn-submit";
import type { UploadedFileInfo } from "@/core/uploads";

export const UPLOADED_FILE_INFO: UploadedFileInfo = {
  filename: "report.pdf",
  size: 4,
  path: "/uploads/report.pdf",
  virtual_path: "/mnt/report.pdf",
  artifact_url: "/artifacts/report.pdf",
};

/**
 * Wiring-smoke double for the turn-submit controller. The submit-chain
 * behaviors (fence, draft policy, pre-uploads) live in the module and are
 * covered by `tests/unit/core/threads/turn-submit.test.ts`; composer tests
 * only pin that a submit reaches the controller with the right request.
 *
 * Framework-agnostic on purpose: it records requests in a plain array so
 * both vitest and rstest files can share it.
 */
export function makeTurnSubmitTestController(
  options: {
    /** Extra dispatch-side effects; runs after the mirrored `onSent`. */
    onDispatch?: (request: TurnSubmitRequest) => void | Promise<void>;
    /** Replace the default settle (mirrored `onSendCompleted`). */
    onSettle?: (request: TurnSubmitRequest) => void;
  } = {},
): { controller: TurnSubmitController; requests: TurnSubmitRequest[] } {
  const requests: TurnSubmitRequest[] = [];
  const controller: TurnSubmitController = {
    async submit(request) {
      requests.push(request);
      // Mirror the real gate protocol: the dispatch fires `onSent` exactly
      // once, then the double settles the turn so completion cleanup runs.
      request.lifecycle?.onSent?.();
      await (options.onDispatch?.(request) ?? undefined);
      if (options.onSettle) {
        options.onSettle(request);
      } else {
        request.lifecycle?.onSendCompleted?.();
      }
    },
    invalidate: () => undefined,
    preupload: () => Promise.resolve(UPLOADED_FILE_INFO),
    syncPreuploads: () => undefined,
    hasPendingSubmission: () => false,
    shouldHoldDraftFor: () => false,
    releaseDraftHold: () => undefined,
  };
  return { controller, requests };
}
