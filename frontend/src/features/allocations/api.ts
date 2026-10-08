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
  start_date?: string;
  end_date?: string;
  fte_pct?: string;
}

export const allocationKeys = {
  all: ['allocations'] as const,
  list: (year: string) => ['allocations', 'list', year] as const,
  options: ['allocations', 'options'] as const,
};

export const fetchAllocations = (year: string) =>
  apiGet<AllocationList>('/api/allocations', { year });

export const fetchAllocationOptions = () => apiGet<AllocationOptions>('/api/allocations/options');

export const addAllocation = (input: AllocationInput) =>
  apiPost<Allocation>('/api/allocations', input);

export const updateAllocation = (id: string, input: AllocationInput) =>
  apiPatch<Allocation>(`/api/allocations/${id}`, input);

export const deleteAllocation = (id: string) => apiDelete(`/api/allocations/${id}`);
