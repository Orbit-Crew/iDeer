import { describe, expect, test } from "vitest";

import { getSlashAtCursor } from "@/components/workspace/slash-suggestions";

describe("getSlashAtCursor", () => {
  test("triggers at start of empty string", () => {
    expect(getSlashAtCursor("/", 1)).toEqual({ query: "", start: 0, end: 1 });
  });

  test("triggers at start of text", () => {
    expect(getSlashAtCursor("/res", 4)).toEqual({
      query: "res",
      start: 0,
      end: 4,
    });
  });

  test("triggers after a space", () => {
    expect(getSlashAtCursor("hello /res", 10)).toEqual({
      query: "res",
      start: 6,
      end: 10,
    });
  });

  test("triggers after a newline", () => {
    expect(getSlashAtCursor("line1\n/res", 10)).toEqual({
      query: "res",
      start: 6,
      end: 10,
    });
  });

  test("triggers after a tab", () => {
    expect(getSlashAtCursor("hello\t/res", 10)).toEqual({
      query: "res",
      start: 6,
      end: 10,
    });
  });

  test("does not trigger on double slash", () => {
    expect(getSlashAtCursor("//res", 5)).toBeNull();
  });

  test("does not trigger when slash is mid-word", () => {
    expect(getSlashAtCursor("abc/res", 7)).toBeNull();
  });

  test("does not trigger when query contains space", () => {
    expect(getSlashAtCursor("/res abc", 4)).toEqual({
      query: "res",
      start: 0,
      end: 4,
    });
  });

  test("does not trigger when slash is mid-word even with later valid slash", () => {
    expect(getSlashAtCursor("re/s", 5)).toBeNull();
  });

  test("uses cursor position, not end of string", () => {
    expect(getSlashAtCursor("hello /res world", 10)).toEqual({
      query: "res",
      start: 6,
      end: 10,
    });
  });

  test("returns null when cursor is before the slash", () => {
    expect(getSlashAtCursor("/res", 0)).toBeNull();
  });

  test("returns null for uppercase query (strict lowercase)", () => {
    expect(getSlashAtCursor("/RES", 4)).toBeNull();
  });

  test("returns null when cursor exceeds string length", () => {
    expect(getSlashAtCursor("/res", 10)).toBeNull();
  });

  test("allows hyphen in query", () => {
    expect(getSlashAtCursor("/anthropic-docx", 15)).toEqual({
      query: "anthropic-docx",
      start: 0,
      end: 15,
    });
  });

  test("rejects non-alphanumeric-hyphen chars in query", () => {
    expect(getSlashAtCursor("/res!", 5)).toBeNull();
  });

  test("returns empty query for bare slash", () => {
    expect(getSlashAtCursor("/", 1)).toEqual({ query: "", start: 0, end: 1 });
  });
});
