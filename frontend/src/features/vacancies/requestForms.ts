/** The request form of a vacancy as a kept document. */
import { apiGet, apiPost } from '@/api/client';
import { postForm } from '@/features/form-templates/api';

export interface KeptForm {
  id: string;
  file_name: string;
  sha256: string;
  size_bytes: number;
  made_at: string;
  made_by_name?: string | null;
}

export interface RequestForms {
  /** The instance has a blank form in use. */
  available: boolean;
  may_make: boolean;
  /** The newest kept form; null when none was made yet. */
  current: KeptForm | null;
  earlier: KeptForm[];
  /** What the vacancy says now that the newest form does not. */
  changed: string[];
  /** Copies that were completed or signed outside grip. */
  signed: KeptForm[];
}

const base = (vacancyId: string) => `/api/vacancies/${vacancyId}/request-forms`;

export const requestFormsKey = (vacancyId: string) =>
  ['vacancies', vacancyId, 'request-forms'] as const;

export const fetchRequestForms = (vacancyId: string) => apiGet<RequestForms>(base(vacancyId));

export const makeRequestForm = (vacancyId: string) => apiPost<RequestForms>(base(vacancyId));

export function recordSignedForm(vacancyId: string, file: File): Promise<RequestForms> {
  const form = new FormData();
  form.append('file', file);
  return postForm<RequestForms>(`${base(vacancyId)}/signed`, form);
}

export const keptFormUrl = (vacancyId: string, documentId: string) =>
  `${base(vacancyId)}/${documentId}`;

/** "Schaal, Advies van HR en Akkoord": what changed, as part of a sentence. */
export function changedText(changed: readonly string[]): string {
  const parts = changed.map((part, index) =>
    index === 0 ? part : part.charAt(0).toLowerCase() + part.slice(1),
  );
  if (parts.length <= 1) return parts[0] ?? '';
  return `${parts.slice(0, -1).join(', ')} en ${parts[parts.length - 1]}`;
}
