/** The roles of one assignment as rows of the shared timeline. */
import { mismatchText } from '@/features/allocations/board/model';
import { formatDate, formatFte, formatMonth, formatPercent, formatPeriod } from '@/lib/format';
import {
  assignLanes,
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
    text = `! ${formatPercent(month.filled_pct)}`;
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
  if (over.length > 0) parts.push(`meer ingezet dan gevraagd in ${over.map((m) => monthShort(m.month)).join(', ')}`);
  if (role.bars.some((bar) => bar.before_start)) parts.push('inzet voor de startdatum');
  if (role.bars.some((bar) => bar.outside_role_period)) parts.push('inzet buiten de periode van de rol');
  const text = parts.join('; ');
  return text.charAt(0).toUpperCase() + text.slice(1);
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
      while (closedSpan < place.span && closed.has(monthKey(months[place.column + closedSpan] ?? ''))) {
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
        ...(flagged ? { mark: '!' } : bar.category_mismatch ? { mark: '≠' } : {}),
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
        data: {},
      });
    }
    const byMonth = new Map((role.months ?? []).map((month) => [monthKey(month.month), month] as const));
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

/** The answer before the board: how the roles stand, in a few figures. */
export function staffingSummary(staffing: AssignmentStaffing): { label: string; value: string; detail: string; attention: boolean }[] {
  const roles = staffing.role_count ?? staffing.roles.length;
  const staffed = staffing.staffed_count ?? 0;
  const over = staffing.overbooked_count ?? 0;
  return [
    {
      label: 'Rollen',
      value: `${staffed} van ${roles} volledig ingevuld`,
      detail: roles === staffed ? 'Geen open rollen' : `${roles - staffed} ${roles - staffed === 1 ? 'rol heeft' : 'rollen hebben'} ruimte`,
      attention: false,
    },
    {
      label: 'Nog open',
      value: staffing.open_fte ? `${formatFte(staffing.open_fte)} FTE` : 'Niets',
      detail: staffing.open_from ? `vanaf ${formatMonth(staffing.open_from)}` : 'Alles is ingevuld',
      attention: Boolean(staffing.open_fte),
    },
    {
      label: 'Elders dubbel geboekt',
      value: over === 0 ? 'Niemand' : over === 1 ? '1 persoon' : `${over} personen`,
      detail: over === 0 ? '' : 'Boven 100% in een maand waarin ze hier werken',
      attention: over > 0,
    },
  ];
}
