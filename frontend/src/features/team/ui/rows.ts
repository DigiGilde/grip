/** True when at least one row carries the field: a column nobody may see is not drawn. */
export function anyHas<T extends object>(rows: T[], field: string): boolean {
  return rows.some((row) => field in row);
}
