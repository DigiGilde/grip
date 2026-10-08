/** The budget years on offer: three back and two ahead of the current one. */
export function reportYearOptions(now: Date = new Date()) {
  const year = now.getFullYear();
  return [-3, -2, -1, 0, 1, 2].map((offset) => ({
    value: String(year + offset),
    label: String(year + offset),
  }));
}

export function currentReportYear(now: Date = new Date()): string {
  return String(now.getFullYear());
}
