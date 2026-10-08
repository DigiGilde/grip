/** Form templates and the language model configuration. Beheerder only. */
import { ApiError, apiGet, apiPost, apiPut, getCsrfToken, type ProblemDetails } from '@/api/client';

export interface FormTemplate {
  id: string;
  name: string;
  file_name: string;
  is_active: boolean;
  created_at: string;
  uploaded_by_name?: string | null;
  mapped_fields: number;
  unverified_fields: number;
}

export interface FormField {
  name: string;
  type: string;
  states: string[];
  has_value: boolean;
  source?: string | null;
  label?: string | null;
}

export interface FormInspection {
  fields: FormField[];
  has_values: boolean;
  missing_fields: string[];
  problem?: string | null;
}

export interface BundledMapping {
  name: string;
  title: string;
  description?: string | null;
  mapping: Record<string, unknown>;
}

export interface LanguageModel {
  configured: boolean;
  model_id?: string | null;
  missing_settings: string[];
  organisation_description_set: boolean;
  available_models?: string[] | null;
  check_error?: string | null;
}

export const SETUP_KEYS = {
  templates: ['form-templates', 'list'] as const,
  bundled: ['form-templates', 'bundled'] as const,
  model: ['vacancies', 'language-model'] as const,
};

const BASE = '/api/form-templates';

export const fetchFormTemplates = () => apiGet<FormTemplate[]>(BASE);
export const fetchBundledMappings = () => apiGet<BundledMapping[]>(`${BASE}/bundled-mappings`);
export const activateFormTemplate = (id: string) => apiPost<FormTemplate>(`${BASE}/${id}/activate`);
export const fetchLanguageModel = (check = false) =>
  apiGet<LanguageModel>('/api/vacancies/language-model', { check: check || undefined });

/** A multipart post: the shared client only sends JSON. */
export async function postForm<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      Accept: 'application/json, application/problem+json',
      'X-CSRF-Token': getCsrfToken(),
    },
    credentials: 'same-origin',
    body: form,
  });
  const text = await response.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (response.ok) return body as T;
  const problem =
    typeof body === 'object' && body !== null && !Array.isArray(body)
      ? (body as ProblemDetails)
      : null;
  throw new ApiError(response.status, response.statusText, body, problem);
}

export interface TemplateSource {
  file: File;
  /** Name of a mapping that ships with grip, or the mapping itself as JSON text. */
  bundledMapping?: string;
  mappingJson?: string;
}

function sourceForm(source: TemplateSource): FormData {
  const form = new FormData();
  form.append('file', source.file);
  if (source.mappingJson?.trim()) form.append('mapping', source.mappingJson);
  else if (source.bundledMapping) form.append('bundled_mapping', source.bundledMapping);
  return form;
}

export function inspectForm(source: TemplateSource): Promise<FormInspection> {
  return postForm<FormInspection>(`${BASE}/inspect`, sourceForm(source));
}

export function uploadFormTemplate(
  source: TemplateSource,
  name: string,
  clearValues: boolean,
): Promise<FormTemplate> {
  const form = sourceForm(source);
  form.append('name', name);
  form.append('clear_values', clearValues ? 'true' : 'false');
  form.append('activate', 'true');
  return postForm<FormTemplate>(BASE, form);
}

/** A field of a stored form, with what fills it. */
export interface TemplateField {
  name: string;
  type: string;
  /** The caption of the field on the form, when the mapping names one. */
  label?: string | null;
  source?: string | null;
  equals?: string | boolean | null;
  /** What grip puts in the field, in plain words. */
  fills?: string | null;
  /** In the form and filled, in the form and not filled, or gone from the form. */
  state: 'mapped' | 'unfilled' | 'missing';
}

export interface FieldSource {
  key: string;
  label: string;
  /** Empty for a text source; a tick box takes one of these. */
  choices: { value: string | boolean; label: string }[];
}

export interface TemplateDetail {
  id: string;
  name: string;
  file_name: string;
  is_active: boolean;
  fields: TemplateField[];
  sources: FieldSource[];
}

export const templateKey = (id: string) => ['form-templates', 'detail', id] as const;

export const fetchTemplateDetail = (id: string) => apiGet<TemplateDetail>(`${BASE}/${id}`);

export const setTemplateField = (
  id: string,
  name: string,
  change: { source: string | null; equals?: string | boolean | null },
) => apiPut<TemplateDetail>(`${BASE}/${id}/fields/${encodeURIComponent(name)}`, change);

export const templateFileUrl = (id: string) => `${BASE}/${id}/file`;

/** The form filled in for a vacancy, or with example values when none is given. */
export const templateSampleUrl = (id: string, vacancyId?: string) =>
  `${BASE}/${id}/sample${vacancyId ? `?vacancy_id=${encodeURIComponent(vacancyId)}` : ''}`;
