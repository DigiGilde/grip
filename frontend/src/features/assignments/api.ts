/**
 * The assignment endpoints. Fields of a data class the person may not see
 * are absent from a response, not null, so most fields are optional here.
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import type { Phase } from './labels';

export interface AssignmentSummary {
  id: string;
  uri: string;
  name: string;
  kind: string;
  status: string;
  /** potential, active or closed; derived from the status. */
  phase: Phase;
  /** The day the assignment got its current status. */
  status_since: string | null;
  /** When it was shared with the grip instance of the client; null when not. */
  shared_with_client_at?: string | null;
  client_organisation_id: string | null;
  client_name: string | null;
  start_date: string | null;
  end_date: string | null;
  owner_name: string | null;
  quoted_amount_cents?: number | null;
  /** Latest quote, or the budget without one; only for a potential assignment. */
  pipeline_amount_cents?: number | null;
  pipeline_amount_source?: 'quote' | 'budget' | null;
}

export interface AssignmentList {
  items: AssignmentSummary[];
  can_create: boolean;
}

export interface RoleHolder {
  person_id: string;
  name: string;
  role: string;
}

export interface AssignmentPermissions {
  edit_basic: boolean;
  edit_financial: boolean;
  edit_staffing: boolean;
  read_financial: boolean;
  read_staffing: boolean;
  /** Who is on the team, by name: what a team member may see. */
  read_roster: boolean;
}

export interface AssignmentDetail extends AssignmentSummary {
  contractor_organisation_id: string | null;
  contractor_name: string | null;
  parent_assignment_uri: string | null;
  context_refs: string[];
  client_contact: string | null;
  quote_date: string | null;
  notes: string | null;
  /** What was agreed verbally and when; null without a verbal agreement. */
  verbal_agreement_note?: string | null;
  verbal_agreement_at?: string | null;
  roles: RoleHolder[];
  allowed_transitions: string[];
  permissions: AssignmentPermissions;
}

export interface AssignmentInput {
  name?: string;
  kind?: string;
  client_organisation_id?: string | null;
  client_contact?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  notes?: string | null;
  context_refs?: string[];
  quoted_amount_cents?: number | null;
}

export interface Organisation {
  id: string;
  name: string;
  tooi_uri: string | null;
}

export interface PersonOption {
  id: string;
  name: string;
}

export interface BudgetLine {
  id: string;
  assignment_id: string;
  description: string;
  kind: string;
  position: number;
  role?: string | null;
  fte?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  rate_category?: string | null;
  amount_cents?: number | null;
  year?: number | null;
  budgeted_cents?: number | null;
  budgeted_by_year?: Record<string, number>;
  pricing_error?: string | null;
}

export interface Budget {
  assignment_id: string;
  assignment_name: string;
  can_edit: boolean;
  lines: BudgetLine[];
  subtotals_by_year?: Record<string, number>;
  total_budgeted_cents?: number | null;
  quoted_amount_cents?: number | null;
  pricing_error?: string | null;
}

export interface BudgetLineInput {
  description?: string;
  kind?: string;
  role?: string | null;
  fte?: string | null;
  rate_category?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  amount_cents?: number | null;
  year?: number | null;
}

export const assignmentKeys = {
  all: ['assignments'] as const,
  list: () => ['assignments', 'list'] as const,
  detail: (id: string) => ['assignments', 'detail', id] as const,
  budget: (id: string) => ['assignments', 'budget', id] as const,
  organisations: ['organisations'] as const,
  personOptions: ['person-options'] as const,
};

export const fetchAssignments = () => apiGet<AssignmentList>('/api/assignments');

export const fetchAssignment = (id: string) => apiGet<AssignmentDetail>(`/api/assignments/${id}`);

export const createAssignment = (input: AssignmentInput) =>
  apiPost<AssignmentDetail>('/api/assignments', input);

export const updateAssignment = (id: string, input: AssignmentInput) =>
  apiPatch<AssignmentDetail>(`/api/assignments/${id}`, input);

/** `reason` is the note of a verbal agreement, required for that step. */
export const transitionAssignment = (id: string, target: string, reason?: string) =>
  apiPost<AssignmentDetail>(`/api/assignments/${id}/transition`, {
    target,
    ...(reason ? { reason } : {}),
  });

export const setAssignmentRole = (id: string, personId: string, role: string) =>
  apiPut<AssignmentDetail>(`/api/assignments/${id}/roles/${personId}`, { role });

export const removeAssignmentRole = (id: string, personId: string) =>
  apiDelete<AssignmentDetail | { removed: true }>(`/api/assignments/${id}/roles/${personId}`);

export const fetchOrganisations = () =>
  apiGet<{ items: Organisation[] }>('/api/organisations').then((body) => body.items);

export const createOrganisation = (name: string) =>
  apiPost<Organisation>('/api/organisations', { name });

export const fetchPersonOptions = () =>
  apiGet<{ items: PersonOption[] }>('/api/person-options').then((body) => body.items);

export const fetchBudget = (id: string) => apiGet<Budget>(`/api/assignments/${id}/budget`);

export const addBudgetLine = (id: string, input: BudgetLineInput) =>
  apiPost<Budget>(`/api/assignments/${id}/budget-lines`, input);

export const updateBudgetLine = (lineId: string, input: BudgetLineInput) =>
  apiPatch<Budget>(`/api/budget-lines/${lineId}`, input);

export const deleteBudgetLine = (lineId: string) =>
  apiDelete<Budget>(`/api/budget-lines/${lineId}`);
