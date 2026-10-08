/**
 * What the person page says in words, as pure functions of what the server
 * returned. Nothing here adds or subtracts amounts: a figure the page shows
 * was computed by the server.
 */
import { formatDate, formatMonth, formatPercent } from '@/lib/format';
import type { BoardPerson } from '@/features/allocations/board/api';
import { monthShort } from '@/ui/timeline/layout';
import {
  ENGAGEMENT_LABELS,
  currentHire,
  engagementOf,
  type Kpi,
  type Person,
  type PersonRole,
} from './api';

/** How someone is engaged, as the one label next to the name. */
export function engagementLabel(person: Person, day: string): string {
  const label = ENGAGEMENT_LABELS[engagementOf(person)];
  const hire = currentHire(person, day);
  if (person.stage === 'prospective') {
    return person.starts_on ? `${label}, start op ${formatDate(person.starts_on)}` : label;
  }
  return hire?.supplier ? `${label} via ${hire.supplier}` : label;
}

/** The quiet facts under the name: roles, scale, address. The manager is a link beside them. */
export function identityFacts(person: Person, roles: PersonRole[] | null): string[] {
  const facts: string[] = [];
  const active = (roles ?? []).filter((role) => role.is_active).map((role) => role.name);
  if (active.length > 0) facts.push(active.join(', '));
  if (typeof person.billing_scale === 'number') facts.push(`Schaal ${person.billing_scale}`);
  if (person.email) facts.push(person.email);
  return facts;
}

export interface Deployment {
  /** "Nu 100% op 2 opdrachten". */
  now: string;
  /** Where the work ends or frees up; empty when there is nothing to say. */
  ahead: string;
  /** Needs attention: above 100 percent, or no work from a month on. */
  attention: string;
}

/** Where someone stands, from the board row and the staffing of the day. */
export function deploymentOf(person: Person, row: BoardPerson | null): Deployment {
  const count = person.current_assignment_count ?? 0;
  const pct = row?.now_pct ?? person.current_fte_pct ?? null;
  const now =
    count === 0
      ? 'Nu niet ingezet'
      : `Nu ${formatPercent(pct)} op ${count === 1 ? '1 opdracht' : `${count} opdrachten`}`;
  const firm = (row?.bars ?? []).filter((bar) => !bar.tentative);
  const lastEnd = firm
    .map((bar) => bar.end_date)
    .sort()
    .at(-1);
  const over = row?.over_months ?? [];
  const attention = [
    over.length > 0 ? `Boven 100% in ${over.map((month) => monthShort(month)).join(', ')}` : '',
    row?.idle_from && count > 0 ? `Geen inzet vanaf ${formatMonth(row.idle_from)}` : '',
  ]
    .filter(Boolean)
    .join('. ');
  // The end of the work is what to act on; room before that comes second.
  const ahead = [
    lastEnd ? `Laatste inzet eindigt op ${formatDate(lastEnd)}` : '',
    row?.room_from && !row.idle_from ? `ruimte vanaf ${formatMonth(row.room_from)}` : '',
  ]
    .filter(Boolean)
    .join(', ');
  return { now, ahead, attention };
}

export type KpiStanding = 'none' | 'on-track' | 'below';

/** Whether the expected total reaches the target. A comparison, not a sum. */
export function kpiStanding(kpi: Kpi): KpiStanding {
  if (kpi.target_cents === null || kpi.realisation_cents === null) return 'none';
  return kpi.realisation_cents >= kpi.target_cents ? 'on-track' : 'below';
}

export const KPI_STANDING_TEXT: Record<Exclude<KpiStanding, 'none'>, string> = {
  'on-track': 'Haalt het target',
  below: 'Blijft onder het target',
};

/**
 * What can change about a person, named as the event it is. The page offers
 * these in one menu; each opens the sheet that records it.
 */
export type PersonEvent =
  | 'scale'
  | 'manager'
  | 'hire'
  | 'roles'
  | 'target'
  | 'identity'
  | 'grant'
  | 'unbind'
  | 'leave'
  | 'return';

export interface EventItem {
  event: PersonEvent;
  text: string;
  destructive?: boolean;
}

export interface EventGroup {
  title: string;
  items: EventItem[];
}

interface EventContext {
  person: Person;
  day: string;
  year: number;
  /** A right is left to grant. */
  canGrant: boolean;
  /** The login is bound to an account. */
  loginBound: boolean;
}

export function eventGroups({
  person,
  day,
  year,
  canGrant,
  loginBound,
}: EventContext): EventGroup[] {
  const prospective = person.stage === 'prospective';
  const hired = currentHire(person, day) !== null;
  const work: EventItem[] = [
    { event: 'scale', text: 'Promotie of andere schaal' },
    { event: 'manager', text: 'Andere leidinggevende' },
    { event: 'roles', text: 'Andere rollen' },
    ...(prospective
      ? []
      : [
          {
            event: 'hire' as const,
            text: hired ? 'Nieuwe inhuurperiode' : 'Wordt ingehuurd',
          },
        ]),
    { event: 'target', text: `Target declarabel ${year}` },
  ];
  const access: EventItem[] = [
    ...(canGrant ? [{ event: 'grant' as const, text: 'Krijgt een recht in grip' }] : []),
    ...(loginBound ? [{ event: 'unbind' as const, text: 'Ontkoppel de login' }] : []),
  ];
  const record: EventItem[] = [
    { event: 'identity', text: 'Naam of e-mailadres' },
    ...(person.is_sole_beheerder
      ? []
      : person.is_active
        ? [
            {
              event: 'leave' as const,
              text: 'Vertrekt of wordt inactief',
              destructive: true,
            },
          ]
        : [{ event: 'return' as const, text: 'Wordt weer actief' }]),
  ];
  return [
    { title: 'Werk', items: work },
    ...(access.length > 0 ? [{ title: 'Toegang', items: access }] : []),
    { title: 'Gegevens', items: record },
  ];
}
