import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { formatDate } from '@/lib/format';

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
