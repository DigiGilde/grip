import { useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
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
  | 'filled'
  | 'established'
  | 'tentative'
  | 'open'
  | 'demand'
  | 'unavailable'
  | 'over'
  | 'mismatch';

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
}

function Bar<B>({ bar, onActivate }: { bar: TimelineBar<B>; onActivate: () => void }) {
  const frame = bar.variant === 'demand';
  return (
    // The bar is the pointer's way in. A keyboard or screen reader user gets
    // the same from the cell, whose text names every bar in it.
    <span
      className="grip-board__bar"
      aria-hidden="true"
      title={bar.description}
      style={{ '--span': bar.span, '--lane': bar.lane } as CSSProperties}
      data-variant={bar.variant}
      {...(bar.variant === 'tentative' ? { 'data-tentative': '' } : {})}
      {...(bar.variant === 'open' ? { 'data-open': '' } : {})}
      {...(frame ? { 'data-demand': '' } : {})}
      {...(bar.mark ? { 'data-mark': bar.mark } : {})}
      {...(bar.clippedStart ? { 'data-clipped-start': '' } : {})}
      {...(bar.clippedEnd ? { 'data-clipped-end': '' } : {})}
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
        <span className="grip-board__bar-label">
          {bar.mark ? `${bar.mark} ` : ''}
          {bar.label}
        </span>
      )}
    </span>
  );
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
}: TimelineProps<R, B>) {
  const tableRef = useRef<HTMLTableElement>(null);
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
    tableRef.current
      ?.querySelector<HTMLElement>(`[data-cell="${nextRow}-${nextColumn}"]`)
      ?.focus();
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
    <div className="grip-board">
      <div className="grip-board__scroll">
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
                      const isSelected =
                        selected?.rowKey === row.key && selected.column === column;
                      return (
                        <td
                          key={month}
                          data-cell={`${index}-${column}`}
                          data-state={state}
                          data-actionable=""
                          className={column === nowIndex ? 'grip-board__now' : undefined}
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
                            <Bar key={bar.key} bar={bar} onActivate={() => onBar(bar, row)} />
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
