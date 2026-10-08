import { apiGet, apiPost } from '@/api/client';

export type OrganisationSource = 'registry' | 'manual';

export interface Organisation {
  id: string;
  /** The name as the source gives it. */
  name: string;
  /** The name to show: "Ministerie van ..." for a ministry. */
  label: string;
  abbreviation: string | null;
  abbreviations: string[];
  organisation_types: string[];
  main_type: string | null;
  source: OrganisationSource;
  parent_id: string | null;
  /** Labels from the top of the hierarchy down to the organisation itself. */
  path: string[];
  path_label: string;
  tooi_uri: string | null;
  unit_key: string | null;
  instance_uri: string | null;
  source_url: string | null;
  end_date: string | null;
}

export interface OrganisationPage {
  items: Organisation[];
  total: number;
  page: number;
  page_size: number;
}

export interface OrganisationSearch {
  q?: string;
  type?: string;
  source?: OrganisationSource;
  page?: number;
  page_size?: number;
}

export interface SyncRun {
  id: string;
  started_at: string;
  finished_at: string;
  status: 'completed' | 'failed';
  source_url: string;
  result: Record<string, number>;
  error: string | null;
}

export interface SyncStatus {
  running: boolean;
  running_since: string | null;
  last_run: SyncRun | null;
  registry_organisations: number;
  manual_organisations: number;
}

export const organisationKeys = {
  all: ['organisations'] as const,
  search: (search: OrganisationSearch) => ['organisations', 'search', search] as const,
  one: (id: string) => ['organisations', 'one', id] as const,
  sync: ['organisations', 'sync'] as const,
};

export function searchOrganisations(search: OrganisationSearch): Promise<OrganisationPage> {
  const params: Record<string, string | number> = {};
  if (search.q) params.q = search.q;
  if (search.type) params.type = search.type;
  if (search.source) params.source = search.source;
  if (search.page) params.page = search.page;
  if (search.page_size) params.page_size = search.page_size;
  return apiGet<OrganisationPage>('/api/organisations', params);
}

export function fetchOrganisation(id: string): Promise<Organisation> {
  return apiGet<Organisation>(`/api/organisations/${id}`);
}

/** Adds a party the register does not hold, or a unit below one it does. */
export function createOrganisation(body: {
  name: string;
  parent_id?: string | null;
}): Promise<Organisation> {
  return apiPost<Organisation>('/api/organisations', body);
}

export function fetchSyncStatus(): Promise<SyncStatus> {
  return apiGet<SyncStatus>('/api/organisations/sync');
}

/** Starts the sync with the public register; it continues in the background. */
export function startSync(): Promise<SyncStatus> {
  return apiPost<SyncStatus>('/api/organisations/sync');
}
