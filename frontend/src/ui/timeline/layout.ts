/**
 * The timeline as data: rows over months, with bars and a text value per
 * cell. Feature-neutral: a caller turns its own records into these rows and
 * keeps its record in `data`, so the same component draws people over
 * months, assignments with their roles, and the roles of one assignment.
 */

export type BarVariant =
  /** Firm inzet. */
  | 'filled'
  /** Inzet that may not happen: striped outline. */
  | 'tentative'
  /** Demand nobody fills: dashed outline. */
  | 'open'
  /** The frame of what a row asks, drawn behind its bars. */
  | 'demand';

export interface TimelineBar<B = unknown> {
  key: string;
  /** Index of the first month column the bar covers. */
  column: number;
  span: number;
  lane: number;
  label: string;
  /** The bar in words: tooltip, and the text of every cell it covers. */
  description: string;
  variant: BarVariant;
  /** Leading months of the bar that are closed, counted in columns. */
  closedSpan: number;
  /** The bar starts before, or ends after, the months on screen. */
  clippedStart: boolean;
  clippedEnd: boolean;
  /**
   * A signal on the bar, as a concept: `attention` (above what is possible)
   * shows the attention icon, `mismatch` (another rate category than the
   * line assumes) a short word. Never a character.
   */
  mark?: 'attention' | 'mismatch';
  /**
   * Where in its first and last month the bar begins and ends, as the part
   * of that month to leave free (0 to 1). Only drawn on a timeline that
   * shows days; without them the bar covers whole months.
   */
  startOffset?: number;
  endOffset?: number;
  data: B;
}

export type CellState = 'none' | 'unavailable' | 'empty' | 'quiet' | 'room' | 'over';

export interface TimelineCell {
  /** The quiet figure of the month; empty for none. */
  text: string;
  state: CellState;
  /** The month is closed: what it shows was established. */
  established: boolean;
  /** The figure in words, without the bars. */
  description: string;
}

export interface TimelineRow<R = unknown, B = unknown> {
  key: string;
  label: string;
  /** A small figure after the label, e.g. "0,8 FTE". */
  figure?: string;
  /** One quiet line under the label. */
  summary: string;
  /** Said louder than the summary, when something needs attention. */
  attention: string;
  cells: TimelineCell[];
  bars: TimelineBar<B>[];
  lanes: number;
  link?: { href: string; text: string } | null;
  data: R;
}

export interface TimelineGroup<R = unknown, B = unknown> {
  key: string;
  /** Empty for the one group of a flat view. */
  title: string;
  rows: TimelineRow<R, B>[];
}

export const EMPTY_CELL: TimelineCell = {
  text: '',
  state: 'none',
  established: false,
  description: '',
};

const MONTHS_SHORT = [
  'jan',
  'feb',
  'mrt',
  'apr',
  'mei',
  'jun',
  'jul',
  'aug',
  'sep',
  'okt',
  'nov',
  'dec',
];

/** "okt", from a YYYY-MM or a date. */
export function monthShort(iso: string): string {
  return MONTHS_SHORT[Number(iso.slice(5, 7)) - 1] ?? '';
}

export const monthKey = (iso: string) => iso.slice(0, 7);

/** The month `count` months after `month` (YYYY-MM), also backwards. */
export function shiftMonth(month: string, count: number): string {
  const index = Number(month.slice(0, 4)) * 12 + (Number(month.slice(5, 7)) - 1) + count;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`;
}

export interface Placement {
  column: number;
  span: number;
  clippedStart: boolean;
  clippedEnd: boolean;
}

/** Where a period falls in the months on screen; null when outside them. */
export function placePeriod(
  months: readonly string[],
  start: string | null,
  end: string | null,
): Placement | null {
  if (months.length === 0) return null;
  const first = monthKey(months[0] ?? '');
  const last = monthKey(months[months.length - 1] ?? '');
  const from = start ? monthKey(start) : first;
  const to = end ? monthKey(end) : last;
  if (to < first || from > last) return null;
  const startColumn = from < first ? 0 : months.findIndex((month) => monthKey(month) === from);
  const endColumn =
    to > last ? months.length - 1 : months.findIndex((month) => monthKey(month) === to);
  if (startColumn < 0 || endColumn < startColumn) return null;
  return {
    column: startColumn,
    span: endColumn - startColumn + 1,
    clippedStart: from < first,
    clippedEnd: to > last,
  };
}

/** Gives every bar the first lane in which it does not overlap an earlier one. */
export function assignLanes<T extends { column: number; span: number; lane: number }>(
  bars: T[],
): number {
  const ends: number[] = [];
  for (const bar of [...bars].sort((a, b) => a.column - b.column || b.span - a.span)) {
    let lane = ends.findIndex((end) => end < bar.column);
    if (lane === -1) lane = ends.length;
    ends[lane] = bar.column + bar.span - 1;
    bar.lane = lane;
  }
  return Math.max(1, ends.length);
}

/** The bars of a row that cover a month column; the demand frame is not one of them. */
export function barsInColumn<B>(row: { bars: TimelineBar<B>[] }, column: number): TimelineBar<B>[] {
  return row.bars.filter(
    (bar) => bar.variant !== 'demand' && bar.column <= column && column < bar.column + bar.span,
  );
}

/** A cell in words: its figure, then every bar in it. */
export function cellDescription(row: TimelineRow, column: number): string {
  const cell = row.cells[column];
  const parts = [
    cell?.description ?? '',
    ...barsInColumn(row, column).map((bar) => bar.description),
  ];
  const text = parts.filter(Boolean).join('; ');
  return text || 'geen inzet';
}

/** The part of its month that lies before a day, and after it: 0 to 1. */
export function dayOffsets(start: string, end: string): { startOffset: number; endOffset: number } {
  const days = (iso: string) =>
    new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)), 0).getDate();
  const startDay = Number(start.slice(8, 10));
  const endDay = Number(end.slice(8, 10));
  return {
    startOffset: (startDay - 1) / days(start),
    endOffset: (days(end) - endDay) / days(end),
  };
}

/** The kinds of mark a legend can explain. */
export type LegendKind =
  'filled' | 'established' | 'tentative' | 'open' | 'demand' | 'unavailable' | 'over' | 'mismatch';

/**
 * The marks that occur in what is drawn, in the legend's fixed order. A
 * legend explains the picture in front of the reader, not every mark there is.
 */
export function occurringLegend<R, B>(groups: readonly TimelineGroup<R, B>[]): LegendKind[] {
  const rows = groups.flatMap((group) => group.rows);
  const bars = rows.flatMap((row) => row.bars);
  const cells = rows.flatMap((row) => row.cells);
  const has: Record<LegendKind, boolean> = {
    demand: bars.some((bar) => bar.variant === 'demand'),
    filled: bars.some((bar) => bar.variant === 'filled'),
    established: bars.some((bar) => bar.closedSpan > 0),
    tentative: bars.some((bar) => bar.variant === 'tentative'),
    open: bars.some((bar) => bar.variant === 'open'),
    unavailable: cells.some((cell) => cell.state === 'unavailable'),
    over: cells.some((cell) => cell.state === 'over'),
    mismatch: bars.some((bar) => bar.mark === 'mismatch'),
  };
  return (Object.keys(has) as LegendKind[]).filter((kind) => has[kind]);
}

/**
 * How far the board scrolls when it opens, so the current month is the first
 * one beside the names. On a narrow screen only a few months fit; the ones
 * before today are history and the one that runs must be in view.
 */
export function openingScroll(monthLeft: number, nameWidth: number, maxScroll: number): number {
  return Math.max(0, Math.min(maxScroll, monthLeft - nameWidth));
}
