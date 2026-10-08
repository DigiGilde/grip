import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { formatPercent } from '@/lib/format';
import type { OccupancyCell, OccupancyMonth, PersonOccupancy } from '../api';
import { monthAbbreviation, monthName } from '../labels';
import { describeCell, personBoardPath } from './model';
import { cellState, fillLevel } from './scale';

export interface CellRef {
  personId: string;
  month: string;
}

interface HeatmapProps {
  label: string;
  persons: PersonOccupancy[];
  /** The months of the year, with the totals over the persons shown. */
  months: OccupancyMonth[];
  /** Today's month (`YYYY-MM`); marked when it is one of the columns. */
  currentMonth: string;
  selected: CellRef | null;
  onSelect: (cell: CellRef | null) => void;
  /** A muted line under a name, e.g. "Vrij, laatste inzet tot ...". */
  rowNote?: (person: PersonOccupancy) => string;
  /**
   * Changes when the selection was made from outside the table (a figure
   * on top): keyboard focus then moves to the selected cell.
   */
  focusRequest?: number;
}

/**
 * One cell of the heat map: the fill carries the value, the number is small
 * and secondary, and the full meaning is there as text for a screen reader.
 */
export function HeatCell({ cell }: { cell: OccupancyCell }) {
  const pct = Number(cell.pct);
  const state = cellState(cell.available, pct);
  const tentative = Number(cell.tentative_pct);
  const share = pct > 0 ? Math.min(1, tentative / pct) : 0;
  return (
    <span
      className="grip-occ__cell"
      data-state={state}
      {...(state === 'filled' ? { 'data-level': fillLevel(pct) } : {})}
      {...(tentative > 0 ? { 'data-tentative': '' } : {})}
      {...(cell.established ? { 'data-established': '' } : {})}
    >
      {share > 0 && (
        <span
          className="grip-occ__tentative"
          style={{ width: `${share * 100}%` }}
          aria-hidden="true"
        />
      )}
      {(state === 'filled' || state === 'over') && (
        <span className="grip-occ__value" aria-hidden="true">
          {state === 'over' ? '! ' : ''}
          {formatPercent(Math.round(pct))}
        </span>
      )}
      {cell.established && state !== 'unavailable' && state !== 'empty' && (
        <span className="grip-occ__established" aria-hidden="true" />
      )}
      <span className="grip-sr-only">{describeCell(cell)}</span>
    </span>
  );
}

/**
 * The occupancy as a heat map that is a table in the markup: a column header
 * per month, a row header per person, and every value as text. The grid is
 * one tab stop; the arrow keys walk the cells and Enter shows what a cell
 * consists of.
 */
export function Heatmap({
  label,
  persons,
  months,
  currentMonth,
  selected,
  onSelect,
  rowNote,
  focusRequest = 0,
}: HeatmapProps) {
  const tableRef = useRef<HTMLTableElement>(null);
  const [focus, setFocus] = useState<[number, number]>([0, 0]);
  // A filter can shorten the list under the remembered position.
  const focusRow = Math.min(focus[0], Math.max(0, persons.length - 1));
  const nowIndex = months.findIndex((month) => month.month === currentMonth);
  // The rule between what lies behind us and what lies ahead.
  const hasBoundary = nowIndex > 0;

  // A selection made from a figure on top: put the keyboard there, once.
  // The selection can arrive a render after the request (the address
  // changes in a transition), so the request waits for it. Focusing the
  // cell is enough; its focus handler moves the tab stop along.
  const handledRequest = useRef(0);
  useEffect(() => {
    if (focusRequest === handledRequest.current || !selected) return;
    const row = persons.findIndex((person) => person.person_id === selected.personId);
    const column = months.findIndex((month) => month.month === selected.month);
    if (row < 0 || column < 0) return;
    handledRequest.current = focusRequest;
    const cell = tableRef.current?.querySelector<HTMLElement>(`[data-cell="${row}-${column}"]`);
    cell?.focus();
    cell?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [focusRequest, selected, persons, months]);

  const moveTo = (row: number, column: number) => {
    const nextRow = Math.max(0, Math.min(persons.length - 1, row));
    const nextColumn = Math.max(0, Math.min(months.length - 1, column));
    setFocus([nextRow, nextColumn]);
    tableRef.current
      ?.querySelector<HTMLElement>(`[data-cell="${nextRow}-${nextColumn}"]`)
      ?.focus();
  };

  const activate = (person: PersonOccupancy, cell: OccupancyCell | undefined) => {
    if (!cell) return;
    const same = selected?.personId === person.person_id && selected.month === cell.month;
    onSelect(same ? null : { personId: person.person_id, month: cell.month });
  };

  const onKeyDown = (
    event: KeyboardEvent<HTMLTableCellElement>,
    row: number,
    column: number,
    person: PersonOccupancy,
  ) => {
    const moves: Record<string, [number, number]> = {
      ArrowRight: [row, column + 1],
      ArrowLeft: [row, column - 1],
      ArrowDown: [row + 1, column],
      ArrowUp: [row - 1, column],
      Home: [row, 0],
      End: [row, months.length - 1],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      moveTo(move[0], move[1]);
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      activate(person, person.cells[column]);
    } else if (event.key === 'Escape') {
      onSelect(null);
    }
  };

  const columnClass = (index: number) =>
    [
      index === nowIndex ? 'grip-occ__now' : '',
      hasBoundary && index === nowIndex ? 'grip-occ__boundary' : '',
    ]
      .filter(Boolean)
      .join(' ') || undefined;

  return (
    <div className="grip-occ__scroll">
      <table ref={tableRef} className="grip-occ__table" role="grid" aria-label={label}>
        <thead>
          {hasBoundary && (
            <tr className="grip-occ__group">
              <td />
              <th scope="colgroup" colSpan={nowIndex}>
                Verstreken
              </th>
              <th scope="colgroup" colSpan={months.length - nowIndex} className="grip-occ__boundary">
                Lopend en komend
              </th>
              <td />
            </tr>
          )}
          <tr>
            <th scope="col">Persoon</th>
            {months.map((month, index) => (
              <th
                key={month.month}
                scope="col"
                abbr={monthName(month.month)}
                className={columnClass(index)}
                {...(index === nowIndex ? { 'aria-current': 'date' as const } : {})}
              >
                {index === nowIndex && <span className="grip-occ__now-tag">nu</span>}
                {monthAbbreviation(month.month)}
              </th>
            ))}
            <th scope="col">Gemiddeld</th>
          </tr>
        </thead>
        <tbody>
          {persons.map((person, row) => {
            const overCount = person.over_months?.length ?? 0;
            const average = person.average_pct === null ? null : Number(person.average_pct);
            return (
              <tr key={person.person_id} data-person={person.person_id}>
                <th scope="row">
                  <Link
                    to={personBoardPath(person.person_id)}
                    className="grip-occ__name"
                    title={`${person.person_name} op het inzetbord`}
                  >
                    {person.person_name}
                  </Link>
                  {overCount > 0 && (
                    <span className="grip-occ__name-flag">
                      <span className="grip-mark" aria-hidden="true">
                        !
                      </span>{' '}
                      Boven 100% in {overCount} {overCount === 1 ? 'maand' : 'maanden'}
                    </span>
                  )}
                  {rowNote?.(person) && (
                    <span className="grip-occ__row-note">{rowNote(person)}</span>
                  )}
                </th>
                {months.map((month, column) => {
                  const cell = person.cells[column];
                  const isSelected =
                    selected?.personId === person.person_id && selected.month === month.month;
                  return (
                    <td
                      key={month.month}
                      role="gridcell"
                      className={columnClass(column)}
                      data-cell={`${row}-${column}`}
                      data-month={month.month}
                      tabIndex={focusRow === row && focus[1] === column ? 0 : -1}
                      aria-selected={isSelected}
                      onFocus={() => setFocus([row, column])}
                      onClick={() => activate(person, cell)}
                      onKeyDown={(event) => onKeyDown(event, row, column, person)}
                    >
                      {cell && <HeatCell cell={cell} />}
                    </td>
                  );
                })}
                <td>
                  <span className="grip-occ__average">
                    <span className="grip-occ__track" aria-hidden="true">
                      <span
                        className="grip-occ__bar"
                        style={{ width: `${Math.max(0, Math.min(100, average ?? 0))}%` }}
                      />
                    </span>
                    <span className="grip-occ__average-number">
                      {average === null ? '' : formatPercent(Math.round(average))}
                    </span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Samen</th>
            {months.map((month, index) => (
              <td
                key={month.month}
                className={[columnClass(index), month.pct === null || Number(month.pct) === 0 ? 'grip-occ__zero' : '']
                  .filter(Boolean)
                  .join(' ')}
              >
                {month.pct === null ? '' : formatPercent(Math.round(Number(month.pct)))}
              </td>
            ))}
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
