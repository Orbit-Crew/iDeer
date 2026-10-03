import { describe, expect, it } from "vitest";

import { enUS } from "@/core/i18n/locales/en-US";
import { zhCN } from "@/core/i18n/locales/zh-CN";

describe("i18n translation keys", () => {
  describe("admin-related keys", () => {
    it("en-US has admin-related workspace keys", () => {
      expect(enUS.workspace).toHaveProperty("adminPanel");
      expect(enUS.workspace).toHaveProperty("userManagement");
      expect(enUS.workspace).toHaveProperty("departmentManagement");
      expect(enUS.workspace).toHaveProperty("toolManagement");
    });

    it("zh-CN has admin-related workspace keys", () => {
      expect(zhCN.workspace).toHaveProperty("adminPanel");
      expect(zhCN.workspace).toHaveProperty("userManagement");
      expect(zhCN.workspace).toHaveProperty("departmentManagement");
      expect(zhCN.workspace).toHaveProperty("toolManagement");
    });
  });

  describe("workflow-related keys", () => {
    it("en-US has workflows sidebar key", () => {
      expect(enUS.sidebar).toHaveProperty("workflows");
    });

    it("zh-CN has workflows sidebar key", () => {
      expect(zhCN.sidebar).toHaveProperty("workflows");
    });

    it("en-US has workflows section", () => {
      expect(enUS).toHaveProperty("workflows");
      expect(enUS.workflows).toHaveProperty("title");
      expect(enUS.workflows).toHaveProperty("newWorkflow");
      expect(enUS.workflows).toHaveProperty("emptyTitle");
      expect(enUS.workflows).toHaveProperty("runDialog");
      expect(enUS.workflows).toHaveProperty("yamlEditor");
    });

    it("zh-CN has workflows section", () => {
      expect(zhCN).toHaveProperty("workflows");
      expect(zhCN.workflows).toHaveProperty("title");
      expect(zhCN.workflows).toHaveProperty("newWorkflow");
      expect(zhCN.workflows).toHaveProperty("emptyTitle");
      expect(zhCN.workflows).toHaveProperty("runDialog");
      expect(zhCN.workflows).toHaveProperty("yamlEditor");
    });

    it("en-US has workflow breadcrumb keys", () => {
      expect(enUS.breadcrumb).toHaveProperty("workflows");
      expect(enUS.breadcrumb).toHaveProperty("edit");
      expect(enUS.breadcrumb).toHaveProperty("runs");
    });

    it("zh-CN has workflow breadcrumb keys", () => {
      expect(zhCN.breadcrumb).toHaveProperty("workflows");
      expect(zhCN.breadcrumb).toHaveProperty("edit");
      expect(zhCN.breadcrumb).toHaveProperty("runs");
    });
  });

  describe("workbench keys", () => {
    it("en-US has task workbench strings", () => {
      expect(enUS.workbench.recentTasks).toBe("Recent tasks");
      expect(enUS.workbench.reviewQuestion).toBe("Reviewing past work?");
      expect(enUS.workbench.reviewAnswer).toBe("iDeer takes you back");
      expect(enUS.workbench.defaultTaskType).toBe("Conversation task");
      expect(enUS.workbench.defaultStatus).toBe("In progress");
      expect(enUS.workbench.exploreQuestion).toBe("Unclear direction?");
      expect(enUS.workbench.exploreAnswer).toBe("iDeer finds the right helper");
      expect(enUS.workbench.focusQuestion).toBe("Clear goal?");
      expect(enUS.workbench.focusAnswer).toBe("iDeer helps you land it");
    });

    it("zh-CN keeps the former hardcoded chat-page strings", () => {
      expect(zhCN.workbench.recentTasks).toBe("最近任务");
      expect(zhCN.workbench.reviewQuestion).toBe("工作复盘？");
      expect(zhCN.workbench.reviewAnswer).toBe("iDeer带你回到过去");
      expect(zhCN.workbench.defaultTaskType).toBe("对话任务");
      expect(zhCN.workbench.defaultStatus).toBe("进行中");
      expect(zhCN.workbench.exploreQuestion).toBe("方向不明？");
      expect(zhCN.workbench.exploreAnswer).toBe("iDeer帮你找对帮手");
      expect(zhCN.workbench.focusQuestion).toBe("目标明确？");
      expect(zhCN.workbench.focusAnswer).toBe("iDeer帮你落地实现");
    });

    it("agent chat welcome describes the agent's skills", () => {
      expect(enUS.agents.skilledAt(["web-search"])).toBe(
        "Skilled in: web-search",
      );
      expect(zhCN.agents.skilledAt(["网页搜索"])).toBe("擅长：网页搜索");
    });
  });

  describe("brand keys", () => {
    it("en-US uses iDeer brand in app name", () => {
      expect(enUS.pages.appName).toBe("iDeer");
    });

    it("zh-CN uses iDeer brand in app name", () => {
      expect(zhCN.pages.appName).toBe("iDeer");
    });
  });

  // Key parity between en-US and zh-CN is enforced at compile time:
  // `Translations` is derived from the en-US literal (locales/types.ts) and
  // zh-CN is annotated with it, so a missing key fails `tsc --noEmit`. The
  // former runtime parity checks are recorded in
  // docs/testing/test-migration-ledger.md (batch 2026-10-03, issue 09).
});
