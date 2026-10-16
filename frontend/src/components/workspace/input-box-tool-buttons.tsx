import { MicIcon, PaperclipIcon, SquareIcon } from "lucide-react";

import {
  PromptInputButton,
  usePromptInputAttachments,
} from "@/components/ai-elements/prompt-input";
import { useI18n } from "@/core/i18n/hooks";
import { formatUploadSize, type UploadLimits } from "@/core/uploads";
import { cn } from "@/lib/utils";

import { Tooltip } from "./tooltip";

/** The mic toggle for voice dictation; hidden entirely when unsupported. */
export function VoiceInputButton({
  disabled,
  listening,
  supported,
  onToggle,
}: {
  disabled?: boolean;
  listening: boolean;
  supported: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const tooltipContent = !supported
    ? t.inputBox.voiceInputUnsupported
    : listening
      ? t.inputBox.voiceInputListening
      : t.inputBox.voiceInputStart;
  const label = listening
    ? t.inputBox.voiceInputStopLabel
    : t.inputBox.voiceInputStartLabel;

  return (
    <Tooltip content={<span className="block max-w-72">{tooltipContent}</span>}>
      <PromptInputButton
        aria-label={label}
        aria-pressed={listening}
        className={cn(
          "min-h-10 min-w-10 px-0!",
          listening && "text-primary bg-primary/10 hover:bg-primary/15",
        )}
        data-testid="voice-input-button"
        disabled={(disabled ?? false) || !supported}
        onClick={onToggle}
      >
        {listening ? (
          <SquareIcon className="size-4 fill-current" />
        ) : (
          <MicIcon className="size-4" />
        )}
      </PromptInputButton>
    </Tooltip>
  );
}

/** The paperclip button opening the file dialog, with upload-limit hints. */
export function AddAttachmentsButton({
  disabled,
  uploadLimits,
}: {
  disabled?: boolean;
  uploadLimits?: UploadLimits;
}) {
  const { t } = useI18n();
  const attachments = usePromptInputAttachments();
  const tooltipContent = uploadLimits
    ? t.uploads.limitsHint(
        uploadLimits.max_files,
        formatUploadSize(uploadLimits.max_file_size),
        formatUploadSize(uploadLimits.max_total_size),
      )
    : t.inputBox.addAttachments;
  return (
    <Tooltip content={<span className="block max-w-80">{tooltipContent}</span>}>
      <PromptInputButton
        aria-label={t.inputBox.addAttachments}
        className="min-h-10 min-w-10 px-0!"
        data-testid="add-attachments-button"
        disabled={disabled}
        onClick={() => attachments.openFileDialog()}
      >
        <PaperclipIcon className="size-4" />
      </PromptInputButton>
    </Tooltip>
  );
}
