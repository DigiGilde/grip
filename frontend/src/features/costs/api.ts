import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';

export interface InvoiceLine {
  id: string;
  reference: string | null;
  description: string | null;
  kind: 'actual' | 'estimate';
  amount_cents: number;
  period: string | null;
}

export interface Coverage {
  budget_line_id: string;
  budget_line_description: string;
  assignment_id: string;
  assignment_name: string;
  pct: string;
  amount_cents: number;
  may_edit: boolean;
}

export interface CostItem {
  id: string;
  description: string;
  budgeted_cents: number;
  forecast_cents: number;
  actual_cents: number;
  estimate_cents: number;
  /** Null when the stored percentages add up to more than 100. */
  covered_cents: number | null;
  uncovered_cents: number | null;
  pct_total: string;
  /** Share covered by assignments the asker may not see. */
  hidden_coverage_pct: string;
  invoice_lines: InvoiceLine[];
  coverages: Coverage[];
  may_edit: boolean;
}

export interface CostItemList {
  items: CostItem[];
  year: number | null;
  may_create: boolean;
}

export interface BudgetLineOption {
  budget_line_id: string;
  description: string;
  kind: string;
  assignment_id: string;
  assignment_name: string;
}

export const costsKey = (year: number | null) => ['costs', 'items', year] as const;
export const COVERAGE_OPTIONS_KEY = ['costs', 'coverage-options'] as const;

export function fetchCostItems(year: number | null): Promise<CostItemList> {
  return apiGet<CostItemList>('/api/costs', { year });
}

export function fetchCoverageOptions(): Promise<{ items: BudgetLineOption[] }> {
  return apiGet<{ items: BudgetLineOption[] }>('/api/costs/coverage-options');
}

export function createCostItem(body: {
  description: string;
  budgeted_cents: number;
}): Promise<CostItem> {
  return apiPost<CostItem>('/api/costs', body);
}

export function updateCostItem(
  id: string,
  body: { description: string; budgeted_cents: number },
): Promise<CostItem> {
  return apiPatch<CostItem>(`/api/costs/${id}`, body);
}

export function addInvoiceLine(
  id: string,
  body: {
    kind: 'actual' | 'estimate';
    amount_cents: number;
    reference: string | null;
    description: string | null;
    period: string | null;
  },
): Promise<CostItem> {
  return apiPost<CostItem>(`/api/costs/${id}/invoice-lines`, body);
}

export function deleteInvoiceLine(id: string, lineId: string): Promise<CostItem> {
  return apiDelete<CostItem>(`/api/costs/${id}/invoice-lines/${lineId}`);
}

export function setCoverage(id: string, budgetLineId: string, pct: string): Promise<CostItem> {
  return apiPut<CostItem>(`/api/costs/${id}/coverage/${budgetLineId}`, { pct });
}

export function removeCoverage(id: string, budgetLineId: string): Promise<void> {
  return apiDelete(`/api/costs/${id}/coverage/${budgetLineId}`);
}

export const KIND_LABELS: Record<InvoiceLine['kind'], string> = {
  actual: 'Realisatie',
  estimate: 'Inschatting',
};
