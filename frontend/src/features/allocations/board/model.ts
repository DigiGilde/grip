/**
 * The board as rows and bars: pure functions from the API response to what
 * is drawn. No dates are computed from "now" here; the server says which
 * month is the current one.
 */
import { formatFte, formatMonth, formatPercent, formatPeriod } from '@/lib/format';
import {
  assignLanes,
  monthKey,
  monthShort,
  placePeriod,
  type TimelineGroup,
} from '@/ui/timeline/layout';
import type { Board, BoardBar, BoardCell, BoardOpenRole, BoardPerson } from './api';

export { assignLanes, monthShort, placePeriod, shiftMonth } from '@/ui/timeline/layout';

export type View = 'person' | 'team' | 'assignment';
export type Show = 'all' | 'room' | 'over';

export interface PlacedBar {
  key: string;
  /** Index of the first month column the bar covers. */
  column: number;
  span: number;
  lane: number;
  /** Leading months of the bar that are closed, counted in columns. */
  closedSpan: number;
  /** The bar starts before, or ends after, the months on screen. */
  clippedStart: boolean;
  clippedEnd: boolean;
  label: string;
  tentative: boolean;
  /** An open role: demand without anyone on it. */
  open: boolean;
  mismatch: boolean;
  allocation?: BoardBar;
  role?: BoardOpenRole;
}

export interface RowModel {
  key: string;
  label: string;
  /** One quiet line under the label. */
  summary: string;
  /** Said louder than the summary, when something needs attention. */
  attention: string;
  kind: 'person' | 'role' | 'line';
  person?: BoardPerson;
  role?: BoardOpenRole;
  cells: (BoardCell | null)[];
  bars: PlacedBar[];
  lanes: number;
}

export interface GroupModel {
  key: string;
  /** Empty for the one group of a flat view. */
  title: string;
  rows: RowModel[];
}

function allocationBar(
  months: readonly string[],
  bar: BoardBar,
  label: string,
): PlacedBar | null {
  const place = placePeriod(months, bar.start_date, bar.end_date);
  if (!place) return null;
  const closed = new Set(bar.closed_months.map(monthKey));
  let closedSpan = 0;
  while (closedSpan < place.span && closed.has(monthKey(months[place.column + closedSpan] ?? ''))) {
    closedSpan += 1;
  }
  return {
    ...place,
    key: bar.allocation_id,
    lane: 0,
    closedSpan,
    label: `${formatPercent(bar.fte_pct)} ${label}`.trim(),
    tentative: bar.tentative,
    open: false,
    mismatch: bar.category_mismatch === true,
    allocation: bar,
  };
}

function roleBar(months: readonly string[], role: BoardOpenRole): PlacedBar | null {
  const place = placePeriod(months, role.start_date, role.end_date);
  if (!place) return null;
  return {
    ...place,
    key: `role-${role.budget_line_id}`,
    lane: 0,
    closedSpan: 0,
    label: `${formatFte(role.unfilled_fte)} FTE open`,
    tentative: false,
    open: true,
    mismatch: false,
    role,
  };
}

export function personSummary(
  person: BoardPerson,
  currentMonth = '',
): { summary: string; attention: string } {
  const over = person.over_months ?? [];
  const attention =
    over.length > 0 ? `Boven 100% in ${over.map((month) => monthShort(month)).join(', ')}` : '';
  if (person.cells.length === 0) return { summary: '', attention };
  // Nothing now and nothing ahead: one plain statement instead of "nu 0%".
  if (person.idle_from && currentMonth && monthKey(person.idle_from) <= monthKey(currentMonth)) {
    return { summary: 'Geen inzet gepland', attention };
  }
  const parts: string[] = [];
  if (person.now_pct !== null && person.now_pct !== undefined) {
    parts.push(`Nu ${formatPercent(person.now_pct)}`);
  }
  if (person.idle_from) parts.push(`geen inzet vanaf ${monthShort(person.idle_from)}`);
  else if (person.room_from) parts.push(`ruimte vanaf ${monthShort(person.room_from)}`);
  const text = parts.join(', ');
  return { summary: text.charAt(0).toUpperCase() + text.slice(1), attention };
}

function personRow(months: readonly string[], person: BoardPerson, currentMonth: string): RowModel {
  const bars = person.bars
    .map((bar) => allocationBar(months, bar, bar.assignment_name ?? 'Opdracht'))
    .filter((bar): bar is PlacedBar => bar !== null);
  const lanes = assignLanes(bars);
  const byMonth = new Map(person.cells.map((cell) => [monthKey(cell.month), cell] as const));
  return {
    key: person.person_id,
    label: person.person_name,
    ...personSummary(person, currentMonth),
    kind: 'person',
    person,
    cells: months.map((month) => byMonth.get(monthKey(month)) ?? null),
    bars,
    lanes,
  };
}

function roleRow(months: readonly string[], role: BoardOpenRole): RowModel {
  const bar = roleBar(months, role);
  return {
    key: `role-${role.budget_line_id}`,
    label: role.role ?? role.description,
    summary: `${role.assignment_name}, ${formatFte(role.unfilled_fte)} van ${formatFte(role.fte)} FTE niet ingevuld`,
    attention: '',
    kind: 'role',
    role,
    cells: months.map(() => null),
    bars: bar ? [bar] : [],
    lanes: 1,
  };
}

export function showPerson(person: BoardPerson, show: Show): boolean {
  if (show === 'over') return (person.over_months ?? []).length > 0;
  if (show === 'room') return Boolean(person.room_from) || Boolean(person.idle_from);
  return true;
}

const byLabel = (a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label, 'nl');

/** Assignments as groups, their roles as rows, with who fills them as bars. */
function assignmentGroups(board: Board): GroupModel[] {
  const groups = new Map<string, { title: string; lines: Map<string, RowModel> }>();
  const group = (id: string, title: string) => {
    let found = groups.get(id);
    if (!found) {
      found = { title, lines: new Map() };
      groups.set(id, found);
    }
    return found;
  };
  for (const person of board.persons) {
    for (const bar of person.bars) {
      if (!bar.assignment_id || !bar.budget_line_id) continue;
      const lines = group(bar.assignment_id, bar.assignment_name ?? 'Opdracht').lines;
      let row = lines.get(bar.budget_line_id);
      if (!row) {
        row = {
          key: `line-${bar.budget_line_id}`,
          label: bar.role ?? bar.line_description ?? 'Rol',
          summary: '',
          attention: '',
          kind: 'line',
          cells: board.months.map(() => null),
          bars: [],
          lanes: 1,
        };
        lines.set(bar.budget_line_id, row);
      }
      const placed = allocationBar(board.months, bar, bar.person_name);
      if (placed) row.bars.push(placed);
    }
  }
  for (const role of board.open_roles) {
    const lines = group(role.assignment_id, role.assignment_name).lines;
    const existing = lines.get(role.budget_line_id);
    const bar = roleBar(board.months, role);
    if (existing) {
      if (bar) existing.bars.push(bar);
      existing.role = role;
      existing.attention = `${formatFte(role.unfilled_fte)} van ${formatFte(role.fte)} FTE niet ingevuld`;
    } else {
      const row = roleRow(board.months, role);
      lines.set(role.budget_line_id, { ...row, key: `line-${role.budget_line_id}`, kind: 'line',
        summary: '', attention: `${formatFte(role.unfilled_fte)} van ${formatFte(role.fte)} FTE niet ingevuld` });
    }
  }
  return [...groups.entries()]
    .map(([key, value]) => ({
      key,
      title: value.title,
      rows: [...value.lines.values()]
        .map((row) => {
          const names = new Set(
            row.bars.filter((bar) => bar.allocation).map((bar) => bar.allocation?.person_name),
          );
          return {
            ...row,
            summary: names.size === 0 ? 'Nog niemand' : names.size === 1 ? '1 persoon' : `${names.size} personen`,
            lanes: assignLanes(row.bars),
          };
        })
        .sort(byLabel),
    }))
    .sort((a, b) => a.title.localeCompare(b.title, 'nl'));
}

/** The groups and rows of the board for a view and a filter. */
export function buildGroups(board: Board, view: View, show: Show): GroupModel[] {
  if (view === 'assignment') return assignmentGroups(board);
  const groups: GroupModel[] = [];
  const roles = board.open_roles.map((role) => roleRow(board.months, role));
  if (roles.length > 0 && show === 'all') {
    groups.push({ key: 'open-roles', title: 'Open rollen', rows: roles });
  }
  const people = board.persons
    .filter((person) => showPerson(person, show))
    .map((person) => personRow(board.months, person, board.current_month));
  if (view === 'person') {
    groups.push({ key: 'people', title: roles.length > 0 && show === 'all' ? 'Mensen' : '', rows: people });
    return groups;
  }
  const teams = new Map<string, RowModel[]>();
  for (const row of people) {
    const team = row.person?.manager_name ?? '';
    teams.set(team, [...(teams.get(team) ?? []), row]);
  }
  for (const [team, rows] of [...teams.entries()].sort(([a], [b]) =>
    a === '' ? 1 : b === '' ? -1 : a.localeCompare(b, 'nl'),
  )) {
    groups.push({
      key: `team-${team}`,
      title: team ? `Team van ${team}` : 'Zonder leidinggevende',
      rows,
    });
  }
  return groups;
}

/** The R14 signal in words, with the categories when the reader got them. */
export function mismatchText(
  bar: BoardBar,
  name: (category: string) => string = (category) => `categorie ${category}`,
): string {
  if (!bar.category_mismatch) return '';
  if (bar.person_category && bar.line_category) {
    const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
    return `declareert in ${lower(name(bar.person_category))}, de regel rekent met ${lower(name(bar.line_category))}`;
  }
  return 'declareert in een andere categorie dan de regel aanneemt';
}

/** A bar in words: what, how much, when, and how firm. */
export function describeBar(
  bar: PlacedBar,
  name?: (category: string) => string,
): string {
  if (bar.role) {
    const role = bar.role;
    return [
      `open rol ${role.role ?? role.description}`,
      `${formatFte(role.unfilled_fte)} van ${formatFte(role.fte)} FTE niet ingevuld`,
      formatPeriod(role.start_date, role.end_date),
    ]
      .filter(Boolean)
      .join(', ');
  }
  const allocation = bar.allocation;
  if (!allocation) return bar.label;
  const firm = allocation.verbally_agreed
    ? 'onder voorbehoud, mondeling akkoord'
    : allocation.tentative
      ? 'onder voorbehoud'
      : '';
  const closed = allocation.closed_months;
  return [
    `${formatPercent(allocation.fte_pct)} ${allocation.assignment_name ?? ''}`.trim(),
    allocation.role ?? allocation.line_description ?? '',
    formatPeriod(allocation.start_date, allocation.end_date),
    firm,
    closed.length > 0 ? `vastgesteld t/m ${formatMonth(closed[closed.length - 1])}` : '',
    mismatchText(allocation, name),
  ]
    .filter(Boolean)
    .join(', ');
}

/** The bars of a row that cover a month column. */
export function barsInColumn(row: RowModel, column: number): PlacedBar[] {
  return row.bars.filter((bar) => bar.column <= column && column < bar.column + bar.span);
}

export type TotalState = 'none' | 'unavailable' | 'empty' | 'quiet' | 'room' | 'over';

/** What the total of a month should look like: loud only when it needs attention. */
export function totalState(cell: BoardCell | null, month: string, currentMonth: string): TotalState {
  if (!cell) return 'none';
  if (!cell.available) return 'unavailable';
  const pct = Number(cell.pct);
  if (cell.over) return 'over';
  const ahead = monthKey(month) >= monthKey(currentMonth);
  if (pct === 0) return ahead ? 'room' : 'empty';
  return ahead && pct < 100 ? 'room' : 'quiet';
}

/** The visible text of a month's total. */
export function totalText(cell: BoardCell | null, state: TotalState): string {
  if (!cell || state === 'none' || state === 'unavailable') return '';
  if (state === 'over') return `! ${formatPercent(cell.pct)}`;
  // The bars already show what is allocated; the figure says what is left.
  if (state === 'room') return `vrij ${formatPercent(100 - Number(cell.pct))}`;
  if (state === 'empty') return '';
  return formatPercent(cell.pct);
}

/** A cell in words, for a screen reader: the total, then what it consists of. */
export function describeCell(row: RowModel, column: number, month: string, currentMonth: string): string {
  const cell = row.cells[column] ?? null;
  const state = totalState(cell, month, currentMonth);
  const words: string[] = [];
  if (state === 'unavailable') words.push('niet inzetbaar');
  else if (cell) {
    words.push(`totaal ${formatPercent(cell.pct)}`);
    if (state === 'over') words.push('boven 100%');
    else if (state === 'room') words.push(`vrij ${formatPercent(100 - Number(cell.pct))}`);
    if (Number(cell.tentative_pct) > 0) {
      words.push(`waarvan ${formatPercent(cell.tentative_pct)} onder voorbehoud`);
    }
    if (cell.established) words.push('vastgesteld');
  }
  const bars = barsInColumn(row, column).map((bar) => describeBar(bar));
  if (bars.length === 0 && words.length === 0) return 'geen inzet';
  return [...words, ...bars].join('; ');
}

/** The figure of a month in words, without the bars. */
function cellWords(cell: BoardCell | null, state: TotalState): string {
  if (state === 'unavailable') return 'niet inzetbaar';
  if (!cell) return '';
  const words = [`totaal ${formatPercent(cell.pct)}`];
  if (state === 'over') words.push('boven 100%');
  else if (state === 'room') words.push(`vrij ${formatPercent(100 - Number(cell.pct))}`);
  if (Number(cell.tentative_pct) > 0) {
    words.push(`waarvan ${formatPercent(cell.tentative_pct)} onder voorbehoud`);
  }
  if (cell.established) words.push('vastgesteld');
  return words.join('; ');
}

/** The rows of the board as the shared timeline draws them. */
export function toTimeline(
  groups: readonly GroupModel[],
  months: readonly string[],
  currentMonth: string,
  linkFor: (row: RowModel) => { href: string; text: string } | null = () => null,
  name?: (category: string) => string,
): TimelineGroup<RowModel, PlacedBar>[] {
  return groups.map((group) => ({
    key: group.key,
    title: group.title,
    rows: group.rows.map((row) => ({
      key: row.key,
      label: row.label,
      summary: row.summary,
      attention: row.attention,
      lanes: row.lanes,
      link: linkFor(row),
      data: row,
      cells: months.map((month, column) => {
        const cell = row.cells[column] ?? null;
        const state = totalState(cell, month, currentMonth);
        return {
          text: totalText(cell, state),
          state,
          established: cell?.established === true,
          description: cellWords(cell, state),
        };
      }),
      bars: row.bars.map((bar) => ({
        key: bar.key,
        column: bar.column,
        span: bar.span,
        lane: bar.lane,
        label: bar.label,
        description: describeBar(bar, name),
        variant: bar.open ? ('open' as const) : bar.tentative ? ('tentative' as const) : ('filled' as const),
        closedSpan: bar.closedSpan,
        clippedStart: bar.clippedStart,
        clippedEnd: bar.clippedEnd,
        ...(bar.mismatch ? { mark: '≠' } : {}),
        data: bar,
      })),
    })),
  }));
}
