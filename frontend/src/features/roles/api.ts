import { apiGet, apiPatch, apiPost } from '@/api/client';

export interface CatalogueRole {
  id: string;
  name: string;
  description: string | null;
  source: 'wies' | 'manual';
  is_active: boolean;
  /** Added on the spot or taken over from free text; the beheerder looks at it. */
  needs_review: boolean;
  /** Budget lines that refer to the role. */
  usage_count: number;
  /** Other names the role goes by in the standard texts; found when searched. */
  also_known_as?: string[];
}

export interface CatalogueRoleList {
  items: CatalogueRole[];
  /** Whether the reader may add a role that is not in the list. */
  can_add: boolean;
  /** Whether the reader may rename, switch off, merge and sync. */
  can_manage: boolean;
}

export interface RoleSyncRun {
  id: string;
  finished_at: string;
  status: 'completed' | 'failed';
  result: Record<string, number>;
  error: string | null;
}

export interface RoleSyncStatus {
  wies_configured: boolean;
  last_run: RoleSyncRun | null;
  roles: number;
  needs_review: number;
}

export interface RoleChanges {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  needs_review?: boolean;
}

export const roleKeys = {
  all: ['catalogue-roles'] as const,
  list: (includeInactive: boolean) => ['catalogue-roles', 'list', includeInactive] as const,
  sync: ['catalogue-roles', 'sync'] as const,
};

/** The whole catalogue; it is small, so searching happens in the browser. */
export function fetchRoles(includeInactive = false): Promise<CatalogueRoleList> {
  return apiGet<CatalogueRoleList>('/api/catalogue-roles', {
    limit: 500,
    ...(includeInactive ? { include_inactive: true } : {}),
  });
}

/** Adds a role. A name that already exists answers with the role that is there. */
export function createRole(body: {
  name: string;
  description?: string | null;
}): Promise<CatalogueRole> {
  return apiPost<CatalogueRole>('/api/catalogue-roles', body);
}

export function updateRole(id: string, changes: RoleChanges): Promise<CatalogueRole> {
  return apiPatch<CatalogueRole>(`/api/catalogue-roles/${id}`, changes);
}

/** Merges `id` into `intoId`: its budget lines move and the role disappears. */
export function mergeRole(
  id: string,
  intoId: string,
): Promise<{ role: CatalogueRole; budget_lines_rewritten: number }> {
  return apiPost(`/api/catalogue-roles/${id}/merge`, { into_id: intoId });
}

export function fetchRoleSync(): Promise<RoleSyncStatus> {
  return apiGet<RoleSyncStatus>('/api/catalogue-roles/sync');
}

export function runRoleSync(): Promise<RoleSyncStatus> {
  return apiPost<RoleSyncStatus>('/api/catalogue-roles/sync');
}
