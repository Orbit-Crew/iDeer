import {
  CheckIcon,
  GraduationCapIcon,
  LightbulbIcon,
  RocketIcon,
  ZapIcon,
} from "lucide-react";

import {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
} from "@/components/ai-elements/prompt-input";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import type { InputMode } from "./input-box-helpers";
import { ModeHoverGuide } from "./mode-hover-guide";

/** The flash/thinking/pro/ultra mode picker inside the composer tools row. */
export function ComposerModeMenu({
  mode,
  supportThinking,
  disabled,
  onSelect,
}: {
  mode: InputMode;
  supportThinking: boolean;
  disabled: boolean;
  onSelect: (mode: InputMode) => void;
}) {
  const { t } = useI18n();
  return (
    <PromptInputActionMenu>
      <ModeHoverGuide mode={mode}>
        <PromptInputActionMenuTrigger
          aria-label={t.inputBox.mode}
          className="max-w-28 gap-1! px-2! sm:max-w-none"
          disabled={disabled}
        >
          <div>
            {mode === "flash" && <ZapIcon className="size-3" />}
            {mode === "thinking" && <LightbulbIcon className="size-3" />}
            {mode === "pro" && <GraduationCapIcon className="size-3" />}
            {mode === "ultra" && (
              <RocketIcon className="size-3 text-[#dabb5e]" />
            )}
          </div>
          <div
            className={cn(
              "type-body truncate font-normal",
              mode === "ultra" ? "golden-text" : "",
            )}
          >
            {(mode === "flash" && t.inputBox.flashMode) ||
              (mode === "thinking" && t.inputBox.reasoningMode) ||
              (mode === "pro" && t.inputBox.proMode) ||
              (mode === "ultra" && t.inputBox.ultraMode)}
          </div>
        </PromptInputActionMenuTrigger>
      </ModeHoverGuide>
      <PromptInputActionMenuContent className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground type-compact">
            {t.inputBox.mode}
          </DropdownMenuLabel>
          <PromptInputActionMenu>
            <PromptInputActionMenuItem
              className={cn(
                mode === "flash"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("flash")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  <ZapIcon
                    className={cn(
                      "mr-2 size-4",
                      mode === "flash" && "text-accent-foreground",
                    )}
                  />
                  {t.inputBox.flashMode}
                </div>
                <div className="type-compact pl-7">
                  {t.inputBox.flashModeDescription}
                </div>
              </div>
              {mode === "flash" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
            {supportThinking && (
              <PromptInputActionMenuItem
                className={cn(
                  mode === "thinking"
                    ? "text-accent-foreground"
                    : "text-muted-foreground/65",
                )}
                onSelect={() => onSelect("thinking")}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-1 font-bold">
                    <LightbulbIcon
                      className={cn(
                        "mr-2 size-4",
                        mode === "thinking" && "text-accent-foreground",
                      )}
                    />
                    {t.inputBox.reasoningMode}
                  </div>
                  <div className="type-compact pl-7">
                    {t.inputBox.reasoningModeDescription}
                  </div>
                </div>
                {mode === "thinking" ? (
                  <CheckIcon className="ml-auto size-4" />
                ) : (
                  <div className="ml-auto size-4" />
                )}
              </PromptInputActionMenuItem>
            )}
            <PromptInputActionMenuItem
              className={cn(
                mode === "pro"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("pro")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  <GraduationCapIcon
                    className={cn(
                      "mr-2 size-4",
                      mode === "pro" && "text-accent-foreground",
                    )}
                  />
                  {t.inputBox.proMode}
                </div>
                <div className="type-compact pl-7">
                  {t.inputBox.proModeDescription}
                </div>
              </div>
              {mode === "pro" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
            <PromptInputActionMenuItem
              className={cn(
                mode === "ultra"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("ultra")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  <RocketIcon
                    className={cn(
                      "mr-2 size-4",
                      mode === "ultra" && "text-[#dabb5e]",
                    )}
                  />
                  <div className={cn(mode === "ultra" && "golden-text")}>
                    {t.inputBox.ultraMode}
                  </div>
                </div>
                <div className="type-compact pl-7">
                  {t.inputBox.ultraModeDescription}
                </div>
              </div>
              {mode === "ultra" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
          </PromptInputActionMenu>
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}

type ReasoningEffort = "minimal" | "low" | "medium" | "high";

/** The reasoning-effort picker shown when the selected model supports it. */
export function ComposerReasoningEffortMenu({
  effort,
  onSelect,
}: {
  effort: ReasoningEffort | undefined;
  onSelect: (effort: ReasoningEffort) => void;
}) {
  const { t } = useI18n();
  return (
    <PromptInputActionMenu>
      <PromptInputActionMenuTrigger className="hidden gap-1! px-2! sm:inline-flex">
        <div className="type-body font-normal">
          {t.inputBox.reasoningEffort}:
          {effort === "minimal" && " " + t.inputBox.reasoningEffortMinimal}
          {effort === "low" && " " + t.inputBox.reasoningEffortLow}
          {(!effort || effort === "medium") &&
            " " + t.inputBox.reasoningEffortMedium}
          {effort === "high" && " " + t.inputBox.reasoningEffortHigh}
        </div>
      </PromptInputActionMenuTrigger>
      <PromptInputActionMenuContent className="w-70">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground type-compact">
            {t.inputBox.reasoningEffort}
          </DropdownMenuLabel>
          <PromptInputActionMenu>
            <PromptInputActionMenuItem
              className={cn(
                effort === "minimal"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("minimal")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  {t.inputBox.reasoningEffortMinimal}
                </div>
                <div className="type-compact pl-2">
                  {t.inputBox.reasoningEffortMinimalDescription}
                </div>
              </div>
              {effort === "minimal" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
            <PromptInputActionMenuItem
              className={cn(
                effort === "low"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("low")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  {t.inputBox.reasoningEffortLow}
                </div>
                <div className="type-compact pl-2">
                  {t.inputBox.reasoningEffortLowDescription}
                </div>
              </div>
              {effort === "low" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
            <PromptInputActionMenuItem
              className={cn(
                !effort || effort === "medium"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("medium")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  {t.inputBox.reasoningEffortMedium}
                </div>
                <div className="type-compact pl-2">
                  {t.inputBox.reasoningEffortMediumDescription}
                </div>
              </div>
              {!effort || effort === "medium" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
            <PromptInputActionMenuItem
              className={cn(
                effort === "high"
                  ? "text-accent-foreground"
                  : "text-muted-foreground/65",
              )}
              onSelect={() => onSelect("high")}
            >
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-1 font-bold">
                  {t.inputBox.reasoningEffortHigh}
                </div>
                <div className="type-compact pl-2">
                  {t.inputBox.reasoningEffortHighDescription}
                </div>
              </div>
              {effort === "high" ? (
                <CheckIcon className="ml-auto size-4" />
              ) : (
                <div className="ml-auto size-4" />
              )}
            </PromptInputActionMenuItem>
          </PromptInputActionMenu>
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}
