/**
 * The vacancy API. A field the viewer may not see is absent from the
 * response (not null), so every field beyond the public ones is optional
 * here and the screens draw only what is there.
 */
import { apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { withLists } from '@/lib/absent';

export type VacancyStatus =
  | 'draft'
  | 'requested'
  | 'approved'
  | 'rejected'
  | 'open'
  | 'filled'
  | 'withdrawn';
export type VacancyType = 'regulier' | 'specialistisch' | 'beoogd' | 'gerede';
export type ContractType = 'temporary_project' | 'temporary_before_permanent';
export type DecisionKind = 'hr_advice' | 'control_advice' | 'approval';
export type TextKind = 'vacancy_text' | 'motivation';
export type Channel = 'internal' | 'federated' | 'recruitment';
export type OpeningStep =
  | 'internal_opening'
  | 'priority_candidates'
  | 'government_wide_opening'
  | 'external_market';

export interface PublishedText {
  body: string;
  established_at: string;
  model_assisted: boolean;
  model_id?: string | null;
  drafted_at?: string | null;
}

export interface ProcedureStep {
  kind: string;
  label: string;
  position: number;
  recorded: boolean;
  started_on?: string | null;
  ended_on?: string | null;
  minimum_working_days?: number | null;
  earliest_end?: string | null;
  note?: string | null;
}

export interface Decision {
  kind: DecisionKind;
  label: string;
  agreed?: boolean | null;
  decided_on?: string | null;
  person_name?: string;
  has_account?: boolean;
  note?: string | null;
}

export interface TextVersion {
  id: string;
  kind: TextKind;
  body: string;
  source: 'human' | 'model';
  model_id?: string | null;
  prompt_version?: string | null;
  created_at: string;
  based_on_id?: string | null;
  established_at?: string | null;
  model_assisted: boolean;
  origin_model_id?: string | null;
  origin_drafted_at?: string | null;
  is_current: boolean;
  created_by_name?: string | null;
  established_by_name?: string | null;
}

export interface VacancyPermissions {
  can_edit: boolean;
  can_record_hr_advice: boolean;
  can_record_control_advice: boolean;
  can_record_approval: boolean;
  can_download_form: boolean;
  can_withdraw?: boolean;
  can_fill?: boolean;
}

export interface VacancySummary {
  id: string;
  function_title: string;
  scale?: number | null;
  fte: string;
  start_date?: string | null;
  end_date?: string | null;
  status: VacancyStatus;
  vacancy_type?: VacancyType;
  declarable?: boolean;
  assignment_name?: string | null;
  requested_on?: string | null;
  current_step?: string | null;
  next_step?: string | null;
  /** The step it is at: prepare, submit, decide, open, fill; null once ended. */
  step?: string | null;
  /** What that step waits on, without a name. */
  step_detail?: string | null;
  /** Since when it is at this step, or when it ended. */
  step_since?: string | null;
  requester_name?: string | null;
}

export interface Vacancy {
  id: string;
  function_title: string;
  fgr_function_name?: string | null;
  scale?: number | null;
  fte: string;
  start_date?: string | null;
  end_date?: string | null;
  status: VacancyStatus;
  published_at?: string | null;
  published_text?: PublishedText | null;
  declarable?: boolean;
  vacancy_type?: VacancyType;
  contract_type?: ContractType | null;
  channels?: Channel[];
  budget_line_id?: string | null;
  assignment_id?: string | null;
  assignment_name?: string | null;
  requested_on?: string | null;
  created_at?: string;
  has_openings?: boolean;
  procedure: ProcedureStep[];
  decisions: Decision[];
  texts: TextVersion[];
  requester_id?: string | null;
  requester_name?: string | null;
  addressee_name?: string | null;
  addressee_has_account?: boolean;
  /** The function group the FGR name was taken from, and what it allows. */
  function_group_id?: string | null;
  function_family_name?: string | null;
  function_group_scales?: number[] | null;
  scale_deviation_reason?: string | null;
  suggested_function_group_ids?: string[];
  /** The scales of the budget line's rate category. */
  budget_line_scales?: number[] | null;
  /** False when the scale lies outside the budget line's category. */
  scale_fits_budget_line?: boolean | null;
  permissions: VacancyPermissions;
}

export interface OpenRole {
  id: string;
  function_title: string;
  fgr_function_name?: string | null;
  scale?: number | null;
  fte: string;
  start_date?: string | null;
  end_date?: string | null;
  published_at?: string | null;
  text: PublishedText;
}

export interface UnfilledRole {
  budget_line_id: string;
  assignment_id: string;
  assignment_name: string;
  description: string;
  role?: string | null;
  fte: string;
  unfilled_fte: string;
  start_date?: string | null;
  end_date?: string | null;
  declarable: boolean;
}

export interface Option {
  value: string;
  label: string;
}

export interface VacancyOptions {
  vacancy_types: Option[];
  contract_types: Option[];
  statuses: Option[];
  channels: Option[];
  decision_kinds: Option[];
  text_kinds: Option[];
  steps: (Option & { minimum_working_days?: number | null })[];
  drafting_available: boolean;
  request_form_available: boolean;
  can_create_without_budget_line: boolean;
  can_manage_setup: boolean;
}

export interface RequestFormStatus {
  available: boolean;
  file_name?: string | null;
  open_fields: { source: string; label: string }[];
  motivation_established: boolean;
}

export interface VacancyCreate {
  budget_line_id?: string;
  function_title?: string;
  fte?: string;
  vacancy_type: VacancyType;
  contract_type?: ContractType | null;
  fgr_function_name?: string | null;
  scale?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  addressee_name?: string | null;
}

export type VacancyUpdate = Partial<Omit<VacancyCreate, 'budget_line_id'>> & {
  function_group_id?: string | null;
  scale_deviation_reason?: string | null;
  addressee_id?: string | null;
};

export interface DecisionInput {
  /** Someone without an account in this instance, named in free text. */
  person_name?: string;
  /** A person of this instance, who can then record the decision themselves. */
  person_id?: string;
  person_email?: string | null;
  agreed?: boolean | null;
  note?: string | null;
  decided_on?: string | null;
}

const BASE = '/api/vacancies';

export const VACANCY_KEYS = {
  list: ['vacancies', 'list'] as const,
  openRoles: ['vacancies', 'open-roles'] as const,
  unfilledRoles: ['vacancies', 'unfilled-roles'] as const,
  options: ['vacancies', 'options'] as const,
  detail: (id: string) => ['vacancies', 'detail', id] as const,
  formStatus: (id: string) => ['vacancies', 'form-status', id] as const,
};

// The procedure, decisions and text versions are absent for a reader who
// sees only the published vacancy.
const whole = (vacancy: Vacancy): Vacancy =>
  withLists(vacancy, 'procedure', 'decisions', 'texts');

export const fetchVacancies = () => apiGet<VacancySummary[]>(BASE);
export const fetchOpenRoles = () => apiGet<OpenRole[]>(`${BASE}/open-roles`);
export const fetchUnfilledRoles = () => apiGet<UnfilledRole[]>(`${BASE}/unfilled-roles`);
export const fetchVacancyOptions = () => apiGet<VacancyOptions>(`${BASE}/options`);
export const fetchVacancy = (id: string) => apiGet<Vacancy>(`${BASE}/${id}`).then(whole);
export const fetchRequestFormStatus = (id: string) =>
  apiGet<RequestFormStatus>(`${BASE}/${id}/request-form/status`);

export const createVacancy = (body: VacancyCreate) => apiPost<Vacancy>(BASE, body).then(whole);
export const updateVacancy = (id: string, body: VacancyUpdate) =>
  apiPatch<Vacancy>(`${BASE}/${id}`, body).then(whole);
export const submitVacancy = (id: string, requestedOn?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/submit`, requestedOn ? { requested_on: requestedOn } : {}).then(whole);
export const recordDecision = (id: string, kind: DecisionKind, body: DecisionInput) =>
  apiPut<Vacancy>(`${BASE}/${id}/decisions/${kind}`, body).then(whole);
export const setOpeningStep = (
  id: string,
  kind: OpeningStep,
  body: { started_on: string; ended_on?: string | null; note?: string | null },
) => apiPut<Vacancy>(`${BASE}/${id}/steps/${kind}`, body).then(whole);
export const publishVacancy = (id: string, channels: Channel[], openedOn?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/publish`, {
    channels,
    ...(openedOn ? { opened_on: openedOn } : {}),
  }).then(whole);
export const withdrawVacancy = (id: string, note?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/withdraw`, note ? { note } : {}).then(whole);
export const fillVacancy = (id: string, note?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/fill`, note ? { note } : {}).then(whole);
export const addText = (id: string, kind: TextKind, body: string, basedOnId?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/texts`, {
    kind,
    body,
    ...(basedOnId ? { based_on_id: basedOnId } : {}),
  }).then(whole);
export const draftText = (id: string, kind: TextKind, assignmentSummary?: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/texts/draft`, {
    kind,
    ...(assignmentSummary ? { assignment_summary: assignmentSummary } : {}),
  }).then(whole);
export const establishText = (id: string, textId: string) =>
  apiPost<Vacancy>(`${BASE}/${id}/texts/${textId}/establish`).then(whole);

/** Query parameter of the vacancy page that names the budget line to open a vacancy for. */
export const ROLE_PARAM = 'rol';

/** The vacancy page with the form open for one unfilled role. */
export const newVacancyPath = (budgetLineId: string) =>
  `/vacatures?${new URLSearchParams({ [ROLE_PARAM]: budgetLineId }).toString()}`;

/** The address of the filled request form; a plain download link. */
export const requestFormUrl = (id: string) => `${BASE}/${id}/request-form`;

// --- the recruitment reference and the hire ---------------------------------

export interface RecruitmentRef {
  system: string;
  reference: string;
  url?: string | null;
}

export interface ProposedAllocation {
  budget_line_id: string;
  start_date: string;
  end_date: string;
  fte_pct: string;
}

export interface Hire {
  person_id?: string | null;
  person_name?: string | null;
  start_date: string;
  /** "prospective" until the person has started. */
  stage?: string | null;
  /** The inzet that follows from the hire, when it was not planned at once. */
  proposed_allocation?: ProposedAllocation | null;
  allocation_id?: string | null;
}

export interface VacancyHire {
  vacancy_id: string;
  recruitment_ref?: RecruitmentRef | null;
  hire?: Hire | null;
}

export interface RecruitmentRefInput {
  reference: string;
  url?: string | null;
  system?: string | null;
}

export interface HireInput {
  start_date: string;
  person_id?: string;
  name?: string;
  suborganization?: string;
  create_allocation: boolean;
  note?: string;
}

/** The recruitment system a reference points into unless another is named. */
export const DEFAULT_RECRUITMENT_SYSTEM = 'Emply';

export const hireKey = (id: string) => ['vacancies', 'hire', id] as const;

export const fetchVacancyHire = (id: string) => apiGet<VacancyHire>(`${BASE}/${id}/hire`);
export const setRecruitmentRef = (id: string, body: RecruitmentRefInput) =>
  apiPut<VacancyHire>(`${BASE}/${id}/recruitment-ref`, body);
export const recordHire = (id: string, body: HireInput) =>
  apiPost<VacancyHire>(`${BASE}/${id}/hire`, body);
export const withdrawHire = (id: string, reason: string) =>
  apiPost<VacancyHire>(`${BASE}/${id}/hire/withdraw`, { reason });
