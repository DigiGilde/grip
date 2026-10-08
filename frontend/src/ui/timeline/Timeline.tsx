import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { formatMonth } from '@/lib/format';
import {
  barsInColumn,
  cellDescription,
  monthKey,
  monthShort,
  type TimelineBar,
  type TimelineGroup,
  type TimelineRow,
} from './layout';
import './timeline.css';

if (import.meta.env.MODE !== 'test') void import('@nldd/design-system/link');

export interface CellRef {
  rowKey: string;
  column: number;
}

export type LegendItem =
  'filled' | 'established' | 'tentative' | 'open' | 'demand' | 'unavailable' | 'over' | 'mismatch';

const LEGEND_TEXT: Record<LegendItem, string> = {
  filled: 'Inzet, gepland',
  established: 'Vastgesteld (afgesloten maand)',
  tentative: 'Onder voorbehoud (potentiële opdracht)',
  open: 'Open: nog niet ingevuld',
  demand: 'Gevraagd: de periode van de rol',
  unavailable: 'Niet inzetbaar',
  over: 'Boven wat kan of gevraagd is',
  mismatch: '≠ Andere tariefcategorie dan de regel aanneemt',
};

interface TimelineProps<R, B> {
  label: string;
  /** What the first column holds, e.g. "Persoon" or "Rol". */
  rowHeader: string;
  /** First days of the months on screen. */
  months: string[];
  currentMonth: string;
  /** First days of closed months, marked in the header. */
  closedMonths?: readonly string[];
  groups: TimelineGroup<R, B>[];
  selected: CellRef | null;
  /** A bar was activated with the pointer. */
  onBar: (bar: TimelineBar<B>, row: TimelineRow<R, B>) => void;
  /** A cell was activated: by keyboard always, by pointer on a stretch without one bar. */
  onCell: (row: TimelineRow<R, B>, column: number, source: 'keyboard' | 'pointer') => void;
  legend: readonly LegendItem[];
  /**
   * Widen the month columns so the months fill the width there is. For a
   * timeline of one thing with a known period; a board that pages through
   * months keeps its fixed columns.
   */
  fit?: boolean;
  /**
   * Show the weeks inside each month and draw bars from their first to
   * their last day. For a period of a few months.
   */
  days?: boolean;
  /** What a row can do besides its bars, drawn in the row header. */
  rowActions?: (row: TimelineRow<R, B>) => ReactNode;
}

/** The width of a month column on a board that pages through months. */
const MIN_COLUMN = 72;
/** The narrowest a column gets when the whole period has to fit the width. */
const MIN_FIT_COLUMN = 30;
/** Below this width a column has no room for its figure; the bars carry it. */
const COMPACT_BELOW = 56;
/** Days of the month that get a mark when days are shown: the weeks. */
const WEEK_DAYS = [1, 8, 15, 22, 29];

const daysIn = (month: string) =>
  new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate();

interface BarProps<B> {
  bar: TimelineBar<B>;
  onActivate: () => void;
  /** Draw from the first to the last day instead of over whole months. */
  days: boolean;
  /** There is free room next to the bar for a label that does not fit in it. */
  roomAfter: boolean;
  roomBefore: boolean;
  /** Changes when the columns change width, so the fit is measured again. */
  columnWidth: number;
}

function Bar<B>({ bar, onActivate, days, roomAfter, roomBefore, columnWidth }: BarProps<B>) {
  const frame = bar.variant === 'demand';
  const ref = useRef<HTMLSpanElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  // A name is never cut off when there is room beside the bar: it moves there.
  const [outside, setOutside] = useState<'' | 'after' | 'before'>('');
  useLayoutEffect(() => {
    const el = ref.current;
    const label = labelRef.current;
    if (!el || !label) return;
    const fits = label.scrollWidth <= el.clientWidth + 1;
    setOutside(fits ? '' : roomAfter ? 'after' : roomBefore ? 'before' : '');
  }, [
    bar.label,
    bar.mark,
    bar.span,
    bar.startOffset,
    bar.endOffset,
    columnWidth,
    roomAfter,
    roomBefore,
  ]);
  return (
    // The bar is the pointer's way in. A keyboard or screen reader user gets
    // the same from the cell, whose text names every bar in it.
    <span
      ref={ref}
      className="grip-board__bar"
      aria-hidden="true"
      title={bar.description}
      style={
        {
          '--span': bar.span,
          '--lane': bar.lane,
          ...(days
            ? { '--start-offset': bar.startOffset ?? 0, '--end-offset': bar.endOffset ?? 0 }
            : {}),
        } as CSSProperties
      }
      data-variant={bar.variant}
      {...(bar.variant === 'tentative' ? { 'data-tentative': '' } : {})}
      {...(bar.variant === 'open' ? { 'data-open': '' } : {})}
      {...(frame ? { 'data-demand': '' } : {})}
      {...(bar.mark ? { 'data-mark': bar.mark } : {})}
      {...(bar.clippedStart ? { 'data-clipped-start': '' } : {})}
      {...(bar.clippedEnd ? { 'data-clipped-end': '' } : {})}
      {...(outside ? { 'data-label': outside } : {})}
      data-bar={bar.key}
      {...(frame
        ? {}
        : {
            onClick: (event) => {
              event.stopPropagation();
              onActivate();
            },
          })}
    >
      {bar.closedSpan > 0 && bar.variant === 'filled' && (
        <span
          className="grip-board__bar-closed"
          style={{ '--closed': bar.closedSpan } as CSSProperties}
        />
      )}
      {!frame && (
        <span ref={labelRef} className="grip-board__bar-label">
          {bar.mark ? `${bar.mark} ` : ''}
          {bar.label}
        </span>
      )}
    </span>
  );
}

/** Whether the lane of a bar is free for a few columns on one side of it. */
function laneIsFree<B>(
  row: TimelineRow<unknown, B>,
  bar: TimelineBar<B>,
  side: 'after' | 'before',
  months: number,
) {
  const end = bar.column + bar.span;
  if (side === 'after' ? end >= months : bar.column === 0) return false;
  return !row.bars.some((other) => {
    if (other === bar || other.variant === 'demand' || other.lane !== bar.lane) return false;
    const otherEnd = other.column + other.span;
    return side === 'after'
      ? other.column >= end && other.column < end + 3
      : otherEnd <= bar.column && otherEnd > bar.column - 3;
  });
}

/**
 * Rows over months, drawn as bars. A table in the markup: a column header
 * per month, a row header per row, and every cell with its meaning as text.
 * The grid is one tab stop; the arrow keys walk the cells and Enter acts on
 * the cell in focus. Used for people over months, assignments with their
 * roles, and the roles of one assignment; the rows are a parameter.
 */
export function Timeline<R, B>({
  label,
  rowHeader,
  months,
  currentMonth,
  closedMonths = [],
  groups,
  selected,
  onBar,
  onCell,
  legend,
  fit = false,
  days = false,
  rowActions,
}: TimelineProps<R, B>) {
  const tableRef = useRef<HTMLTableElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // With `fit` the months share the width that is left beside the names.
  const [columnWidth, setColumnWidth] = useState(MIN_COLUMN);
  const monthCount = months.length;
  useLayoutEffect(() => {
    if (!fit) return;
    const box = scrollRef.current;
    if (!box) return;
    const measure = () => {
      const name = box.querySelector<HTMLElement>('thead th')?.offsetWidth ?? 0;
      const room = box.clientWidth - name - 2;
      setColumnWidth(Math.max(MIN_FIT_COLUMN, Math.floor(room / Math.max(1, monthCount))));
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(box);
    return () => observer.disconnect();
  }, [fit, monthCount]);
  const rows = groups.flatMap((group) => group.rows);
  const [focus, setFocus] = useState<[number, number]>([0, 0]);
  const focusRow = Math.min(focus[0], Math.max(0, rows.length - 1));
  const focusColumn = Math.min(focus[1], Math.max(0, months.length - 1));
  const nowIndex = months.findIndex((month) => monthKey(month) === monthKey(currentMonth));
  const closed = new Set(closedMonths.map(monthKey));
  // The position of every row in the whole grid, across the groups.
  const indexOf = new Map(rows.map((row, position) => [row.key, position] as const));

  const moveTo = (row: number, column: number) => {
    const nextRow = Math.max(0, Math.min(rows.length - 1, row));
    const nextColumn = Math.max(0, Math.min(months.length - 1, column));
    setFocus([nextRow, nextColumn]);
    tableRef.current?.querySelector<HTMLElement>(`[data-cell="${nextRow}-${nextColumn}"]`)?.focus();
  };

  const onKeyDown = (
    event: KeyboardEvent<HTMLTableCellElement>,
    rowIndex: number,
    column: number,
    row: TimelineRow<R, B>,
  ) => {
    const moves: Record<string, [number, number]> = {
      ArrowRight: [rowIndex, column + 1],
      ArrowLeft: [rowIndex, column - 1],
      ArrowDown: [rowIndex + 1, column],
      ArrowUp: [rowIndex - 1, column],
      Home: [rowIndex, 0],
      End: [rowIndex, months.length - 1],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      moveTo(move[0], move[1]);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onCell(row, column, 'keyboard');
    }
  };

  return (
    <div
      className="grip-board"
      {...(days ? { 'data-days': '' } : {})}
      {...(fit && columnWidth < COMPACT_BELOW ? { 'data-compact': '' } : {})}
      style={fit ? ({ '--board-column': `${columnWidth}px` } as CSSProperties) : undefined}
    >
      <div ref={scrollRef} className="grip-board__scroll" data-spacing="grid">
        <table
          ref={tableRef}
          className="grip-board__table"
          role="grid"
          aria-label={label}
          style={{ '--months': months.length } as CSSProperties}
        >
          <thead>
            <tr>
              <th scope="col">{rowHeader}</th>
              {months.map((month, index) => (
                <th
                  key={month}
                  scope="col"
                  abbr={formatMonth(month)}
                  className={index === nowIndex ? 'grip-board__now' : undefined}
                  {...(index === nowIndex ? { 'aria-current': 'date' as const } : {})}
                >
                  {index === nowIndex && <span className="grip-board__now-tag">nu</span>}
                  {monthShort(month)}
                  {(index === 0 || month.slice(5, 7) === '01') && (
                    <span className="grip-board__year">{month.slice(0, 4)}</span>
                  )}
                  {closed.has(monthKey(month)) && (
                    <span className="grip-board__closed-tag">
                      <span className="grip-board__dot" aria-hidden="true" />
                      afgesloten
                    </span>
                  )}
                  {days && (
                    // The weeks of the month, as the day each one starts on.
                    <span className="grip-board__weeks" aria-hidden="true">
                      {WEEK_DAYS.filter((day) => day <= daysIn(month)).map((day) => (
                        <span
                          key={day}
                          style={{ '--at': (day - 1) / daysIn(month) } as CSSProperties}
                        >
                          {day}
                        </span>
                      ))}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.key}>
              {group.title && (
                <tr className="grip-board__group">
                  <th scope="rowgroup" colSpan={months.length + 1}>
                    {group.title}
                  </th>
                </tr>
              )}
              {group.rows.map((row) => {
                const index = indexOf.get(row.key) ?? 0;
                return (
                  <tr key={row.key} style={{ '--lanes': row.lanes } as CSSProperties}>
                    <th scope="row">
                      <span className="grip-board__name">
                        {row.label}
                        {row.figure && <span className="grip-board__figure">{row.figure}</span>}
                      </span>
                      {row.attention && (
                        <span className="grip-board__attention">{row.attention}</span>
                      )}
                      {row.summary && <span className="grip-board__summary">{row.summary}</span>}
                      {rowActions && (
                        <span className="grip-board__row-actions">{rowActions(row)}</span>
                      )}
                      {row.link && (
                        <nldd-link
                          class="grip-board__row-link"
                          href={row.link.href}
                          text={row.link.text}
                          size="sm"
                        />
                      )}
                    </th>
                    {months.map((month, column) => {
                      const cell = row.cells[column];
                      const state = cell?.state ?? 'none';
                      const starting = row.bars.filter((bar) => bar.column === column);
                      const isSelected = selected?.rowKey === row.key && selected.column === column;
                      return (
                        <td
                          key={month}
                          data-cell={`${index}-${column}`}
                          data-state={state}
                          data-actionable=""
                          className={column === nowIndex ? 'grip-board__now' : undefined}
                          {...(days ? { style: { '--days': daysIn(month) } as CSSProperties } : {})}
                          tabIndex={index === focusRow && column === focusColumn ? 0 : -1}
                          aria-selected={isSelected}
                          onFocus={() => setFocus([index, column])}
                          onKeyDown={(event) => onKeyDown(event, index, column, row)}
                          onClick={() => {
                            setFocus([index, column]);
                            const here = barsInColumn(row, column);
                            const only = here.length === 1 ? here[0] : undefined;
                            if (only) onBar(only, row);
                            else onCell(row, column, 'pointer');
                          }}
                        >
                          <span className="grip-board__total" data-state={state} aria-hidden="true">
                            {cell?.established && state !== 'unavailable' && (
                              <span className="grip-board__dot" />
                            )}
                            {cell?.text ?? ''}
                          </span>
                          {starting.map((bar) => (
                            <Bar
                              key={bar.key}
                              bar={bar}
                              onActivate={() => onBar(bar, row)}
                              days={days}
                              columnWidth={fit ? columnWidth : MIN_COLUMN}
                              roomAfter={laneIsFree(row, bar, 'after', months.length)}
                              roomBefore={laneIsFree(row, bar, 'before', months.length)}
                            />
                          ))}
                          <span className="grip-board__sr-only">
                            {cellDescription(row as TimelineRow, column)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          ))}
        </table>
      </div>
      <ul className="grip-board__legend" aria-label="Legenda">
        {legend.map((item) => (
          <li key={item}>
            {item === 'over' ? (
              <span className="grip-board__legend-over">!</span>
            ) : item === 'mismatch' ? null : (
              <span className="grip-board__swatch" data-kind={item} aria-hidden="true" />
            )}
            {LEGEND_TEXT[item]}
          </li>
        ))}
      </ul>
    </div>
  );
}
