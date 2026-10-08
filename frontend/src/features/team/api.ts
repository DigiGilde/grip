import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { formatDate } from '@/lib/format';
import type { PriceImpact } from '@/features/rates/api';

/**
 * A person as the asker may see them. Every group of fields below is present
 * only when the asker may see it: a field that is hidden is absent, not null.
 */
export interface Person {
  id: string;
  name: string;
  /** Null for a prospective colleague: the address comes later, from Wies. */
  email: string | null;
  is_active: boolean;
  manager_id: string | null;
  manager_name: string | null;
  /** prospective: hired and planned, not started yet. */
  stage?: 'prospective' | 'colleague' | 'left';
  starts_on?: string | null;
  can_log_in?: boolean;

  functions?: string[];
  /** The rights in grip held today, with since when and who granted each. */
  function_grants?: FunctionGrant[];
  /** The only active beheerder: that right cannot be revoked. */
  is_sole_beheerder?: boolean;
  is_hired?: boolean;
  /** Staffing on the reference day. */
  current_assignment_count?: number;
  current_fte_pct?: string;

  billing_scale?: number | null;
  rate_category?: string | null;
  monthly_rate_cents?: number | null;
  scales?: Scale[];

  cost_monthly_rate_cents?: number | null;
  margin_monthly_cents?: number | null;
  hires?: Hire[];
}

export interface Scale {
  id: string;
  valid_from: string;
  valid_to: string | null;
  billing_scale: number;
}

/**
 * A period in which someone is hired. From whom and until when is part of how
 * someone is engaged; the cost is present only for who may see it.
 */
export interface Hire {
  id?: string;
  supplier?: string;
  valid_from?: string;
  valid_to?: string | null;
  contract_reference?: string | null;
  cost_monthly_rate_cents?: number;
  notes?: string | null;
}

export interface FunctionGrant {
  function: string;
  since: string;
  /** Null when the system granted it at the set-up of the instance. */
  granted_by_name: string | null;
}

export interface PersonList {
  items: Person[];
  may_manage: boolean;
  period_start: string;
  period_end: string;
}

export interface Kpi {
  person_id: string;
  person_name: string;
  year: number;
  target_pct: string | null;
  target_cents: number | null;
  realised_cents: number | null;
  forecast_cents: number | null;
  realisation_cents: number | null;
  unavailable_reason: string | null;
}

export interface KpiList {
  items: Kpi[];
  year: number;
  may_manage: boolean;
}

/**
 * The rights in grip a person can hold. In code and in the API they are
 * called functions; on screen "recht", because "functie" already means
 * someone's job. `farReaching` marks the two that are confirmed before they
 * are granted.
 */
export const FUNCTIONS = [
  {
    id: 'beheerder',
    label: 'Beheerder',
    description: 'Beheert tarieven, personen en wie welk recht heeft; mag gesloten jaren wijzigen',
    farReaching: true,
  },
  {
    id: 'planner',
    label: 'Planner',
    description: 'Plant inzet over alle opdrachten, zonder bedragen te zien',
    farReaching: false,
  },
  {
    id: 'lezer',
    label: 'Lezer',
    description: 'Leest alle opdrachten met hun bedragen',
    farReaching: false,
  },
  {
    id: 'aanvrager',
    label: 'Aanvrager',
    description: 'Vraagt als opdrachtgever een offerte aan bij een andere instantie',
    farReaching: false,
  },
  {
    id: 'tekenbevoegde',
    label: 'Tekenbevoegde',
    description: 'Tekent offertes namens de organisatie en bindt haar daarmee',
    farReaching: true,
  },
  {
    id: 'offertegoedkeurder',
    label: 'Interne goedkeurder van offertes',
    description:
      'Keurt een gemaakte offerte intern goed of stuurt haar terug, voordat zij naar de opdrachtgever gaat',
    farReaching: false,
  },
] as const;

export function functionLabel(id: string): string {
  return FUNCTIONS.find((f) => f.id === id)?.label ?? id;
}

export const peopleKey = (day: string, includeInactive: boolean) =>
  ['team', 'people', day, includeInactive] as const;
export const kpiKey = (year: number) => ['team', 'kpi', year] as const;
export const personKey = (id: string, day: string) => ['team', 'person', id, day] as const;
export const personKpiKey = (id: string, year: number) => ['team', 'kpi', year, id] as const;

/** One person as the asker may see them; 404 when the asker may see nothing. */
export function fetchPerson(id: string, day: string): Promise<Person> {
  return apiGet<Person>(`/api/people/${id}`, { period_start: day, period_end: day });
}

/** The KPI of one person; 404 when the asker may not see it. */
export function fetchPersonKpi(id: string, year: number): Promise<Kpi> {
  return apiGet<Kpi>(`/api/kpi/${id}`, { year });
}

/** The day decides which scale, rate and hire are shown, and who counts as staffed. */
export function fetchPeople(day: string, includeInactive: boolean): Promise<PersonList> {
  return apiGet<PersonList>('/api/people', {
    period_start: day,
    period_end: day,
    include_inactive: includeInactive || undefined,
  });
}

export function createPerson(body: {
  name: string;
  /** Leave out for a prospective colleague; start_date is then required. */
  email?: string;
  manager_id: string | null;
  start_date?: string;
  suborganization?: string;
}): Promise<Person> {
  return apiPost<Person>('/api/people', body);
}

export function updatePerson(
  id: string,
  body: Partial<{ name: string; email: string; manager_id: string | null; is_active: boolean }>,
): Promise<Person> {
  return apiPatch<Person>(`/api/people/${id}`, body);
}

export function addScale(
  id: string,
  body: { valid_from: string; billing_scale: number },
): Promise<Person> {
  return apiPost<Person>(`/api/people/${id}/scales`, body);
}

export function addHire(
  id: string,
  body: {
    supplier: string;
    cost_monthly_rate_cents: number;
    valid_from: string;
    valid_to: string | null;
    contract_reference: string | null;
  },
): Promise<Person> {
  return apiPost<Person>(`/api/people/${id}/hires`, body);
}

export function removeHire(id: string, hireId: string): Promise<void> {
  return apiDelete(`/api/people/${id}/hires/${hireId}`);
}

/** Whether the person's login is bound to an account of the identity provider. */
export const loginKey = (id: string) => ['team', 'login', id] as const;

export function fetchLoginState(id: string): Promise<{ bound: boolean }> {
  return apiGet<{ bound: boolean }>(`/api/people/${id}/login`);
}

/** Forget the binding, so the next login with the verified email binds again. */
export function unbindLogin(id: string): Promise<{ bound: boolean }> {
  return apiDelete<{ bound: boolean }>(`/api/people/${id}/login`);
}

export function setFunction(id: string, fn: string, held: boolean): Promise<Person> {
  const path = `/api/people/${id}/functions/${fn}`;
  return held ? apiPut<Person>(path) : apiDelete<Person>(path);
}

export function fetchKpi(year: number): Promise<KpiList> {
  return apiGet<KpiList>('/api/kpi', { year });
}

export function setKpiTarget(personId: string, year: number, targetPct: string): Promise<Kpi> {
  return apiPut<Kpi>(`/api/kpi/${personId}/${year}`, { target_pct: targetPct });
}

/** Today as an ISO date in local time. */
export function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/** What to show under a name: the address, or when someone starts. */
export function personSubtitle(person: Person): string {
  const base =
    person.stage === 'prospective' && person.starts_on
      ? `start op ${formatDate(person.starts_on)}`
      : (person.email ?? 'nog geen e-mailadres');
  return person.is_active ? base : `${base}, inactief`;
}

export type Engagement = 'prospective' | 'left' | 'hired' | 'employed' | 'colleague';

/**
 * How someone is engaged with the organisation: one fact. Whether a colleague
 * is hired or employed is only known to who may see staffing; without it the
 * person is simply a colleague.
 */
export function engagementOf(person: Person): Engagement {
  if (person.stage === 'prospective') return 'prospective';
  if (person.stage === 'left') return 'left';
  if (!('is_hired' in person)) return 'colleague';
  return person.is_hired ? 'hired' : 'employed';
}

export const ENGAGEMENT_LABELS: Record<Engagement, string> = {
  prospective: 'Aanstaande collega',
  left: 'Vertrokken',
  hired: 'Ingehuurd',
  employed: 'In dienst',
  colleague: 'Collega',
};

/** The hire period that runs on the given day, if any. */
export function currentHire(person: Person, day: string): Hire | null {
  const running = (person.hires ?? []).filter(
    (hire) =>
      hire.valid_from !== undefined &&
      hire.valid_from <= day &&
      (hire.valid_to === null || hire.valid_to === undefined || hire.valid_to >= day),
  );
  return running.at(-1) ?? (person.hires ?? []).find((hire) => !hire.valid_from) ?? null;
}

/** What recording a scale from a date would touch. Saves nothing. */
export function previewScale(
  id: string,
  body: { valid_from: string; billing_scale: number },
): Promise<PriceImpact> {
  return apiPost<PriceImpact>(`/api/people/${id}/scales/preview`, body);
}

export const scalePreviewKey = (id: string, from: string, scale: number) =>
  ['team', 'scale-preview', id, from, scale] as const;

/** A role a person can be staffed in, with where the link came from. */
export interface PersonRole {
  role_id: string;
  name: string;
  /** wies: from the person's skills in Wies. manual: set by the beheerder. */
  source: 'wies' | 'manual';
  is_active: boolean;
}

export const personRolesKey = (id: string) => ['team', 'roles', id] as const;

/** The roles of a person; 404 or 403 when the asker may not see their staffing. */
export function fetchPersonRoles(id: string): Promise<{ items: PersonRole[] }> {
  return apiGet<{ items: PersonRole[] }>(`/api/people/${id}/roles`);
}

/** Make the roles of a person exactly this set; what is not listed is taken away. */
export function setPersonRoles(id: string, roleIds: string[]): Promise<{ items: PersonRole[] }> {
  return apiPut<{ items: PersonRole[] }>(`/api/people/${id}/roles`, { role_ids: roleIds });
}

export const ROLE_SOURCE_LABELS: Record<PersonRole['source'], string> = {
  wies: 'Uit Wies',
  manual: 'Met de hand',
};

/** The periods of a billing scale, newest first, each with the scale before it. */
export function scaleHistory(scales: Scale[]): Array<Scale & { previous: number | null }> {
  const ordered = [...scales].sort((a, b) => (a.valid_from < b.valid_from ? -1 : 1));
  return ordered
    .map((entry, index) => ({
      ...entry,
      previous: index > 0 ? (ordered[index - 1]?.billing_scale ?? null) : null,
    }))
    .reverse();
}

/** "Schaal 12 sinds 1 jul 2026 (was 11)": a promotion reads as one. */
export function scaleSentence(entry: Scale & { previous: number | null }): string {
  const was =
    entry.previous !== null && entry.previous !== entry.billing_scale
      ? ` (was ${entry.previous})`
      : '';
  return `Schaal ${entry.billing_scale} sinds ${formatDate(entry.valid_from)}${was}`;
}
