import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { InputBox } from "@/components/workspace/input-box";
import { ThreadContext } from "@/components/workspace/messages/context";
import { AuthProvider } from "@/core/auth/AuthProvider";
import { DEFAULT_LOCALE } from "@/core/i18n";
import { I18nProvider } from "@/core/i18n/context";
import { buildComposerDraftKey } from "@/core/threads/composer-draft";

import { makeTurnSubmitTestController } from "./turn-submit-test-stub";

const skillState = rs.hoisted(() => ({
  skills: [
    {
      name: "research",
      description: "Research a topic",
      category: "general",
      license: "MIT",
      enabled: true,
      editable: false,
    },
  ],
  isLoading: false,
}));

rs.mock("next/navigation", () => ({
  useRouter: () => ({ push: rs.fn(), replace: rs.fn(), refresh: rs.fn() }),
  usePathname: () => "/workspace",
  useSearchParams: () => new URLSearchParams(),
}));

rs.mock("@/core/models/hooks", () => ({
  useModels: () => ({
    models: [],
    tokenUsageEnabled: false,
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: rs.fn(),
  }),
}));

rs.mock("@/core/skills/hooks", () => ({
  useSkills: () => ({
    skills: skillState.skills,
    isLoading: skillState.isLoading,
    error: null,
  }),
}));

const draftKey = buildComposerDraftKey({
  userId: "user-1",
  agentName: "researcher",
  threadId: "thread-1",
});

function renderComposer(allowedSkillNames?: readonly string[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <I18nProvider initialLocale={DEFAULT_LOCALE}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider
          initialUser={{
            id: "user-1",
            email: "user@example.test",
            system_role: "user",
            needs_setup: false,
            oauth_provider: null,
          }}
        >
          <ThreadContext.Provider
            value={{ thread: { messages: [] } as never, isMock: true }}
          >
            <PromptInputProvider>
              <InputBox
                threadId="thread-1"
                draftAgentName="researcher"
                allowedSkillNames={allowedSkillNames}
                context={{ mode: "flash" } as never}
                turnSubmit={makeTurnSubmitTestController().controller}
              />
            </PromptInputProvider>
          </ThreadContext.Provider>
        </AuthProvider>
      </QueryClientProvider>
    </I18nProvider>,
  );
}

afterEach(() => {
  rs.restoreAllMocks();
  window.sessionStorage.clear();
  cleanup();
});

describe("InputBox skill draft hydration", () => {
  it("waits for the skill catalog before restoring a saved skill chip", async () => {
    window.sessionStorage.setItem(
      draftKey,
      JSON.stringify({ version: 1, text: "topic", skillName: "research" }),
    );
    skillState.isLoading = true;

    const view = renderComposer(["research"]);

    expect(
      screen.queryByRole("button", { name: "Remove /research" }),
    ).toBeNull();
    expect(window.sessionStorage.getItem(draftKey)).toContain(
      '"skillName":"research"',
    );

    skillState.isLoading = false;
    view.rerender(
      <I18nProvider initialLocale={DEFAULT_LOCALE}>
        <QueryClientProvider
          client={
            new QueryClient({
              defaultOptions: {
                queries: { retry: false },
                mutations: { retry: false },
              },
            })
          }
        >
          <AuthProvider
            initialUser={{
              id: "user-1",
              email: "user@example.test",
              system_role: "user",
              needs_setup: false,
              oauth_provider: null,
            }}
          >
            <ThreadContext.Provider
              value={{ thread: { messages: [] } as never, isMock: true }}
            >
              <PromptInputProvider>
                <InputBox
                  threadId="thread-1"
                  draftAgentName="researcher"
                  allowedSkillNames={["research"]}
                  context={{ mode: "flash" } as never}
                  turnSubmit={makeTurnSubmitTestController().controller}
                />
              </PromptInputProvider>
            </ThreadContext.Provider>
          </AuthProvider>
        </QueryClientProvider>
      </I18nProvider>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Remove /research" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByRole("textbox").textContent).toBe("topic");
  });

  it("preserves inherit semantics when no allowlist is set", async () => {
    window.sessionStorage.setItem(
      draftKey,
      JSON.stringify({ version: 1, text: "topic", skillName: "research" }),
    );

    renderComposer(undefined);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Remove /research" }),
      ).toBeInTheDocument();
    });
  });

  it("folds the saved skill back into editable text when it is not offerable", async () => {
    window.sessionStorage.setItem(
      draftKey,
      JSON.stringify({ version: 1, text: "topic", skillName: "research" }),
    );

    renderComposer(["other-skill"]);

    await waitFor(() => {
      expect(screen.getByRole("textbox").textContent).toBe("/research topic");
    });
    expect(
      screen.queryByRole("button", { name: "Remove /research" }),
    ).toBeNull();
  });
});
