/**
 * The texts of a vacancy as work: where each stands, its versions, the
 * rounds of review, the remarks, and where the vacancy is published. A field
 * the viewer may not see is absent, so names are optional here.
 */
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client';
import type { TextKind } from './api';

export type TextState = 'none' | 'draft' | 'in_review' | 'returned' | 'agreed' | 'settled';
export type ActionKey =
  'start' | 'write' | 'offer' | 'withdraw' | 'judge' | 'process' | 'settle' | 'revise' | 'none';

export interface WorkVersion {
  id: string;
  number: number;
  body: string;
  source: 'human' | 'model' | 'template';
  origin?: string | null;
  created_at: string;
  settled_at?: string | null;
  created_by_name?: string | null;
  settled_by_name?: string | null;
  by_viewer: boolean;
}

export interface Verdict {
  reviewer_id?: string;
  reviewer_name?: string | null;
  is_viewer: boolean;
  verdict?: 'agreed' | 'remarks' | null;
  note?: string | null;
  decided_at?: string | null;
}

export interface Round {
  id: string;
  round: number;
  version_number: number;
  offered_at: string;
  offered_by_name?: string | null;
  note?: string | null;
  withdrawn: boolean;
  outcome: 'open' | 'agreed' | 'returned' | 'withdrawn';
  verdicts: Verdict[];
}

export interface Remark {
  id: string;
  section: string;
  body: string;
  version_number?: number | null;
  created_at: string;
  author_name?: string | null;
  by_viewer: boolean;
  resolved_at?: string | null;
  answers: Remark[];
}

export interface Change {
  heading: string;
  change: 'added' | 'removed' | 'changed';
  summary: string;
  before: string;
  after: string;
}

export interface StandardText {
  role: string;
  match: 'role' | 'name' | 'function_group';
  unread: boolean;
  missing: string[];
}

export interface TextWork {
  kind: TextKind;
  needed: boolean;
  state: TextState;
  state_text: string;
  with_whom?: string | null;
  revising: boolean;
  open_passages: string[];
  action: { key: ActionKey; text: string };
  may_write: boolean;
  may_remark: boolean;
  may_settle: boolean;
  viewer_review_id?: string | null;
  standard_text?: StandardText | null;
  default_reviewer_ids?: string[];
  versions: WorkVersion[];
  rounds: Round[];
  remarks: Remark[];
  latest_changes: Change[];
}

export interface Publication {
  id: string;
  place: 'internal' | 'government_wide' | 'external';
  place_text: string;
  url: string;
  published_on: string;
}

export interface VacancyTextWork {
  vacancy_id: string;
  texts: TextWork[];
  publications: Publication[];
  may_record_publication: boolean;
  publication_missing: boolean;
  drafting_available: boolean;
  drafting_note?: string | null;
  /**
   * Only in the answer to a tailored draft: whether the policy context from
   * the corpus went along to the model.
   */
  context?: 'used' | 'none' | 'unreachable';
  reviewer_options?: { id: string; name: string }[];
}

const base = (id: string) => `/api/vacancies/${id}`;

export const TEXT_WORK_KEY = (id: string) => ['vacancies', 'text-work', id] as const;

function whole(work: VacancyTextWork): VacancyTextWork {
  return {
    ...work,
    publications: work.publications ?? [],
    texts: (work.texts ?? []).map((text) => ({
      ...text,
      open_passages: text.open_passages ?? [],
      versions: text.versions ?? [],
      rounds: (text.rounds ?? []).map((round) => ({ ...round, verdicts: round.verdicts ?? [] })),
      remarks: (text.remarks ?? []).map((remark) => ({
        ...remark,
        answers: remark.answers ?? [],
      })),
      latest_changes: text.latest_changes ?? [],
    })),
  };
}

export const fetchTextWork = (id: string) =>
  apiGet<VacancyTextWork>(`${base(id)}/text-work`).then(whole);
export const saveVersion = (id: string, kind: TextKind, body: string, basedOnId: string | null) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/versions`, {
    kind,
    body,
    based_on_id: basedOnId,
  }).then(whole);
export const useStandardText = (id: string) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/standard`).then(whole);
export const draftTailored = (id: string, instruction: string) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/tailored`, {
    instruction: instruction.trim() || null,
  }).then(whole);
export const offerForReview = (id: string, kind: TextKind, reviewerIds: string[], note: string) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/reviews`, {
    kind,
    reviewer_ids: reviewerIds,
    note: note.trim() || null,
  }).then(whole);
export const withdrawReview = (id: string, reviewId: string) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/reviews/${reviewId}/withdraw`).then(whole);
export const giveVerdict = (
  id: string,
  reviewId: string,
  verdict: 'agreed' | 'remarks',
  note: string,
) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/reviews/${reviewId}/verdict`, {
    verdict,
    note: note.trim() || null,
  }).then(whole);
export const addRemark = (
  id: string,
  kind: TextKind,
  body: string,
  section: string,
  parentId?: string,
) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/remarks`, {
    kind,
    body,
    section,
    parent_id: parentId ?? null,
  }).then(whole);
export const resolveRemark = (id: string, remarkId: string, resolved: boolean) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/remarks/${remarkId}/resolve`, {
    resolved,
  }).then(whole);
export const settleVersion = (id: string, textId: string) =>
  apiPost<VacancyTextWork>(`${base(id)}/text-work/versions/${textId}/settle`).then(whole);
export const setPublication = (
  id: string,
  place: Publication['place'],
  url: string,
  publishedOn: string,
) =>
  apiPut<VacancyTextWork>(`${base(id)}/publications`, {
    place,
    url,
    published_on: publishedOn || null,
  }).then(whole);
export const removePublication = (id: string, publicationId: string) =>
  apiDelete<VacancyTextWork>(`${base(id)}/publications/${publicationId}`).then(whole);

/** A structured text as sections: a heading line "## ..." and what follows. */
export function splitSections(text: string): { heading: string; body: string }[] {
  const sections: { heading: string; lines: string[] }[] = [{ heading: '', lines: [] }];
  for (const line of text.split('\n')) {
    if (line.startsWith('## ')) sections.push({ heading: line.slice(3).trim(), lines: [] });
    else sections[sections.length - 1]?.lines.push(line);
  }
  return sections
    .map((section) => ({ heading: section.heading, body: section.lines.join('\n').trim() }))
    .filter((section) => section.heading || section.body);
}

// --- the library of standard texts ----------------------------------------

export interface TemplateSection {
  key?: string;
  heading?: string;
  body?: string;
  shared?: string;
  optional?: string;
}

export interface StandardTemplate {
  id: string;
  role_name: string;
  aliases: string[];
  scale_min: number | null;
  scale_max: number | null;
  function_group: string | null;
  status: 'example' | 'derived' | 'derived_unread' | 'manual' | 'changed';
  status_text: string;
  changed_at: string | null;
  changed_by_name: string | null;
  is_active: boolean;
  sections: TemplateSection[];
  label: string;
}

export interface SharedSection {
  key: string;
  heading: string;
  body: string;
  used_by: string[];
  changed_at: string | null;
  changed_by_name: string | null;
}

export interface TextSettings {
  unit_name: string;
  location: string;
  website: string;
  contact: string;
}

export interface Library {
  may_manage: boolean;
  placeholders: { name: string; meaning: string }[];
  settings: TextSettings;
  shared_sections: SharedSection[];
  templates: StandardTemplate[];
}

export interface TemplateInput {
  role_name: string;
  aliases: string[];
  scale_min: number | null;
  scale_max: number | null;
  function_group: string | null;
  sections?: TemplateSection[];
  copy_of?: string;
}

export const LIBRARY_KEY = ['vacancy-texts'] as const;
const LIB = '/api/vacancy-texts';

export const fetchLibrary = () => apiGet<Library>(LIB);
export const addTemplate = (body: TemplateInput) => apiPost<Library>(`${LIB}/templates`, body);
export const changeTemplate = (id: string, body: TemplateInput) =>
  apiPut<Library>(`${LIB}/templates/${id}`, body);
export const markTemplateRead = (id: string) => apiPost<Library>(`${LIB}/templates/${id}/read`);
export const setTemplateActive = (id: string, isActive: boolean) =>
  apiPost<Library>(`${LIB}/templates/${id}/active`, { is_active: isActive });
export const changeSharedSection = (key: string, heading: string, body: string) =>
  apiPut<Library>(`${LIB}/shared/${key}`, { heading, body });
export const changeTextSettings = (settings: TextSettings) =>
  apiPut<Library>(`${LIB}/settings`, settings);
export const previewTemplate = (id: string) =>
  apiPost<{ text: string; missing: string[] }>(`${LIB}/templates/${id}/preview`, {});

export interface ModelStatus {
  provider: 'vlam' | 'claude_cli' | 'none';
  provider_text: string;
  available: boolean;
  development: boolean;
  note: string | null;
}
export const fetchModelStatus = () => apiGet<ModelStatus>(`${LIB}/model`);
export const testModel = () =>
  apiPost<{ answered: boolean; message: string; model?: string }>(`${LIB}/model/test`);
