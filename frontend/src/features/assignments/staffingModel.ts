/** The roles of one assignment as rows of the shared timeline. */
import { mismatchText } from '@/features/allocations/board/model';
import { formatDate, formatFte, formatMonth, formatPercent, formatPeriod } from '@/lib/format';
import {
  assignLanes,
  dayOffsets,
  monthKey,
  monthShort,
  placePeriod,
  type CellState,
  type TimelineBar,
  type TimelineCell,
  type TimelineGroup,
} from '@/ui/timeline/layout';
import type { AssignmentStaffing, RoleBar, RoleGap, RoleMonth, RoleStaffing } from './staffingApi';

export interface RoleBarData {
  /** A person on the role. */
  bar?: RoleBar;
  /** A stretch of the role nobody fills. */
  gap?: RoleGap;
}

/** "0,3 FTE open vanaf okt". */
export function gapText(gap: RoleGap): string {
  return `${formatFte(gap.open_fte)} FTE open vanaf ${monthShort(gap.start)}`;
}

/** A person's inzet on a role, in words. */
export function describeRoleBar(bar: RoleBar, name?: (category: string) => string): string {
  const firm = bar.verbally_agreed
    ? 'onder voorbehoud, mondeling akkoord'
    : bar.tentative
      ? 'onder voorbehoud'
      : '';
  const closed = bar.closed_months;
  return [
    `${formatPercent(bar.fte_pct)} ${bar.person_name}`,
    formatPeriod(bar.start_date, bar.end_date),
    firm,
    closed.length > 0 ? `vastgesteld t/m ${formatMonth(closed[closed.length - 1])}` : '',
    bar.starts_on ? `start op ${formatDate(bar.starts_on)}` : '',
    bar.before_start ? 'de inzet begint voor de startdatum' : '',
    bar.outside_role_period ? 'deels buiten de periode van de rol' : '',
    mismatchText(bar, name),
  ]
    .filter(Boolean)
    .join(', ');
}

function monthCell(month: RoleMonth, currentMonth: string): TimelineCell {
  const asked = Number(month.asked_pct);
  const filled = Number(month.filled_pct);
  const ahead = monthKey(month.month) >= monthKey(currentMonth);
  let state: CellState = 'quiet';
  let text = filled > 0 ? formatPercent(month.filled_pct) : '';
  if (asked === 0 && filled === 0) state = 'none';
  else if (month.over) {
    state = 'over';
    text = formatPercent(month.filled_pct);
  } else if (Number(month.open_pct) > 0 && ahead) {
    state = 'room';
    text = `open ${formatPercent(month.open_pct)}`;
  } else if (filled === 0) state = 'empty';
  const words =
    state === 'none'
      ? ''
      : [
          `gevraagd ${formatPercent(month.asked_pct)}`,
          `ingevuld ${formatPercent(month.filled_pct)}`,
          month.over ? 'meer dan gevraagd' : '',
          Number(month.open_pct) > 0 ? `open ${formatPercent(month.open_pct)}` : '',
          month.closed ? 'afgesloten maand' : '',
        ]
          .filter(Boolean)
          .join(', ');
  return { text, state, established: month.closed && filled > 0, description: words };
}

function roleAttention(role: RoleStaffing): string {
  const parts: string[] = [];
  const first = (role.gaps ?? [])[0];
  if (first) parts.push(gapText(first));
  const over = (role.months ?? []).filter((month) => month.over);
  if (over.length > 0)
    parts.push(`meer ingezet dan gevraagd in ${over.map((m) => monthShort(m.month)).join(', ')}`);
  if (role.bars.some((bar) => bar.before_start)) parts.push('inzet voor de startdatum');
  if (role.bars.some((bar) => bar.outside_role_period))
    parts.push('inzet buiten de periode van de rol');
  const text = parts.join('; ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Day offsets only at an end that lies inside the months on screen. */
function clippedOffsets(
  place: { clippedStart: boolean; clippedEnd: boolean },
  start: string,
  end: string,
): { startOffset: number; endOffset: number } {
  const offsets = dayOffsets(start, end);
  return {
    startOffset: place.clippedStart ? 0 : offsets.startOffset,
    endOffset: place.clippedEnd ? 0 : offsets.endOffset,
  };
}

/** The roles as one group of timeline rows; `linkFor` adds the vacancy link. */
export function staffingRows(
  staffing: AssignmentStaffing,
  linkFor: (role: RoleStaffing) => { href: string; text: string } | null = () => null,
  name?: (category: string) => string,
): TimelineGroup<RoleStaffing, RoleBarData>[] {
  const months = staffing.months;
  const rows = staffing.roles.map((role) => {
    const bars: TimelineBar<RoleBarData>[] = [];
    for (const bar of role.bars) {
      const place = placePeriod(months, bar.start_date, bar.end_date);
      if (!place) continue;
      const closed = new Set(bar.closed_months.map(monthKey));
      let closedSpan = 0;
      while (
        closedSpan < place.span &&
        closed.has(monthKey(months[place.column + closedSpan] ?? ''))
      ) {
        closedSpan += 1;
      }
      const flagged = bar.before_start || bar.outside_role_period;
      bars.push({
        ...place,
        key: bar.allocation_id,
        lane: 0,
        closedSpan,
        label:
          `${formatPercent(bar.fte_pct)} ${bar.person_name}` +
          (bar.starts_on ? `, start op ${formatDate(bar.starts_on)}` : ''),
        description: describeRoleBar(bar, name),
        variant: bar.tentative ? 'tentative' : 'filled',
        ...(flagged
          ? { mark: 'attention' as const }
          : bar.category_mismatch
            ? { mark: 'mismatch' as const }
            : {}),
        // Where in its first and last month the inzet begins and ends.
        ...clippedOffsets(place, bar.start_date, bar.end_date),
        data: { bar },
      });
    }
    for (const gap of role.gaps ?? []) {
      const place = placePeriod(months, gap.start, gap.end);
      if (!place) continue;
      bars.push({
        ...place,
        key: `gap-${role.budget_line_id}-${gap.start}`,
        lane: 0,
        closedSpan: 0,
        label: `${formatFte(gap.open_fte)} FTE open`,
        description: `open: ${formatFte(gap.open_fte)} FTE niet ingevuld, ${formatMonth(gap.start)} t/m ${formatMonth(gap.end)}`,
        variant: 'open',
        data: { gap },
      });
    }
    const lanes = assignLanes(bars);
    const frame = placePeriod(months, role.start_date ?? null, role.end_date ?? null);
    if (frame && role.start_date && role.end_date) {
      bars.push({
        ...frame,
        key: `demand-${role.budget_line_id}`,
        lane: 0,
        closedSpan: 0,
        label: '',
        description: '',
        variant: 'demand',
        ...clippedOffsets(frame, role.start_date, role.end_date),
        data: {},
      });
    }
    const byMonth = new Map(
      (role.months ?? []).map((month) => [monthKey(month.month), month] as const),
    );
    const names = new Set(role.bars.map((bar) => bar.person_name));
    return {
      key: role.budget_line_id,
      // The description tells two lines with the same role apart.
      label: role.description || role.role || 'Rol',
      ...(role.fte ? { figure: `${formatFte(role.fte)} FTE` } : {}),
      attention: roleAttention(role),
      summary:
        role.fully_staffed && names.size > 0
          ? 'Volledig ingevuld'
          : names.size === 0
            ? 'Nog niemand ingezet'
            : names.size === 1
              ? '1 persoon'
              : `${names.size} personen`,
      cells: months.map((month) => {
        const found = byMonth.get(monthKey(month));
        return found
          ? monthCell(found, staffing.current_month)
          : { text: '', state: 'none' as const, established: false, description: '' };
      }),
      bars,
      lanes,
      link: linkFor(role),
      data: role,
    };
  });
  return [{ key: 'roles', title: '', rows }];
}

/** The last day of the month a date falls in, as ISO. */
export function lastDayOfMonth(iso: string): string {
  const year = Number(iso.slice(0, 4));
  const month = Number(iso.slice(5, 7));
  const day = new Date(year, month, 0).getDate();
  return `${iso.slice(0, 7)}-${String(day).padStart(2, '0')}`;
}

/**
 * The state of the staffing in one sentence: everything filled, or which
 * roles are open, how much and from when.
 */
export function staffingSentence(staffing: AssignmentStaffing): string {
  const roles = staffing.roles;
  const open = roles.filter((role) => !role.fully_staffed);
  if (roles.length === 0) return '';
  if (open.length === 0)
    return roles.length === 1 ? 'De rol is ingevuld.' : 'Alle rollen zijn ingevuld.';
  const named = open.map((role) => {
    const gap = (role.gaps ?? [])[0];
    const name = role.description || role.role || 'Rol';
    return gap ? `${name}, ${formatFte(gap.open_fte)} FTE vanaf ${formatMonth(gap.start)}` : name;
  });
  if (roles.length === 1) return `De rol is nog open: ${named[0]}.`;
  const verb = open.length === 1 ? 'is' : 'zijn';
  return `${open.length} van ${roles.length} rollen ${verb} nog open: ${named.join('; ')}.`;
}

/** "Sem Senior zit in oktober 2026 op 140%", one per person who is double booked. */
export function overbookedSignals(
  staffing: AssignmentStaffing,
): { key: string; text: string; personId: string | null }[] {
  return (staffing.overbooked ?? []).map((item) => ({
    key: item.person_id ?? item.month,
    // A whole percentage: the signal is that it is over, not by how many tenths.
    text: `${item.person_name ?? 'Iemand'} zit in ${formatMonth(item.month)} op ${Math.round(Number(item.pct))}%`,
    personId: item.person_id ?? null,
  }));
}

/** The kinds of mark that actually occur in the rows, for the legend. */
export function legendOf(
  groups: TimelineGroup<RoleStaffing, RoleBarData>[],
): ('demand' | 'filled' | 'established' | 'tentative' | 'open' | 'over' | 'mismatch')[] {
  const rows = groups.flatMap((group) => group.rows);
  const bars = rows.flatMap((row) => row.bars);
  const has = {
    demand: bars.some((bar) => bar.variant === 'demand'),
    filled: bars.some((bar) => bar.variant === 'filled'),
    established: bars.some((bar) => bar.closedSpan > 0),
    tentative: bars.some((bar) => bar.variant === 'tentative'),
    open: bars.some((bar) => bar.variant === 'open'),
    over: rows.some((row) => row.cells.some((cell) => cell.state === 'over')),
    mismatch: bars.some((bar) => bar.mark === 'mismatch'),
  };
  return (Object.keys(has) as (keyof typeof has)[]).filter((kind) => has[kind]);
}
