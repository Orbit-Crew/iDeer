import { describe, expect, it } from "vitest";

import { enUS } from "@/core/i18n/locales/en-US";

// A locale entry must be a non-empty string. This upgrades the previous
// `toBeTruthy()` sweep, which silently passed empty strings — exactly the
// regression mode for translation keys. The path argument makes a failure
// point at the offending key (vitest renders the second expect argument).
function expectNonEmptyString(value: unknown, path: string): void {
  expect(
    value,
    `enUS.${path} must be a non-empty string, got ${JSON.stringify(value)}`,
  ).satisfies((v: unknown) => typeof v === "string" && v.length > 0);
}

describe("en-US translations", () => {
  describe("locale meta", () => {
    it("has locale.localName as English", () => {
      expect(enUS.locale.localName).toBe("English");
    });
  });

  describe("common section", () => {
    it("has all expected string keys", () => {
      const expectedKeys = [
        "home",
        "settings",
        "delete",
        "edit",
        "rename",
        "share",
        "openInNewWindow",
        "close",
        "more",
        "search",
        "loadMore",
        "download",
        "thinking",
        "artifacts",
        "public",
        "custom",
        "notAvailableInDemoMode",
        "loading",
        "version",
        "lastUpdated",
        "code",
        "preview",
        "cancel",
        "save",
        "install",
        "create",
        "import",
        "export",
        "exportAsMarkdown",
        "exportAsJSON",
        "exportSuccess",
      ];
      for (const key of expectedKeys) {
        expect(enUS.common).toHaveProperty(key);
        expect(typeof (enUS.common as Record<string, unknown>)[key]).toBe(
          "string",
        );
      }
    });
  });

  describe("home section", () => {
    it("has docs and blog", () => {
      expect(enUS.home.docs).toBe("Docs");
      expect(enUS.home.blog).toBe("Blog");
    });
  });

  describe("welcome section", () => {
    it("has greeting", () => {
      expect(typeof enUS.welcome.greeting).toBe("string");
    });

    it("has createYourOwnSkill field", () => {
      expect(typeof enUS.welcome.createYourOwnSkill).toBe("string");
    });
  });

  describe("clipboard section", () => {
    it("has all clipboard keys", () => {
      expectNonEmptyString(
        enUS.clipboard.copyToClipboard,
        "clipboard.copyToClipboard",
      );
      expectNonEmptyString(
        enUS.clipboard.copiedToClipboard,
        "clipboard.copiedToClipboard",
      );
      expectNonEmptyString(
        enUS.clipboard.failedToCopyToClipboard,
        "clipboard.failedToCopyToClipboard",
      );
      expectNonEmptyString(enUS.clipboard.linkCopied, "clipboard.linkCopied");
    });
  });

  describe("inputBox section", () => {
    it("has basic input box keys", () => {
      expectNonEmptyString(enUS.inputBox.placeholder, "inputBox.placeholder");
      expectNonEmptyString(
        enUS.inputBox.createSkillPrompt,
        "inputBox.createSkillPrompt",
      );
      expectNonEmptyString(
        enUS.inputBox.addAttachments,
        "inputBox.addAttachments",
      );
    });

    it("has mode descriptions", () => {
      expectNonEmptyString(enUS.inputBox.flashMode, "inputBox.flashMode");
      expectNonEmptyString(
        enUS.inputBox.flashModeDescription,
        "inputBox.flashModeDescription",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningMode,
        "inputBox.reasoningMode",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningModeDescription,
        "inputBox.reasoningModeDescription",
      );
      expectNonEmptyString(enUS.inputBox.proMode, "inputBox.proMode");
      expectNonEmptyString(
        enUS.inputBox.proModeDescription,
        "inputBox.proModeDescription",
      );
      expectNonEmptyString(enUS.inputBox.ultraMode, "inputBox.ultraMode");
      expectNonEmptyString(
        enUS.inputBox.ultraModeDescription,
        "inputBox.ultraModeDescription",
      );
    });

    it("has reasoning effort levels", () => {
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortMinimal,
        "inputBox.reasoningEffortMinimal",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortMinimalDescription,
        "inputBox.reasoningEffortMinimalDescription",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortLow,
        "inputBox.reasoningEffortLow",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortLowDescription,
        "inputBox.reasoningEffortLowDescription",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortMedium,
        "inputBox.reasoningEffortMedium",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortMediumDescription,
        "inputBox.reasoningEffortMediumDescription",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortHigh,
        "inputBox.reasoningEffortHigh",
      );
      expectNonEmptyString(
        enUS.inputBox.reasoningEffortHighDescription,
        "inputBox.reasoningEffortHighDescription",
      );
    });

    it("has followup keys", () => {
      expectNonEmptyString(
        enUS.inputBox.followupLoading,
        "inputBox.followupLoading",
      );
      expectNonEmptyString(
        enUS.inputBox.followupConfirmTitle,
        "inputBox.followupConfirmTitle",
      );
      expectNonEmptyString(
        enUS.inputBox.followupConfirmDescription,
        "inputBox.followupConfirmDescription",
      );
      expectNonEmptyString(
        enUS.inputBox.followupConfirmAppend,
        "inputBox.followupConfirmAppend",
      );
      expectNonEmptyString(
        enUS.inputBox.followupConfirmReplace,
        "inputBox.followupConfirmReplace",
      );
    });
  });

  describe("sidebar section", () => {
    it("has all sidebar keys", () => {
      expectNonEmptyString(enUS.sidebar.newChat, "sidebar.newChat");
      expectNonEmptyString(enUS.sidebar.chats, "sidebar.chats");
      expectNonEmptyString(enUS.sidebar.recentChats, "sidebar.recentChats");
      expectNonEmptyString(enUS.sidebar.demoChats, "sidebar.demoChats");
      expectNonEmptyString(
        enUS.sidebar.scheduledTasks,
        "sidebar.scheduledTasks",
      );
      expectNonEmptyString(enUS.sidebar.workflows, "sidebar.workflows");
    });
  });

  describe("agents section", () => {
    it("has all agent management keys", () => {
      expectNonEmptyString(enUS.agents.title, "agents.title");
      expectNonEmptyString(enUS.agents.description, "agents.description");
      expectNonEmptyString(enUS.agents.newAgent, "agents.newAgent");
      expectNonEmptyString(enUS.agents.emptyTitle, "agents.emptyTitle");
      expectNonEmptyString(
        enUS.agents.emptyDescription,
        "agents.emptyDescription",
      );
      expectNonEmptyString(enUS.agents.chat, "agents.chat");
      expectNonEmptyString(enUS.agents.delete, "agents.delete");
      expectNonEmptyString(enUS.agents.deleteConfirm, "agents.deleteConfirm");
      expectNonEmptyString(enUS.agents.deleteSuccess, "agents.deleteSuccess");
      expectNonEmptyString(enUS.agents.template, "agents.template");
      expectNonEmptyString(enUS.agents.newChat, "agents.newChat");
    });

    it("has agent creation page keys", () => {
      expectNonEmptyString(
        enUS.agents.createPageTitle,
        "agents.createPageTitle",
      );
      expectNonEmptyString(
        enUS.agents.createPageSubtitle,
        "agents.createPageSubtitle",
      );
    });

    it("has name step keys", () => {
      expectNonEmptyString(enUS.agents.nameStepTitle, "agents.nameStepTitle");
      expectNonEmptyString(enUS.agents.nameStepHint, "agents.nameStepHint");
      expectNonEmptyString(
        enUS.agents.nameStepPlaceholder,
        "agents.nameStepPlaceholder",
      );
      expectNonEmptyString(
        enUS.agents.nameStepContinue,
        "agents.nameStepContinue",
      );
      expectNonEmptyString(
        enUS.agents.nameStepInvalidError,
        "agents.nameStepInvalidError",
      );
      expectNonEmptyString(
        enUS.agents.nameStepAlreadyExistsError,
        "agents.nameStepAlreadyExistsError",
      );
      expectNonEmptyString(
        enUS.agents.nameStepNetworkError,
        "agents.nameStepNetworkError",
      );
      expectNonEmptyString(
        enUS.agents.nameStepCheckError,
        "agents.nameStepCheckError",
      );
    });

    it("has nameStepBootstrapMessage with placeholder", () => {
      expect(enUS.agents.nameStepBootstrapMessage).toContain("{name}");
    });

    it("has save-related keys", () => {
      expectNonEmptyString(enUS.agents.save, "agents.save");
      expectNonEmptyString(enUS.agents.saving, "agents.saving");
      expectNonEmptyString(enUS.agents.saveRequested, "agents.saveRequested");
      expectNonEmptyString(enUS.agents.saveHint, "agents.saveHint");
      expectNonEmptyString(
        enUS.agents.saveCommandMessage,
        "agents.saveCommandMessage",
      );
      expectNonEmptyString(
        enUS.agents.agentCreatedPendingRefresh,
        "agents.agentCreatedPendingRefresh",
      );
      expectNonEmptyString(enUS.agents.more, "agents.more");
      expectNonEmptyString(enUS.agents.agentCreated, "agents.agentCreated");
      expectNonEmptyString(enUS.agents.startChatting, "agents.startChatting");
      expectNonEmptyString(enUS.agents.backToGallery, "agents.backToGallery");
    });
  });

  describe("workflows section", () => {
    it("has gallery keys", () => {
      expectNonEmptyString(enUS.workflows.title, "workflows.title");
      expectNonEmptyString(enUS.workflows.description, "workflows.description");
      expectNonEmptyString(enUS.workflows.newWorkflow, "workflows.newWorkflow");
      expectNonEmptyString(enUS.workflows.emptyTitle, "workflows.emptyTitle");
      expectNonEmptyString(
        enUS.workflows.emptyDescription,
        "workflows.emptyDescription",
      );
    });

    it("has card keys", () => {
      expectNonEmptyString(enUS.workflows.view, "workflows.view");
      expectNonEmptyString(enUS.workflows.deleteTitle, "workflows.deleteTitle");
      expectNonEmptyString(
        enUS.workflows.deleteSuccess,
        "workflows.deleteSuccess",
      );
      expectNonEmptyString(enUS.workflows.deleting, "workflows.deleting");
      expectNonEmptyString(enUS.workflows.unknown, "workflows.unknown");
    });

    it("has deleteConfirm as function", () => {
      expect(typeof enUS.workflows.deleteConfirm).toBe("function");
      const result = enUS.workflows.deleteConfirm("test-workflow");
      expect(result).toContain("test-workflow");
    });

    it("has steps function for plural/singular", () => {
      expect(typeof enUS.workflows.steps).toBe("function");
      expect(enUS.workflows.steps(1)).toBe("1 step");
      expect(enUS.workflows.steps(5)).toBe("5 steps");
    });

    it("has inputs function for plural/singular", () => {
      expect(typeof enUS.workflows.inputs).toBe("function");
      expect(enUS.workflows.inputs(1)).toBe("1 input");
      expect(enUS.workflows.inputs(3)).toBe("3 inputs");
    });

    it("has detail keys", () => {
      expectNonEmptyString(enUS.workflows.notFound, "workflows.notFound");
      expectNonEmptyString(
        enUS.workflows.backToWorkflows,
        "workflows.backToWorkflows",
      );
      expectNonEmptyString(enUS.workflows.edit, "workflows.edit");
      expectNonEmptyString(enUS.workflows.run, "workflows.run");
      expectNonEmptyString(
        enUS.workflows.stepsDescription,
        "workflows.stepsDescription",
      );
      expectNonEmptyString(enUS.workflows.noSteps, "workflows.noSteps");
      expectNonEmptyString(enUS.workflows.inputsTitle, "workflows.inputsTitle");
      expectNonEmptyString(
        enUS.workflows.inputsDescription,
        "workflows.inputsDescription",
      );
      expectNonEmptyString(enUS.workflows.required, "workflows.required");
      expectNonEmptyString(enUS.workflows.runStatus, "workflows.runStatus");
      expectNonEmptyString(enUS.workflows.runId, "workflows.runId");
      expectNonEmptyString(
        enUS.workflows.yamlDefinition,
        "workflows.yamlDefinition",
      );
    });

    it("has stepsTitle function", () => {
      expect(typeof enUS.workflows.stepsTitle).toBe("function");
      expect(enUS.workflows.stepsTitle(3)).toBe("Steps (3)");
    });

    it("has run dialog keys", () => {
      expectNonEmptyString(enUS.workflows.runDialog, "workflows.runDialog");
      expectNonEmptyString(
        enUS.workflows.runDialogDescription,
        "workflows.runDialogDescription",
      );
      expectNonEmptyString(
        enUS.workflows.defaultPrefix,
        "workflows.defaultPrefix",
      );
      expectNonEmptyString(enUS.workflows.noInputs, "workflows.noInputs");
      expectNonEmptyString(enUS.workflows.starting, "workflows.starting");
    });

    it("has enterInput function", () => {
      expect(typeof enUS.workflows.enterInput).toBe("function");
      expect(enUS.workflows.enterInput("prompt")).toBe("Enter prompt...");
    });

    it("has create/edit keys", () => {
      expectNonEmptyString(
        enUS.workflows.createSubtitle,
        "workflows.createSubtitle",
      );
      expectNonEmptyString(enUS.workflows.yamlEditor, "workflows.yamlEditor");
      expectNonEmptyString(enUS.workflows.creating, "workflows.creating");
      expectNonEmptyString(enUS.workflows.saving, "workflows.saving");
      expectNonEmptyString(enUS.workflows.created, "workflows.created");
      expectNonEmptyString(enUS.workflows.updated, "workflows.updated");
      expectNonEmptyString(enUS.workflows.started, "workflows.started");
      expectNonEmptyString(enUS.workflows.saveChanges, "workflows.saveChanges");
    });

    it("has requiredMissing function", () => {
      expect(typeof enUS.workflows.requiredMissing).toBe("function");
      const result = enUS.workflows.requiredMissing("input_name");
      expect(result).toContain("input_name");
    });
  });

  describe("breadcrumb section", () => {
    it("has all breadcrumb keys", () => {
      expectNonEmptyString(enUS.breadcrumb.workspace, "breadcrumb.workspace");
      expectNonEmptyString(enUS.breadcrumb.chats, "breadcrumb.chats");
      expectNonEmptyString(enUS.breadcrumb.workflows, "breadcrumb.workflows");
      expectNonEmptyString(enUS.breadcrumb.edit, "breadcrumb.edit");
      expectNonEmptyString(enUS.breadcrumb.runs, "breadcrumb.runs");
    });
  });

  describe("workspace section", () => {
    it("has all workspace keys", () => {
      expectNonEmptyString(
        enUS.workspace.officialWebsite,
        "workspace.officialWebsite",
      );
      expectNonEmptyString(
        enUS.workspace.githubTooltip,
        "workspace.githubTooltip",
      );
      expectNonEmptyString(
        enUS.workspace.settingsAndMore,
        "workspace.settingsAndMore",
      );
      expectNonEmptyString(enUS.workspace.visitGithub, "workspace.visitGithub");
      expectNonEmptyString(enUS.workspace.reportIssue, "workspace.reportIssue");
      expectNonEmptyString(enUS.workspace.contactUs, "workspace.contactUs");
      expectNonEmptyString(enUS.workspace.about, "workspace.about");
      expectNonEmptyString(enUS.workspace.logout, "workspace.logout");
      expectNonEmptyString(enUS.workspace.adminPanel, "workspace.adminPanel");
      expectNonEmptyString(
        enUS.workspace.userManagement,
        "workspace.userManagement",
      );
      expectNonEmptyString(
        enUS.workspace.departmentManagement,
        "workspace.departmentManagement",
      );
      expectNonEmptyString(
        enUS.workspace.toolManagement,
        "workspace.toolManagement",
      );
    });
  });

  describe("conversation section", () => {
    it("has conversation keys", () => {
      expectNonEmptyString(
        enUS.conversation.noMessages,
        "conversation.noMessages",
      );
      expectNonEmptyString(
        enUS.conversation.startConversation,
        "conversation.startConversation",
      );
    });
  });

  describe("chats section", () => {
    it("has searchChats", () => {
      expectNonEmptyString(enUS.chats.searchChats, "chats.searchChats");
    });
  });

  describe("pages section", () => {
    it("has page title keys", () => {
      expect(enUS.pages.appName).toBe("iDeer");
      expectNonEmptyString(enUS.pages.chats, "pages.chats");
      expectNonEmptyString(enUS.pages.newChat, "pages.newChat");
      expectNonEmptyString(enUS.pages.untitled, "pages.untitled");
    });
  });

  describe("toolCalls section", () => {
    it("has all tool call string keys", () => {
      expectNonEmptyString(enUS.toolCalls.lessSteps, "toolCalls.lessSteps");
      expectNonEmptyString(
        enUS.toolCalls.executeCommand,
        "toolCalls.executeCommand",
      );
      expectNonEmptyString(
        enUS.toolCalls.presentFiles,
        "toolCalls.presentFiles",
      );
      expectNonEmptyString(
        enUS.toolCalls.needYourHelp,
        "toolCalls.needYourHelp",
      );
      expectNonEmptyString(
        enUS.toolCalls.searchForRelatedInfo,
        "toolCalls.searchForRelatedInfo",
      );
      expectNonEmptyString(
        enUS.toolCalls.searchForRelatedImages,
        "toolCalls.searchForRelatedImages",
      );
      expectNonEmptyString(enUS.toolCalls.viewWebPage, "toolCalls.viewWebPage");
      expectNonEmptyString(enUS.toolCalls.listFolder, "toolCalls.listFolder");
      expectNonEmptyString(enUS.toolCalls.readFile, "toolCalls.readFile");
      expectNonEmptyString(enUS.toolCalls.writeFile, "toolCalls.writeFile");
      expectNonEmptyString(
        enUS.toolCalls.clickToViewContent,
        "toolCalls.clickToViewContent",
      );
      expectNonEmptyString(enUS.toolCalls.writeTodos, "toolCalls.writeTodos");
      expectNonEmptyString(
        enUS.toolCalls.skillInstallTooltip,
        "toolCalls.skillInstallTooltip",
      );
    });

    it("has moreSteps function", () => {
      expect(typeof enUS.toolCalls.moreSteps).toBe("function");
      expect(enUS.toolCalls.moreSteps(1)).toBe("1 more step");
      expect(enUS.toolCalls.moreSteps(5)).toBe("5 more steps");
    });

    it("has useTool function", () => {
      expect(typeof enUS.toolCalls.useTool).toBe("function");
      expect(enUS.toolCalls.useTool("web_search")).toContain("web_search");
    });

    it("has searchFor function", () => {
      expect(typeof enUS.toolCalls.searchFor).toBe("function");
      expect(enUS.toolCalls.searchFor("query")).toContain("query");
    });

    it("has searchForRelatedImagesFor function", () => {
      expect(typeof enUS.toolCalls.searchForRelatedImagesFor).toBe("function");
      expect(enUS.toolCalls.searchForRelatedImagesFor("cats")).toContain(
        "cats",
      );
    });

    it("has searchOnWebFor function", () => {
      expect(typeof enUS.toolCalls.searchOnWebFor).toBe("function");
      expect(enUS.toolCalls.searchOnWebFor("news")).toContain("news");
    });
  });

  describe("uploads section", () => {
    it("has upload keys", () => {
      expectNonEmptyString(enUS.uploads.uploading, "uploads.uploading");
      expectNonEmptyString(
        enUS.uploads.uploadingFiles,
        "uploads.uploadingFiles",
      );
    });
  });

  describe("subtasks section", () => {
    it("has subtask keys", () => {
      expectNonEmptyString(enUS.subtasks.subtask, "subtasks.subtask");
      expectNonEmptyString(enUS.subtasks.in_progress, "subtasks.in_progress");
      expectNonEmptyString(enUS.subtasks.completed, "subtasks.completed");
      expectNonEmptyString(enUS.subtasks.failed, "subtasks.failed");
    });

    it("has executing function for singular", () => {
      expect(typeof enUS.subtasks.executing).toBe("function");
      expect(enUS.subtasks.executing(1)).toBe("Executing subtask");
    });

    it("has executing function for plural", () => {
      const result = enUS.subtasks.executing(3);
      expect(result).toContain("3");
      expect(result).toContain("subtasks");
      expect(result).toContain("parallel");
    });
  });

  describe("tokenUsage section", () => {
    it("has basic token usage keys", () => {
      expectNonEmptyString(enUS.tokenUsage.title, "tokenUsage.title");
      expectNonEmptyString(enUS.tokenUsage.label, "tokenUsage.label");
      expectNonEmptyString(enUS.tokenUsage.input, "tokenUsage.input");
      expectNonEmptyString(enUS.tokenUsage.output, "tokenUsage.output");
      expectNonEmptyString(enUS.tokenUsage.total, "tokenUsage.total");
      expectNonEmptyString(enUS.tokenUsage.view, "tokenUsage.view");
      expectNonEmptyString(
        enUS.tokenUsage.unavailable,
        "tokenUsage.unavailable",
      );
      expectNonEmptyString(
        enUS.tokenUsage.unavailableShort,
        "tokenUsage.unavailableShort",
      );
      expectNonEmptyString(enUS.tokenUsage.note, "tokenUsage.note");
      expectNonEmptyString(
        enUS.tokenUsage.finalAnswer,
        "tokenUsage.finalAnswer",
      );
      expectNonEmptyString(enUS.tokenUsage.stepTotal, "tokenUsage.stepTotal");
      expectNonEmptyString(
        enUS.tokenUsage.sharedAttribution,
        "tokenUsage.sharedAttribution",
      );
    });

    it("has presets", () => {
      expectNonEmptyString(
        enUS.tokenUsage.presets.off,
        "tokenUsage.presets.off",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presets.summary,
        "tokenUsage.presets.summary",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presets.perTurn,
        "tokenUsage.presets.perTurn",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presets.debug,
        "tokenUsage.presets.debug",
      );
    });

    it("has presetDescriptions", () => {
      expectNonEmptyString(
        enUS.tokenUsage.presetDescriptions.off,
        "tokenUsage.presetDescriptions.off",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presetDescriptions.summary,
        "tokenUsage.presetDescriptions.summary",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presetDescriptions.perTurn,
        "tokenUsage.presetDescriptions.perTurn",
      );
      expectNonEmptyString(
        enUS.tokenUsage.presetDescriptions.debug,
        "tokenUsage.presetDescriptions.debug",
      );
    });

    it("has subagent function", () => {
      expect(typeof enUS.tokenUsage.subagent).toBe("function");
      expect(enUS.tokenUsage.subagent("planning")).toContain("planning");
    });

    it("has todo functions", () => {
      expect(typeof enUS.tokenUsage.startTodo).toBe("function");
      expect(typeof enUS.tokenUsage.completeTodo).toBe("function");
      expect(typeof enUS.tokenUsage.updateTodo).toBe("function");
      expect(typeof enUS.tokenUsage.removeTodo).toBe("function");

      expect(enUS.tokenUsage.startTodo("task A")).toContain("task A");
      expect(enUS.tokenUsage.completeTodo("task B")).toContain("task B");
      expect(enUS.tokenUsage.updateTodo("task C")).toContain("task C");
      expect(enUS.tokenUsage.removeTodo("task D")).toContain("task D");
    });
  });

  describe("shortcuts section", () => {
    it("has all shortcut keys", () => {
      expectNonEmptyString(
        enUS.shortcuts.searchActions,
        "shortcuts.searchActions",
      );
      expectNonEmptyString(enUS.shortcuts.noResults, "shortcuts.noResults");
      expectNonEmptyString(enUS.shortcuts.actions, "shortcuts.actions");
      expectNonEmptyString(
        enUS.shortcuts.keyboardShortcuts,
        "shortcuts.keyboardShortcuts",
      );
      expectNonEmptyString(
        enUS.shortcuts.keyboardShortcutsDescription,
        "shortcuts.keyboardShortcutsDescription",
      );
      expectNonEmptyString(
        enUS.shortcuts.openCommandPalette,
        "shortcuts.openCommandPalette",
      );
      expectNonEmptyString(
        enUS.shortcuts.toggleSidebar,
        "shortcuts.toggleSidebar",
      );
    });
  });

  describe("settings section", () => {
    it("has top-level settings keys", () => {
      expectNonEmptyString(enUS.settings.title, "settings.title");
      expectNonEmptyString(enUS.settings.description, "settings.description");
    });

    it("has section keys", () => {
      expectNonEmptyString(
        enUS.settings.sections.account,
        "settings.sections.account",
      );
      expectNonEmptyString(
        enUS.settings.sections.appearance,
        "settings.sections.appearance",
      );
      expectNonEmptyString(
        enUS.settings.sections.memory,
        "settings.sections.memory",
      );
      expectNonEmptyString(
        enUS.settings.sections.tools,
        "settings.sections.tools",
      );
      expectNonEmptyString(
        enUS.settings.sections.skills,
        "settings.sections.skills",
      );
      expectNonEmptyString(
        enUS.settings.sections.notification,
        "settings.sections.notification",
      );
      expectNonEmptyString(
        enUS.settings.sections.about,
        "settings.sections.about",
      );
    });

    it("has memory settings", () => {
      expectNonEmptyString(enUS.settings.memory.title, "settings.memory.title");
      expectNonEmptyString(
        enUS.settings.memory.description,
        "settings.memory.description",
      );
      expectNonEmptyString(enUS.settings.memory.empty, "settings.memory.empty");
      expectNonEmptyString(
        enUS.settings.memory.rawJson,
        "settings.memory.rawJson",
      );
      expectNonEmptyString(
        enUS.settings.memory.exportButton,
        "settings.memory.exportButton",
      );
      expectNonEmptyString(
        enUS.settings.memory.exportSuccess,
        "settings.memory.exportSuccess",
      );
      expectNonEmptyString(
        enUS.settings.memory.importButton,
        "settings.memory.importButton",
      );
      expectNonEmptyString(
        enUS.settings.memory.importConfirmTitle,
        "settings.memory.importConfirmTitle",
      );
      expectNonEmptyString(
        enUS.settings.memory.importConfirmDescription,
        "settings.memory.importConfirmDescription",
      );
      expectNonEmptyString(
        enUS.settings.memory.importFileLabel,
        "settings.memory.importFileLabel",
      );
      expectNonEmptyString(
        enUS.settings.memory.importInvalidFile,
        "settings.memory.importInvalidFile",
      );
      expectNonEmptyString(
        enUS.settings.memory.importSuccess,
        "settings.memory.importSuccess",
      );
    });

    it("has memory fact management keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.manualFactSource,
        "settings.memory.manualFactSource",
      );
      expectNonEmptyString(
        enUS.settings.memory.addFact,
        "settings.memory.addFact",
      );
      expectNonEmptyString(
        enUS.settings.memory.addFactTitle,
        "settings.memory.addFactTitle",
      );
      expectNonEmptyString(
        enUS.settings.memory.editFactTitle,
        "settings.memory.editFactTitle",
      );
      expectNonEmptyString(
        enUS.settings.memory.addFactSuccess,
        "settings.memory.addFactSuccess",
      );
      expectNonEmptyString(
        enUS.settings.memory.editFactSuccess,
        "settings.memory.editFactSuccess",
      );
      expectNonEmptyString(
        enUS.settings.memory.factSave,
        "settings.memory.factSave",
      );
      expectNonEmptyString(
        enUS.settings.memory.factValidationContent,
        "settings.memory.factValidationContent",
      );
      expectNonEmptyString(
        enUS.settings.memory.factValidationConfidence,
        "settings.memory.factValidationConfidence",
      );
      expectNonEmptyString(
        enUS.settings.memory.noFacts,
        "settings.memory.noFacts",
      );
    });

    it("has memory clear and delete keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.clearAll,
        "settings.memory.clearAll",
      );
      expectNonEmptyString(
        enUS.settings.memory.clearAllConfirmTitle,
        "settings.memory.clearAllConfirmTitle",
      );
      expectNonEmptyString(
        enUS.settings.memory.clearAllConfirmDescription,
        "settings.memory.clearAllConfirmDescription",
      );
      expectNonEmptyString(
        enUS.settings.memory.clearAllSuccess,
        "settings.memory.clearAllSuccess",
      );
      expectNonEmptyString(
        enUS.settings.memory.factDeleteConfirmTitle,
        "settings.memory.factDeleteConfirmTitle",
      );
      expectNonEmptyString(
        enUS.settings.memory.factDeleteConfirmDescription,
        "settings.memory.factDeleteConfirmDescription",
      );
      expectNonEmptyString(
        enUS.settings.memory.factDeleteSuccess,
        "settings.memory.factDeleteSuccess",
      );
    });

    it("has memory fact form label keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.factContentLabel,
        "settings.memory.factContentLabel",
      );
      expectNonEmptyString(
        enUS.settings.memory.factCategoryLabel,
        "settings.memory.factCategoryLabel",
      );
      expectNonEmptyString(
        enUS.settings.memory.factConfidenceLabel,
        "settings.memory.factConfidenceLabel",
      );
      expectNonEmptyString(
        enUS.settings.memory.factContentPlaceholder,
        "settings.memory.factContentPlaceholder",
      );
      expectNonEmptyString(
        enUS.settings.memory.factCategoryPlaceholder,
        "settings.memory.factCategoryPlaceholder",
      );
      expectNonEmptyString(
        enUS.settings.memory.factConfidenceHint,
        "settings.memory.factConfidenceHint",
      );
    });

    it("has memory filter and search keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.summaryReadOnly,
        "settings.memory.summaryReadOnly",
      );
      expectNonEmptyString(
        enUS.settings.memory.memoryFullyEmpty,
        "settings.memory.memoryFullyEmpty",
      );
      expectNonEmptyString(
        enUS.settings.memory.factPreviewLabel,
        "settings.memory.factPreviewLabel",
      );
      expectNonEmptyString(
        enUS.settings.memory.searchPlaceholder,
        "settings.memory.searchPlaceholder",
      );
      expectNonEmptyString(
        enUS.settings.memory.filterAll,
        "settings.memory.filterAll",
      );
      expectNonEmptyString(
        enUS.settings.memory.filterFacts,
        "settings.memory.filterFacts",
      );
      expectNonEmptyString(
        enUS.settings.memory.filterSummaries,
        "settings.memory.filterSummaries",
      );
      expectNonEmptyString(
        enUS.settings.memory.noMatches,
        "settings.memory.noMatches",
      );
    });

    it("has memory markdown keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.markdown.overview,
        "settings.memory.markdown.overview",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.userContext,
        "settings.memory.markdown.userContext",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.work,
        "settings.memory.markdown.work",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.personal,
        "settings.memory.markdown.personal",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.topOfMind,
        "settings.memory.markdown.topOfMind",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.historyBackground,
        "settings.memory.markdown.historyBackground",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.recentMonths,
        "settings.memory.markdown.recentMonths",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.earlierContext,
        "settings.memory.markdown.earlierContext",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.longTermBackground,
        "settings.memory.markdown.longTermBackground",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.updatedAt,
        "settings.memory.markdown.updatedAt",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.facts,
        "settings.memory.markdown.facts",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.empty,
        "settings.memory.markdown.empty",
      );
    });

    it("has memory markdown table keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.category,
        "settings.memory.markdown.table.category",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.confidence,
        "settings.memory.markdown.table.confidence",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.content,
        "settings.memory.markdown.table.content",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.source,
        "settings.memory.markdown.table.source",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.createdAt,
        "settings.memory.markdown.table.createdAt",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.view,
        "settings.memory.markdown.table.view",
      );
    });

    it("has memory markdown table confidenceLevel keys", () => {
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.confidenceLevel.veryHigh,
        "settings.memory.markdown.table.confidenceLevel.veryHigh",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.confidenceLevel.high,
        "settings.memory.markdown.table.confidenceLevel.high",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.confidenceLevel.normal,
        "settings.memory.markdown.table.confidenceLevel.normal",
      );
      expectNonEmptyString(
        enUS.settings.memory.markdown.table.confidenceLevel.unknown,
        "settings.memory.markdown.table.confidenceLevel.unknown",
      );
    });

    it("has appearance settings", () => {
      expectNonEmptyString(
        enUS.settings.appearance.themeTitle,
        "settings.appearance.themeTitle",
      );
      expectNonEmptyString(
        enUS.settings.appearance.themeDescription,
        "settings.appearance.themeDescription",
      );
      expectNonEmptyString(
        enUS.settings.appearance.system,
        "settings.appearance.system",
      );
      expectNonEmptyString(
        enUS.settings.appearance.light,
        "settings.appearance.light",
      );
      expectNonEmptyString(
        enUS.settings.appearance.dark,
        "settings.appearance.dark",
      );
      expectNonEmptyString(
        enUS.settings.appearance.systemDescription,
        "settings.appearance.systemDescription",
      );
      expectNonEmptyString(
        enUS.settings.appearance.lightDescription,
        "settings.appearance.lightDescription",
      );
      expectNonEmptyString(
        enUS.settings.appearance.darkDescription,
        "settings.appearance.darkDescription",
      );
      expectNonEmptyString(
        enUS.settings.appearance.languageTitle,
        "settings.appearance.languageTitle",
      );
      expectNonEmptyString(
        enUS.settings.appearance.languageDescription,
        "settings.appearance.languageDescription",
      );
    });

    it("has tools settings", () => {
      expectNonEmptyString(enUS.settings.tools.title, "settings.tools.title");
      expectNonEmptyString(
        enUS.settings.tools.description,
        "settings.tools.description",
      );
    });

    it("has skills settings", () => {
      expectNonEmptyString(enUS.settings.skills.title, "settings.skills.title");
      expectNonEmptyString(
        enUS.settings.skills.description,
        "settings.skills.description",
      );
      expectNonEmptyString(
        enUS.settings.skills.createSkill,
        "settings.skills.createSkill",
      );
      expectNonEmptyString(
        enUS.settings.skills.emptyTitle,
        "settings.skills.emptyTitle",
      );
      expectNonEmptyString(
        enUS.settings.skills.emptyDescription,
        "settings.skills.emptyDescription",
      );
      expectNonEmptyString(
        enUS.settings.skills.emptyButton,
        "settings.skills.emptyButton",
      );
    });

    it("has notification settings", () => {
      expectNonEmptyString(
        enUS.settings.notification.title,
        "settings.notification.title",
      );
      expectNonEmptyString(
        enUS.settings.notification.description,
        "settings.notification.description",
      );
      expectNonEmptyString(
        enUS.settings.notification.requestPermission,
        "settings.notification.requestPermission",
      );
      expectNonEmptyString(
        enUS.settings.notification.deniedHint,
        "settings.notification.deniedHint",
      );
      expectNonEmptyString(
        enUS.settings.notification.testButton,
        "settings.notification.testButton",
      );
      expectNonEmptyString(
        enUS.settings.notification.testTitle,
        "settings.notification.testTitle",
      );
      expectNonEmptyString(
        enUS.settings.notification.testBody,
        "settings.notification.testBody",
      );
      expectNonEmptyString(
        enUS.settings.notification.notSupported,
        "settings.notification.notSupported",
      );
      expectNonEmptyString(
        enUS.settings.notification.disableNotification,
        "settings.notification.disableNotification",
      );
    });

    it("has account settings", () => {
      expectNonEmptyString(
        enUS.settings.account.profileTitle,
        "settings.account.profileTitle",
      );
      expectNonEmptyString(
        enUS.settings.account.email,
        "settings.account.email",
      );
      expectNonEmptyString(enUS.settings.account.role, "settings.account.role");
      expectNonEmptyString(
        enUS.settings.account.changePasswordTitle,
        "settings.account.changePasswordTitle",
      );
      expectNonEmptyString(
        enUS.settings.account.changePasswordDescription,
        "settings.account.changePasswordDescription",
      );
      expectNonEmptyString(
        enUS.settings.account.currentPassword,
        "settings.account.currentPassword",
      );
      expectNonEmptyString(
        enUS.settings.account.newPassword,
        "settings.account.newPassword",
      );
      expectNonEmptyString(
        enUS.settings.account.confirmNewPassword,
        "settings.account.confirmNewPassword",
      );
      expectNonEmptyString(
        enUS.settings.account.passwordMismatch,
        "settings.account.passwordMismatch",
      );
      expectNonEmptyString(
        enUS.settings.account.passwordTooShort,
        "settings.account.passwordTooShort",
      );
      expectNonEmptyString(
        enUS.settings.account.passwordChangedSuccess,
        "settings.account.passwordChangedSuccess",
      );
      expectNonEmptyString(
        enUS.settings.account.networkError,
        "settings.account.networkError",
      );
      expectNonEmptyString(
        enUS.settings.account.updating,
        "settings.account.updating",
      );
      expectNonEmptyString(
        enUS.settings.account.updatePassword,
        "settings.account.updatePassword",
      );
      expectNonEmptyString(
        enUS.settings.account.signOut,
        "settings.account.signOut",
      );
    });

    it("has acknowledge settings", () => {
      expectNonEmptyString(
        enUS.settings.acknowledge.emptyTitle,
        "settings.acknowledge.emptyTitle",
      );
      expectNonEmptyString(
        enUS.settings.acknowledge.emptyDescription,
        "settings.acknowledge.emptyDescription",
      );
    });
  });

  describe("all sections are non-empty", () => {
    it("every top-level section has at least one key", () => {
      const sections = [
        "locale",
        "common",
        "home",
        "welcome",
        "clipboard",
        "inputBox",
        "sidebar",
        "agents",
        "workflows",
        "breadcrumb",
        "workspace",
        "conversation",
        "chats",
        "pages",
        "toolCalls",
        "uploads",
        "subtasks",
        "tokenUsage",
        "shortcuts",
        "settings",
      ];
      for (const section of sections) {
        expect(
          Object.keys(
            (enUS as unknown as Record<string, unknown>)[section] as object,
          ).length,
        ).toBeGreaterThan(0);
      }
    });
  });
});
