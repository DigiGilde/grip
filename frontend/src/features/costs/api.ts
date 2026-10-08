import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  getCsrfToken,
  type ProblemDetails,
} from '@/api/client';

/** A document attached to an invoice line: the received invoice itself. */
export interface Attachment {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: string;
  uploaded_by_name: string | null;
}

export interface InvoiceLine {
  id: string;
  reference: string | null;
  description: string | null;
  kind: 'actual' | 'estimate';
  amount_cents: number;
  period: string | null;
  attachments: Attachment[];
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
  /** Budgeted minus the expected total; negative means over budget. */
  variance_cents: number;
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

export interface InvoiceLineInput {
  kind: 'actual' | 'estimate';
  amount_cents: number;
  reference: string | null;
  description: string | null;
  period: string | null;
}

/** The cost item after the change, with the id of the line that was made. */
export function addInvoiceLine(
  id: string,
  body: InvoiceLineInput,
): Promise<CostItem & { created_invoice_line_id: string }> {
  return apiPost(`/api/costs/${id}/invoice-lines`, body);
}

export function updateInvoiceLine(
  id: string,
  lineId: string,
  body: InvoiceLineInput,
): Promise<CostItem> {
  return apiPatch<CostItem>(`/api/costs/${id}/invoice-lines/${lineId}`, body);
}

/** Deletes the line and every file attached to it. */
export function deleteInvoiceLine(id: string, lineId: string): Promise<CostItem> {
  return apiDelete<CostItem>(`/api/costs/${id}/invoice-lines/${lineId}`);
}

/** What the server accepts as an invoice: pdf, a scan or photo, or an e-invoice. */
export const ATTACHMENT_ACCEPT = '.pdf,.png,.jpg,.jpeg,.xml,application/pdf,image/png,image/jpeg';
export const ATTACHMENT_HELP =
  'Pdf, scan of foto (png of jpg) of e-factuur (xml); hoogstens 10 MB per bestand';

const attachmentsPath = (id: string, lineId: string) =>
  `/api/costs/${id}/invoice-lines/${lineId}/attachments`;

/** Where the file itself is; the server answers with a download, never a page. */
export function attachmentUrl(id: string, lineId: string, attachmentId: string): string {
  return `${attachmentsPath(id, lineId)}/${attachmentId}`;
}

/** Upload one file to an invoice line. A file goes as multipart, not as JSON. */
export async function uploadAttachment(id: string, lineId: string, file: File): Promise<CostItem> {
  const body = new FormData();
  body.append('file', file, file.name);
  const response = await fetch(attachmentsPath(id, lineId), {
    method: 'POST',
    headers: {
      Accept: 'application/json, application/problem+json',
      'X-CSRF-Token': getCsrfToken(),
    },
    credentials: 'same-origin',
    body,
  });
  const text = await response.text();
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = text;
  }
  if (!response.ok) {
    const problem =
      typeof parsed === 'object' && parsed !== null ? (parsed as ProblemDetails) : null;
    throw new ApiError(response.status, response.statusText, parsed, problem);
  }
  return parsed as CostItem;
}

export function removeAttachment(
  id: string,
  lineId: string,
  attachmentId: string,
): Promise<CostItem> {
  return apiDelete<CostItem>(attachmentUrl(id, lineId, attachmentId));
}

/** A file size for reading: "84 kB", "1,2 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} kB`;
  return `${(kb / 1024).toLocaleString('nl-NL', { maximumFractionDigits: 1 })} MB`;
}

export function setCoverage(id: string, budgetLineId: string, pct: string): Promise<CostItem> {
  return apiPut<CostItem>(`/api/costs/${id}/coverage/${budgetLineId}`, { pct });
}

export function removeCoverage(id: string, budgetLineId: string): Promise<void> {
  return apiDelete(`/api/costs/${id}/coverage/${budgetLineId}`);
}

/** In a table: whether the invoice is in, or still expected. */
export const KIND_LABELS: Record<InvoiceLine['kind'], string> = {
  actual: 'Ontvangen',
  estimate: 'Verwacht',
};

/** As a choice in a form. */
export const KIND_CHOICES: Record<InvoiceLine['kind'], string> = {
  actual: 'Ontvangen factuur',
  estimate: 'Verwachte factuur',
};
