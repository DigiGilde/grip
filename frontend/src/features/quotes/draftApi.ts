/**
 * The text of a quote in preparation: a letter with sections, one draft per
 * assignment. The numbers are not here; they come from the budget.
 */
import { ApiError, apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { PATHS } from '@/paths';

export type SectionOrigin = 'empty' | 'standard' | 'written' | 'generated';

export interface DraftSection {
  key: string;
  heading: string;
  /** Plain text with a few marks; never HTML. */
  body: string;
  /** What belongs in this section, from the organisation. */
  hint?: string;
  included: boolean;
  /** The section that carries the table from the budget. */
  with_costs: boolean;
  numbered?: boolean;
  /** The organisation lets the language model draft this section. */
  draftable: boolean;
  origin: SectionOrigin | string;
  /** False for a text the model drafted that nobody saved yet. */
  settled: boolean;
  /**
   * How a model draft came about. `context` says whether the policy context
   * from the corpus went along: used, none to give, or not reachable.
   */
  generated?: { context?: 'used' | 'none' | 'unreachable' } | null;
  /** Counts up with every save; sent back so nobody overwrites a colleague unseen. */
  version?: number;
  changed_by?: string | null;
  changed_at?: string | null;
  /**
   * The organisation changed its standard text for this section after a
   * person wrote their own here. The own text stays until they take the new
   * one over.
   */
  standard_changed?: boolean;
  /** What the organisation allows for this section in a quote. */
  optional?: boolean;
  removable?: boolean;
  movable?: boolean;
}

export interface ClientSignatory {
  on_behalf_of?: string;
  name?: string;
  function?: string;
  organisation?: string;
}

export interface QuoteDraft {
  /** False while the reader looks at the organisation's starting texts. */
  saved: boolean;
  may_edit: boolean;
  /** Whether a language model can be asked at all. */
  drafting_available: boolean;
  problems: { key: string; problem: string }[];
  /** What the sender still lacks for this letter, as one sentence; null when complete. */
  sender_problem?: string | null;
  /** Whether this reader can fill that in under Beheer. */
  may_set_sender?: boolean;
  subject: string;
  addressee: string[];
  salutation: string;
  opening: string;
  closing: string;
  billing_annex?: boolean;
  client_signatory?: ClientSignatory;
  sections: DraftSection[];
  head_version?: number;
  outline_version?: number;
}

export const draftKeys = {
  // Under 'quotes': making a quote or changing one refreshes the draft too.
  draft: (assignmentId: string) => ['quotes', 'draft', assignmentId] as const,
};

const base = (assignmentId: string) => `/api/assignments/${assignmentId}/quote-draft`;

export function fetchDraft(assignmentId: string): Promise<QuoteDraft> {
  return apiGet(base(assignmentId));
}

export function saveLetter(
  assignmentId: string,
  input: Partial<
    Pick<QuoteDraft, 'subject' | 'addressee' | 'salutation' | 'opening' | 'closing'>
  > & { client_signatory?: ClientSignatory; head_version?: number },
): Promise<QuoteDraft> {
  return apiPatch(base(assignmentId), input);
}

/** Saving a section is what settles a text the model drafted. */
export function saveSection(
  assignmentId: string,
  key: string,
  input: {
    body?: string;
    heading?: string;
    included?: boolean;
    /** Give up the own text and follow the organisation's standard text again. */
    follow_standard?: boolean;
    version?: number;
  },
): Promise<QuoteDraft> {
  return apiPut(`${base(assignmentId)}/sections/${key}`, input);
}

export function saveOutline(
  assignmentId: string,
  keys: string[],
  newSections: { key: string; heading: string }[] = [],
  outlineVersion?: number,
): Promise<QuoteDraft> {
  return apiPut(`${base(assignmentId)}/outline`, {
    keys,
    new_sections: newSections,
    ...(outlineVersion === undefined ? {} : { outline_version: outlineVersion }),
  });
}

export function draftSection(assignmentId: string, key: string): Promise<QuoteDraft> {
  return apiPost(`${base(assignmentId)}/sections/${key}/draft`);
}

export function rewritePassage(
  assignmentId: string,
  key: string,
  input: { passage: string; instruction: string | null },
): Promise<{ text: string }> {
  return apiPost(`${base(assignmentId)}/sections/${key}/rewrite`, input);
}

/** A colleague saved first: who, when, and the draft as it is now. */
export interface DraftConflict {
  changedBy: string | null;
  changedAt: string | null;
  current: QuoteDraft;
}

/** The conflict in a refused save, or null when the failure is something else. */
export function conflictOf(failure: unknown): DraftConflict | null {
  if (!(failure instanceof ApiError) || failure.status !== 409) return null;
  const problem = failure.problem;
  const current = problem?.current as QuoteDraft | undefined;
  if (!current) return null;
  return {
    changedBy: (problem?.changed_by as string | null | undefined) ?? null,
    changedAt: (problem?.changed_at as string | null | undefined) ?? null,
    current,
  };
}

export function draftPreviewUrl(assignmentId: string): string {
  return `${base(assignmentId)}/preview`;
}

/**
 * The address of the writing page. `fresh` says the reader chose to make a
 * new quote: without it the page shows the quote that already lies there.
 */
export function quoteDraftPath(
  assignmentId: string,
  sectionKey?: string,
  options: { fresh?: boolean } = {},
): string {
  const path = PATHS.assignmentQuoteDraft.replace(':assignmentId', assignmentId);
  const query = new URLSearchParams();
  if (options.fresh) query.set(FRESH_PARAM, '1');
  if (sectionKey) query.set(SECTION_PARAM, sectionKey);
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const FRESH_PARAM = 'nieuw';
export const SECTION_PARAM = 'onderdeel';

// --- words ---------------------------------------------------------------------

/** Where the text of a section comes from and whether it counts, in words. */
export function sectionState(section: DraftSection): string {
  if (!section.included) return 'Niet in deze offerte';
  if (section.with_costs) return 'Bedragen uit de begroting';
  if (!section.settled) return 'Concept van het taalmodel: nog niet vastgesteld';
  if (section.origin === 'standard') return 'Standaardtekst';
  if (section.origin === 'generated') return 'Opgesteld met het taalmodel, vastgesteld';
  if (section.origin === 'written' && section.body) return 'Zelf geschreven';
  return 'Leeg';
}

/** A section that still stands in the way of the quote: no text, or a draft nobody settled. */
export function needsAttention(section: DraftSection): boolean {
  if (!section.included || section.with_costs) return false;
  return !section.settled || !section.body;
}

/** A person writes this section here; a standard text and the costs are not written here. */
export function isWritten(section: DraftSection): boolean {
  return !section.with_costs && section.origin !== 'standard';
}

// --- the outline ----------------------------------------------------------------

/** The keys with one section moved up or down; unchanged at an edge. */
export function movedKeys(keys: readonly string[], key: string, by: -1 | 1): string[] {
  const from = keys.indexOf(key);
  const to = from + by;
  if (from < 0 || to < 0 || to >= keys.length) return [...keys];
  const next = [...keys];
  next.splice(from, 1);
  next.splice(to, 0, key);
  return next;
}

/** A key for a section someone adds, from its heading; unique among the others. */
export function newSectionKey(heading: string, existing: readonly string[]): string {
  const slug =
    heading
      .toLowerCase()
      .normalize('NFD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 30) || 'onderdeel';
  let key = slug;
  for (let n = 2; existing.includes(key); n += 1) key = `${slug}-${n}`;
  return key;
}

// --- never lose text --------------------------------------------------------------

const LOCAL_PREFIX = 'grip.offertetekst.';
const localKey = (assignmentId: string, key: string) => `${LOCAL_PREFIX}${assignmentId}.${key}`;

export interface LocalCopy {
  text: string;
  /** The text on the server when the person started typing. */
  base: string;
  at: string;
}

/**
 * What the person typed and the server did not confirm yet. Kept in this
 * browser, so a closed tab, a lost connection or a refused save loses nothing.
 */
export function keepLocal(assignmentId: string, key: string, copy: LocalCopy): void {
  try {
    localStorage.setItem(localKey(assignmentId, key), JSON.stringify(copy));
  } catch {
    // Without storage the text is only in the field; saving still works.
  }
}

export function readLocal(assignmentId: string, key: string): LocalCopy | null {
  try {
    const raw = localStorage.getItem(localKey(assignmentId, key));
    return raw ? (JSON.parse(raw) as LocalCopy) : null;
  } catch {
    return null;
  }
}

export function dropLocal(assignmentId: string, key: string): void {
  try {
    localStorage.removeItem(localKey(assignmentId, key));
  } catch {
    // Nothing to drop.
  }
}
