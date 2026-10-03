export function getSlashAtCursor(
  value: string,
  selectionStart: number,
): { query: string; start: number; end: number } | null {
  if (selectionStart <= 0 || selectionStart > value.length) return null;

  const before = value.slice(0, selectionStart);
  const lastSlash = before.lastIndexOf("/");
  if (lastSlash < 0) return null;
  if (lastSlash > 0 && !/\s/.test(before[lastSlash - 1]!)) return null;

  const queryRaw = before.slice(lastSlash + 1);
  if (queryRaw.length > 0 && !/^[a-z0-9-]+$/.test(queryRaw)) return null;

  return {
    query: queryRaw.toLowerCase(),
    start: lastSlash,
    end: selectionStart,
  };
}
