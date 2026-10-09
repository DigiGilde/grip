/**
 * The inzet endpoints. A row carries only the fields the person may see:
 * a team member gets names, a planner gets time and the mismatch signal,
 * a manager also gets amounts and categories.
 */
import { apiDelete, apiGet, apiPatch, apiPost } from '@/api/client';

export interface Allocation {
  id: string;
  person_id: string;
  person_name: string;
  assignment_id?: string;
  assignment_name?: string;
  budget_line_id?: string;
  budget_line_description?: string;
  role?: string | null;
  /** On an assignment that is still potential: this inzet may not happen. */
  tentative?: boolean;
  /** 'line' when the inzet follows its budget line, 'own' when it deviates. */
  period_source?: 'line' | 'own';
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
  can_edit?: boolean;
  amount_cents?: number | null;
  pricing_error?: string | null;
  line_category?: string | null;
  person_category?: string | null;
  mismatch_direction?: string | null;
  category_mismatch?: boolean;
}

export interface AllocationList {
  items: Allocation[];
  can_add: boolean;
}

export interface PersonChoice {
  id: string;
  name: string;
}

export interface LineChoice {
  budget_line_id: string;
  assignment_id: string;
  assignment_name: string;
  description: string;
  role?: string | null;
  fte?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface AllocationOptions {
  people: PersonChoice[];
  lines: LineChoice[];
}

export interface AllocationInput {
  budget_line_id?: string;
  person_id?: string;
  /** 'line' when the inzet follows its budget line, 'own' when it deviates. */
  period_source?: 'line' | 'own';
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
}

export const allocationKeys = {
  all: ['allocations'] as const,
  list: (year: string) => ['allocations', 'list', year] as const,
  options: ['allocations', 'options'] as const,
  /** The options for the form on the page of one assignment. */
  optionsOf: (assignmentId: string) => ['allocations', 'options', assignmentId] as const,
};

export const fetchAllocations = (year: string) =>
  apiGet<AllocationList>('/api/allocations', { year });

export const fetchAllocationOptions = () => apiGet<AllocationOptions>('/api/allocations/options');

/** The same for the form on the page of one assignment: only that assignment's lines. */
export const fetchAllocationOptionsOf = (assignmentId: string) =>
  apiGet<AllocationOptions>('/api/allocations/options', { assignment_id: assignmentId });

export const addAllocation = (input: AllocationInput) =>
  apiPost<Allocation>('/api/allocations', input);

export const updateAllocation = (id: string, input: AllocationInput) =>
  apiPatch<Allocation>(`/api/allocations/${id}`, input);

export const deleteAllocation = (id: string) => apiDelete(`/api/allocations/${id}`);

/** A month in which the person would be above 100 percent, with this inzet. */
export interface OverMonth {
  /** First day of the month. */
  month: string;
  current_pct: string;
  new_pct: string;
}

export interface AllocationLoad {
  person_name: string;
  over_months: OverMonth[];
}

/** What the inzet would do to the person's load; nothing is saved by asking. */
export const previewAllocationLoad = (input: AllocationInput & { allocation_id?: string }) =>
  apiPost<AllocationLoad>('/api/allocations/load-preview', input);
