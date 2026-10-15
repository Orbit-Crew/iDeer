export {
  SUGGESTION_TEMPLATE_PLACEHOLDER_PATTERN,
  findSuggestionTemplatePlaceholder,
} from "@/core/suggestions/placeholders";

import type { Message } from "@langchain/langgraph-sdk";

import type { SidecarContext } from "@/core/sidecar";

export const MAX_SKILL_SUGGESTIONS = 6;

export type InputMode = "flash" | "thinking" | "pro" | "ultra";

/** Resolve the effective mode against what the selected model supports. */
export function getResolvedMode(
  mode: InputMode | undefined,
  supportsThinking: boolean,
): InputMode {
  if (!supportsThinking && mode !== "flash") {
    return "flash";
  }
  if (mode) {
    return mode;
  }
  return supportsThinking ? "pro" : "flash";
}

function escapeXmlAttribute(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Build the hidden human message that carries quoted conversation context into
 * the next turn without rendering in the transcript.
 */
export function buildHiddenConversationQuoteMessage({
  contexts,
}: {
  contexts: SidecarContext[];
}): Message {
  return {
    type: "human",
    content: [
      {
        type: "text",
        text: [
          contexts.length === 1
            ? "The user added the following quoted context to this conversation."
            : `The user added the following ${contexts.length} quoted contexts to this conversation.`,
          "Use the referenced_message blocks as reference material for the user's next message.",
          "",
          ...contexts.flatMap((context, index) =>
            [
              `<referenced_message index="${index + 1}" label="${escapeXmlAttribute(
                context.label,
              )}">`,
              `Role: ${context.role === "user" ? "User" : "Assistant"}`,
              context.messageId ? `Message ID: ${context.messageId}` : null,
              "",
              context.content,
              "</referenced_message>",
              "",
            ].filter((line): line is string => line !== null),
          ),
        ]
          .filter((line): line is string => line !== null)
          .join("\n"),
      },
    ],
    additional_kwargs: {
      hide_from_ui: true,
      conversation_quote_context: true,
      // Keep ids/roles/count 1:1 parallel with `contexts` so consumers can zip
      // them safely; do not dedupe ids here.
      referenced_message_ids: contexts.map(
        (context) => context.messageId ?? "",
      ),
      referenced_message_roles: contexts.map((context) => context.role),
      quote_context_count: contexts.length,
    },
  } as Message;
}

// Mirror of the backend raw request limit (`ThreadGoalRequest.objective`
// max_length and `MAX_GOAL_OBJECTIVE_CHARS` in backend goal.py). Kept here so
// the composer can reject an over-length `/goal <objective>` before issuing the
// PUT request and show a friendly error instead of surfacing a raw HTTP 422.
export const MAX_GOAL_OBJECTIVE_CHARS = 4000;

export function isGoalObjectiveTooLong(objective: string): boolean {
  return objective.length > MAX_GOAL_OBJECTIVE_CHARS;
}

// The live composer counter stays hidden until the objective approaches the
// limit, so it only surfaces when the user is at risk of being rejected rather
// than adding permanent noise to the footer.
export const GOAL_OBJECTIVE_COUNTER_VISIBLE_AT = Math.floor(
  MAX_GOAL_OBJECTIVE_CHARS * 0.9,
);

export type GoalObjectiveCounter = {
  length: number;
  max: number;
  overLimit: boolean;
};

// Derive the live counter for the composer footer from the same parsed
// objective string sent to the API. Returns null unless the input is a
// `/goal <objective>` set command whose raw length has reached the visibility
// threshold, so the counter only appears for the case the limit actually
// applies to.
export function getGoalObjectiveCounter(
  value: string,
): GoalObjectiveCounter | null {
  const command = parseGoalCommand(value);
  if (command?.kind !== "set") {
    return null;
  }
  const length = command.objective.length;
  if (length < GOAL_OBJECTIVE_COUNTER_VISIBLE_AT) {
    return null;
  }
  return {
    length,
    max: MAX_GOAL_OBJECTIVE_CHARS,
    overLimit: length > MAX_GOAL_OBJECTIVE_CHARS,
  };
}

export type GoalCommand =
  | { kind: "status" }
  | { kind: "clear" }
  | { kind: "set"; objective: string };

export type InputSubmitAction =
  | { kind: "goal"; command: GoalCommand }
  | { kind: "compact" }
  | { kind: "stop" }
  | { kind: "empty" }
  | { kind: "message" };

export type GoalRequestState = {
  controller: AbortController | null;
  sequence: number;
  threadId: string | null;
};

export type ActiveGoalRequest = {
  controller: AbortController;
  sequence: number;
  threadId: string;
};

export function createGoalRequestState(): GoalRequestState {
  return {
    controller: null,
    sequence: 0,
    threadId: null,
  };
}

export function beginGoalRequest(
  state: GoalRequestState,
  threadId: string,
): ActiveGoalRequest {
  state.controller?.abort();
  const controller = new AbortController();
  const request = {
    controller,
    sequence: state.sequence + 1,
    threadId,
  };
  state.controller = controller;
  state.sequence = request.sequence;
  state.threadId = threadId;
  return request;
}

export function abortGoalRequest(state: GoalRequestState): void {
  state.controller?.abort();
  state.controller = null;
  state.sequence += 1;
  state.threadId = null;
}

export function finishGoalRequest(
  state: GoalRequestState,
  request: ActiveGoalRequest,
): void {
  if (
    state.controller === request.controller &&
    state.sequence === request.sequence
  ) {
    state.controller = null;
  }
}

export function isCurrentGoalRequest(
  state: GoalRequestState,
  request: ActiveGoalRequest,
  threadId: string,
): boolean {
  return (
    state.controller === request.controller &&
    state.sequence === request.sequence &&
    state.threadId === threadId &&
    !request.controller.signal.aborted
  );
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (typeof error === "object" &&
      error !== null &&
      Reflect.get(error, "name") === "AbortError")
  );
}

export function getLeadingSlashSkillQuery(value: string): string | null {
  if (!value.startsWith("/")) {
    return null;
  }

  const query = value.slice(1);
  if (query.includes("/") || /\s/.test(query)) {
    return null;
  }

  return query;
}

export function parseGoalCommand(value: string): GoalCommand | null {
  const trimmed = value.trim();
  const match = /^\/goal(?:\s+|$)/i.exec(trimmed);
  if (!match) {
    return null;
  }

  const args = trimmed.slice(match[0].length).trim();
  if (!args) {
    return { kind: "status" };
  }
  if (["clear", "reset", "off"].includes(args.toLowerCase())) {
    return { kind: "clear" };
  }
  return { kind: "set", objective: args };
}

export function parseCompactCommand(value: string): boolean {
  return /^\/(?:compact|context\s+compact)\s*$/i.test(value.trim());
}

export function canPolishInput(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  // Reserved builtin command lines are routed to their own handlers, not the
  // LLM, so they must not be rewritten. Reuse the same parsers the composer
  // uses to dispatch them instead of maintaining a third parallel list.
  return parseGoalCommand(trimmed) === null && !parseCompactCommand(trimmed);
}

export function getInputSubmitAction({
  text,
  fileCount,
  status,
}: {
  text: string;
  fileCount: number;
  status: string;
}): InputSubmitAction {
  const goalCommand = parseGoalCommand(text);
  if (goalCommand && fileCount === 0) {
    return { kind: "goal", command: goalCommand };
  }
  if (parseCompactCommand(text) && fileCount === 0) {
    return { kind: "compact" };
  }
  if (status === "streaming") {
    return { kind: "stop" };
  }
  if (!text.trim() && fileCount === 0) {
    return { kind: "empty" };
  }
  return { kind: "message" };
}

export async function readGoalResponseError(
  response: Response,
): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Fall through to generic message.
  }
  return `HTTP ${response.status}`;
}
