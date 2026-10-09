/**
 * The assignment endpoints. Fields of a data class the person may not see
 * are absent from a response, not null, so most fields are optional here.
 */
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { ifMatch } from '@/ui/stale';
import type { Phase } from './labels';

export interface AssignmentSummary {
  id: string;
  /** Counts the changes of the assignment; sent back with a save. */
  version?: number;
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
  /** May assign owner and managers, also without any other edit right. */
  manage_roles?: boolean;
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
  /** How the reader relates to the assignment: owner, manager, member. */
  viewer_relations?: string[];
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
  /** Set for a colleague who is hired but has not started yet. */
  starts_on?: string | null;
}

export interface BudgetLine {
  id: string;
  /** Counts the changes of the line; sent back with a save. */
  version?: number;
  assignment_id: string;
  description: string;
  /** The free text that tells the line apart; the form edits this. */
  detail?: string;
  /** 'assignment' when the line follows the assignment, 'own' when it deviates. */
  period_source?: string;
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
  /** Why the line runs over or under, naming the person: only for who may see that. */
  rate_difference_notes?: string[];
  /** The same without the person: "tariefwijziging per 1 juli 2026". */
  rate_difference_signals?: string[];
  /** The colleague the role is meant for. Never part of a quote. */
  intended_person_id?: string | null;
  intended_person_name?: string | null;
  /** The reservation still follows the line (period and size). */
  intended_in_step?: boolean | null;
  intended_tentative?: boolean | null;
  intended_notes?: string[];
  /** The person bills in another category than the line assumes. */
  intended_category_differs?: boolean | null;
  intended_category?: string | null;
  intended_category_notes?: string[];
}

export interface Budget {
  assignment_id: string;
  assignment_name: string;
  can_edit: boolean;
  /** Lines wait for the assignment to get a period; the message says what to do. */
  period_missing?: boolean;
  period_message?: string | null;
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
  /** 'assignment' follows the assignment; 'own' has its own two dates. */
  period_source?: 'assignment' | 'own';
  start_date?: string | null;
  end_date?: string | null;
  amount_cents?: number | null;
  year?: number | null;
  /** A person names or replaces the intended person; null removes it. */
  intended_person_id?: string | null;
}

/**
 * What follows from an intended person: proposals, each with its source in
 * words. Nothing is saved by asking.
 */
export interface Derivation {
  intended_person_id: string;
  /** Sentences in plain Dutch, built by the server. */
  summary?: string[];
  role?: string | null;
  role_source_text?: string | null;
  /** More than one role is known for the person: the user picks. */
  role_alternatives?: { role: string }[];
  start_date: string | null;
  end_date: string | null;
  /** The period is a proposal and was not sent by the form. */
  period_proposed: boolean;
  period_source_text?: string | null;
  /** The room the person has over the period. */
  fte?: string | null;
  fte_source_text?: string | null;
  /** Absent for a reader who may not see what a person bills. */
  rate_summary?: string | null;
  rate_category?: string | null;
  monthly_rates?: { year: number; monthly_rate_cents: number }[];
  budgeted_cents?: number | null;
}

export interface LinePreview {
  budgeted_cents: number | null;
  budgeted_by_year: Record<string, number>;
  reason: string | null;
}

export const assignmentKeys = {
  all: ['assignments'] as const,
  list: () => ['assignments', 'list'] as const,
  detail: (id: string) => ['assignments', 'detail', id] as const,
  budget: (id: string) => ['assignments', 'budget', id] as const,
  organisations: ['organisations'] as const,
  personOptions: ['person-options'] as const,
  judgeOptions: ['person-options', 'judging'] as const,
};

export const fetchAssignments = () => apiGet<AssignmentList>('/api/assignments');

export const fetchAssignment = (id: string) => apiGet<AssignmentDetail>(`/api/assignments/${id}`);

export const createAssignment = (input: AssignmentInput) =>
  apiPost<AssignmentDetail>('/api/assignments', input);

/** `version` is the version of the assignment the form started from. */
export const updateAssignment = (id: string, input: AssignmentInput, version?: number) =>
  apiPatch<AssignmentDetail>(`/api/assignments/${id}`, input, ifMatch(id, version));

/** `reason` is the note of a verbal agreement, required for that step. */
export const transitionAssignment = (id: string, target: string, reason?: string) =>
  apiPost<AssignmentDetail>(`/api/assignments/${id}/transition`, {
    target,
    ...(reason ? { reason } : {}),
  });

export const setAssignmentRole = (id: string, personId: string, role: string, version?: number) =>
  apiPut<AssignmentDetail>(
    `/api/assignments/${id}/roles/${personId}`,
    { role },
    ifMatch(id, version),
  );

export const removeAssignmentRole = (id: string, personId: string) =>
  apiDelete<AssignmentDetail | { removed: true }>(`/api/assignments/${id}/roles/${personId}`);

export const fetchOrganisations = () =>
  apiGet<{ items: Organisation[] }>('/api/organisations').then((body) => body.items);

export const createOrganisation = (name: string) =>
  apiPost<Organisation>('/api/organisations', { name });

export const fetchPersonOptions = () =>
  apiGet<{ items: PersonOption[] }>('/api/person-options').then((body) => body.items);

/** Who can be asked to advise, approve or review something internal. */
export const fetchJudgeOptions = () =>
  apiGet<{ items: PersonOption[] }>('/api/person-options?oordeel=true').then((body) => body.items);

export const fetchBudget = (id: string) => apiGet<Budget>(`/api/assignments/${id}/budget`);

export const addBudgetLine = (id: string, input: BudgetLineInput) =>
  apiPost<Budget>(`/api/assignments/${id}/budget-lines`, input);

/** `version` is the version of the line the form started from. */
export const updateBudgetLine = (lineId: string, input: BudgetLineInput, version?: number) =>
  apiPatch<Budget>(`/api/budget-lines/${lineId}`, input, ifMatch(lineId, version));

export const deleteBudgetLine = (lineId: string) =>
  apiDelete<Budget>(`/api/budget-lines/${lineId}`);

export const deriveBudgetLine = (
  id: string,
  body: { intended_person_id: string; start_date?: string; end_date?: string; fte?: string },
) => apiPost<Derivation>(`/api/assignments/${id}/budget-lines/derive`, body);

/** What a line with these values would be budgeted at; the server computes it. */
export const previewBudgetLine = (id: string, body: BudgetLineInput) =>
  apiPost<LinePreview>(`/api/assignments/${id}/budget-lines/preview`, body);
