export type EditorLineRange = {
  start: number;
  end: number;
  lineCount: number;
};

export type EditorPosition = {
  line: number;
  column: number;
  lineCount: number;
};

function lineCountOf(content: string): number {
  let count = 1;
  let offset = -1;
  while (true) {
    offset = content.indexOf("\n", offset + 1);
    if (offset < 0) return count;
    count += 1;
  }
}

/**
 * Finds non-overlapping literal matches while preserving UTF-16 offsets for
 * textarea selection. RegExp supplies offsets from the original string, so a
 * Unicode case fold cannot shift an offset as toLocaleLowerCase() can.
 */
export function findLiteralMatches(content: string, query: string, matchCase: boolean): number[] {
  if (!query) return [];
  const escaped = query.replace(/[\\^$.*+?()[\]{}|/]/gu, "\\$&");
  try {
    const expression = new RegExp(escaped, matchCase ? "gu" : "giu");
    const matches: number[] = [];
    let match: RegExpExecArray | null;
    while ((match = expression.exec(content)) !== null) {
      matches.push(match.index);
    }
    return matches;
  } catch {
    // A malformed surrogate in an untrusted query must not break editing.
    return [];
  }
}

/** Returns the complete requested line excluding its trailing newline. */
export function lineRangeAt(content: string, requestedLine: number): EditorLineRange | null {
  if (!Number.isSafeInteger(requestedLine) || requestedLine < 1) return null;
  let start = 0;
  for (let line = 1; line < requestedLine; line += 1) {
    const newline = content.indexOf("\n", start);
    if (newline < 0) return null;
    start = newline + 1;
  }
  const newline = content.indexOf("\n", start);
  return {
    start,
    end: newline < 0 ? content.length : newline,
    lineCount: lineCountOf(content),
  };
}

/** The beginning offset of a one-based line, retained for simple callers. */
export function lineStartOffset(content: string, requestedLine: number): number | null {
  return lineRangeAt(content, requestedLine)?.start ?? null;
}

/** Returns a one-based UTF-16 column, matching native textarea offsets. */
export function lineColumnAt(content: string, offset: number): EditorPosition {
  const bounded = Math.min(Math.max(0, Number.isFinite(offset) ? Math.trunc(offset) : 0), content.length);
  let line = 1;
  let start = 0;
  let cursor = content.indexOf("\n");
  while (cursor >= 0 && cursor < bounded) {
    line += 1;
    start = cursor + 1;
    cursor = content.indexOf("\n", start);
  }
  return {
    line,
    column: content.slice(start, bounded).length + 1,
    lineCount: lineCountOf(content),
  };
}
