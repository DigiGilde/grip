/**
 * The API leaves out what a reader may not see: a list of things the reader
 * has no right to is absent, not empty, so nothing can be counted. A screen
 * that loops over such a list reads it through this, and treats "not for
 * you" the same as "none".
 */
export function withLists<T extends object, K extends keyof T>(value: T, ...keys: K[]): T {
  const result = { ...value };
  for (const key of keys) {
    if (result[key] === undefined || result[key] === null) {
      (result as Record<K, unknown>)[key] = [];
    }
  }
  return result;
}
