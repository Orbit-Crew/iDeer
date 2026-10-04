import { describe, expect, it } from "vitest";

import {
  applyTaskInputInsertion,
  getResolvedInputMode,
  hasTaskInput,
  prepareTaskInputInsertion,
} from "@/core/threads/task-input";

describe("task input", () => {
  it("accepts files when text is empty", () => {
    expect(hasTaskInput({ text: "  ", files: [{}] })).toBe(true);
    expect(hasTaskInput({ text: "  ", files: [] })).toBe(false);
  });

  it("resolves unsupported modes to flash", () => {
    expect(getResolvedInputMode("pro", false)).toBe("flash");
    expect(getResolvedInputMode(undefined, true)).toBe("pro");
  });

  it("requires a choice before a template replaces existing text", () => {
    expect(prepareTaskInputInsertion("my task", "template")).toEqual({
      kind: "conflict",
      current: "my task",
      incoming: "template",
    });
    expect(applyTaskInputInsertion("my task", "template", "replace")).toBe(
      "template",
    );
    expect(applyTaskInputInsertion("my task", "template", "append")).toBe(
      "my task\ntemplate",
    );
  });

  it("inserts a template directly when the input is empty", () => {
    expect(prepareTaskInputInsertion("  ", "template")).toEqual({
      kind: "insert",
      text: "template",
    });
  });
});
