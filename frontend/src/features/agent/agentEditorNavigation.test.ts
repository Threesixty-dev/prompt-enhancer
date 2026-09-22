import { describe, expect, it } from "vitest";
import {
  findLiteralMatches,
  lineColumnAt,
  lineRangeAt,
  lineStartOffset,
} from "./agentEditorNavigation";

describe("agentEditorNavigation", () => {
  it("finds literal text without regex interpretation, overlap, or Unicode offset drift", () => {
    expect(findLiteralMatches("[a-z]+ [a-z]+", "[a-z]+", true)).toEqual([0, 7]);
    expect(findLiteralMatches("foofoofoo", "foo", true)).toEqual([0, 3, 6]);
    expect(findLiteralMatches("aaaa", "aa", true)).toEqual([0, 2]);
    expect(findLiteralMatches("İ😀İ", "İ", true)).toEqual([0, 3]);
    expect(findLiteralMatches("İx X", "x", false)).toEqual([1, 3]);
    expect(findLiteralMatches("Alpha alpha", "alpha", false)).toEqual([0, 6]);
    expect(findLiteralMatches("Alpha alpha", "alpha", true)).toEqual([6]);
  });

  it("treats an empty query as no match and preserves the trailing empty line", () => {
    expect(findLiteralMatches("literal", "", false)).toEqual([]);
    expect(lineRangeAt("", 1)).toEqual({ start: 0, end: 0, lineCount: 1 });
    expect(lineRangeAt("first\n", 2)).toEqual({ start: 6, end: 6, lineCount: 2 });
    expect(lineStartOffset("first\n", 2)).toBe(6);
  });

  it("locates whole lines and cursor columns without splitting emoji UTF-16 offsets", () => {
    const content = "alpha\n😀beta\nlast";
    expect(lineRangeAt(content, 2)).toEqual({ start: 6, end: 12, lineCount: 3 });
    for (const invalidLine of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1.5, Number.MAX_SAFE_INTEGER]) {
      expect(lineStartOffset(content, invalidLine)).toBeNull();
      expect(lineRangeAt(content, invalidLine)).toBeNull();
    }
    expect(lineColumnAt(content, 6)).toEqual({ line: 2, column: 1, lineCount: 3 });
    expect(lineColumnAt(content, 8)).toEqual({ line: 2, column: 3, lineCount: 3 });
    expect(lineColumnAt(content, content.length)).toEqual({ line: 3, column: 5, lineCount: 3 });
  });
});
