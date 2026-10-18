import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import type { AttachmentsContext } from "@/components/ai-elements/prompt-input";
import type { Translations } from "@/core/i18n/locales";
import {
  formatUploadSize,
  validateUploadLimits,
  type UploadLimits,
  type UploadLimitViolation,
} from "@/core/uploads";

/**
 * Attachment ownership for the composer: eager pre-uploads through the
 * turn-submit controller, upload-limit enforcement (reject + toast), and the
 * shared error/violation toast reporters.
 */
export function useInputBoxAttachments({
  threadId,
  attachmentParts,
  removeAttachment,
  uploadLimits,
  turnSubmit,
  t,
}: {
  threadId: string;
  attachmentParts: AttachmentsContext["files"];
  removeAttachment: AttachmentsContext["remove"];
  uploadLimits: UploadLimits | undefined;
  turnSubmit: {
    syncPreuploads: (input: { threadId: string; files: File[] }) => void;
    preupload: (file: File, threadId: string) => Promise<unknown>;
    hasPendingSubmission: () => boolean;
  };
  t: Translations;
}) {
  const notifyUploadError = useCallback(
    (error: unknown) => {
      toast.error(
        error instanceof Error ? error.message : "Failed to upload attachment.",
        { id: `upload-error-${threadId}` },
      );
    },
    [threadId],
  );

  // Eager attachment pre-uploads: the store, dedup, and trace id live in the
  // turn-submit controller; this effect only reconciles it with the
  // composer's current attachments and surfaces failures as toasts.
  useEffect(() => {
    if (threadId === "new") {
      turnSubmit.syncPreuploads({ threadId, files: [] });
      return;
    }
    if (!uploadLimits) {
      return;
    }

    const files = attachmentParts
      .map((part) => part.file)
      .filter((file): file is File => file instanceof File);
    const validation = validateUploadLimits([], files, uploadLimits);
    const rejectedFiles = new Set(validation.rejected);
    turnSubmit.syncPreuploads({ threadId, files });

    void Promise.all(
      files
        .filter((file) => !rejectedFiles.has(file))
        .map((file) => turnSubmit.preupload(file, threadId)),
    ).catch((error) => {
      // While a submission is pending, its own pre-upload path owns the
      // error surfacing; a background eager failure must not double-toast it.
      if (turnSubmit.hasPendingSubmission()) {
        return;
      }
      notifyUploadError(error);
    });
  }, [attachmentParts, notifyUploadError, threadId, turnSubmit, uploadLimits]);

  const reportUploadLimitViolations = useCallback(
    (violations: UploadLimitViolation[]) => {
      for (const violation of violations) {
        if (violation.code === "max_file_size") {
          toast.error(
            t.uploads.filesTooLarge(
              violation.files.map((file) => file.name).join(", "),
              formatUploadSize(violation.limit),
            ),
          );
        } else if (violation.code === "max_files") {
          toast.error(
            t.uploads.tooManyFiles(violation.files.length, violation.limit),
          );
        } else {
          toast.error(
            t.uploads.totalSizeTooLarge(
              violation.files.length,
              formatUploadSize(violation.limit),
            ),
          );
        }
      }
    },
    [t.uploads],
  );

  useEffect(() => {
    if (!uploadLimits) {
      return;
    }

    const attachmentEntries = attachmentParts.flatMap((attachment) =>
      attachment.file instanceof File
        ? [{ id: attachment.id, file: attachment.file }]
        : [],
    );
    const validation = validateUploadLimits(
      [],
      attachmentEntries.map(({ file }) => file),
      uploadLimits,
    );
    if (validation.rejected.length === 0) {
      return;
    }

    const rejected = new Set(validation.rejected);
    for (const entry of attachmentEntries) {
      if (rejected.has(entry.file)) {
        removeAttachment(entry.id);
      }
    }
    reportUploadLimitViolations(validation.violations);
  }, [
    attachmentParts,
    removeAttachment,
    reportUploadLimitViolations,
    uploadLimits,
  ]);

  return { notifyUploadError, reportUploadLimitViolations };
}
