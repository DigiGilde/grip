import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';

/**
 * A person as the asker may see them. Every group of fields below is present
 * only when the asker may see it: a field that is hidden is absent, not null.
 */
export interface Person {
  id: string;
  name: string;
  email: string;
  is_active: boolean;
  manager_id: string | null;
  manager_name: string | null;

  functions?: string[];
  is_hired?: boolean;

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

export interface Hire {
  id: string;
  supplier: string;
  cost_monthly_rate_cents: number;
  valid_from: string;
  valid_to: string | null;
  contract_reference: string | null;
  notes: string | null;
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

export const FUNCTIONS = [
  { id: 'beheerder', label: 'Beheerder', description: 'Beheert tarieven, personen en functies' },
  { id: 'planner', label: 'Planner', description: 'Plant inzet over alle opdrachten' },
  { id: 'lezer', label: 'Lezer', description: 'Leest opdrachten en hun bedragen' },
  { id: 'aanvrager', label: 'Aanvrager', description: 'Vraagt als opdrachtgever een offerte aan' },
  {
    id: 'tekenbevoegde',
    label: 'Tekenbevoegde',
    description: 'Tekent offertes namens de instantie',
  },
] as const;

export function functionLabel(id: string): string {
  return FUNCTIONS.find((f) => f.id === id)?.label ?? id;
}

export const peopleKey = (day: string, includeInactive: boolean) =>
  ['team', 'people', day, includeInactive] as const;
export const kpiKey = (year: number) => ['team', 'kpi', year] as const;

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
  email: string;
  manager_id: string | null;
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
