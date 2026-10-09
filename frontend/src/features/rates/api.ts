import { apiGet, apiPatch, apiPost, apiPut } from '@/api/client';
import { ifMatch } from '@/ui/stale';

export type CardStatus = 'draft' | 'active' | 'closed';
export const CATEGORIES = ['A', 'B', 'C', 'D', 'E'] as const;
export type Category = (typeof CATEGORIES)[number];

export interface RateBand {
  /** Absent for a rate that was never set. */
  id?: string | null;
  /** Counts the changes of the rate; sent back with a save. */
  version?: number;
  category: string;
  /** Absent for a reader who may not read the amounts of the price list. */
  monthly_rate_cents?: number;
}

export interface ScaleBand {
  scale: number;
  category: string;
}

/** A rate card holds for a period: from a date, and to a date or open-ended. */
export interface RateCard {
  id: string;
  /** Counts the changes of the card; sent back with a save. */
  version?: number;
  name: string;
  valid_from: string;
  valid_to: string | null;
  status: CardStatus;
  rate_bands: RateBand[];
  scale_bands: ScaleBand[];
}

export interface RateCardList {
  /** Newest first. */
  items: RateCard[];
  may_manage: boolean;
  /** Whether the bands carry their amounts for this reader. */
  may_read_amounts?: boolean;
  /** Instance setting: the increase proposed for a new card, as a decimal string. */
  default_increase_pct: string;
}

/** What a new rate is rounded to. */
export type Rounding = 'euro' | 'ten' | 'fifty';

export const ROUNDING_LABELS: Record<Rounding, string> = {
  euro: "Hele euro's",
  ten: 'Tientallen',
  fifty: 'Vijftigtallen',
};

export interface IndexedRate {
  category: string;
  old_monthly_rate_cents: number;
  new_monthly_rate_cents: number;
  difference_cents: number;
}

export interface IndexationPreview {
  copy_from_id: string;
  copy_from_name: string;
  increase_pct: string;
  rounding: Rounding;
  rates: IndexedRate[];
}

/** How a new card is filled from the card valid just before its start. */
export interface Indexation {
  validFrom: string;
  increasePct: string;
  rounding: Rounding;
}

export interface MonthChange {
  /** yyyy-mm */
  month: string;
  state: 'open' | 'closed' | 'delivered' | 'invoiced';
  before_cents: number | null;
  after_cents: number | null;
  difference_cents: number;
  invoice_number: string | null;
}

export interface AssignmentImpact {
  assignment_id: string;
  assignment_name: string;
  open_difference_cents: number;
  closed_difference_cents: number;
  /** Already delivered: becomes a correction to deliver (naverrekening). */
  correction_cents: number;
  months: MonthChange[];
}

/** What a change does to what is already priced. Nothing was saved. */
export interface PriceImpact {
  budget_lines_changed: number;
  budget_difference_cents: number;
  allocations_changed: number;
  open_difference_cents: number;
  closed_difference_cents: number;
  correction_cents: number;
  unpriced_months: number;
  reaches_into_the_past: boolean;
  /** Among the repriced: assignments with a signed quote. */
  signed_assignments_changed?: number;
  signed_difference_cents?: number;
  assignments: AssignmentImpact[];
}

export interface ActivationPreview {
  card: RateCard;
  /** The card that activating this one ends on the day before it starts. */
  shortened: { id: string; name: string; old_valid_to: string | null; new_valid_to: string } | null;
  /** The periods no settled card prices once this one is settled, with the drafts in them. */
  gaps?: { start_date: string; end_date: string; drafts: string[] }[];
  impact: PriceImpact;
}

export interface ValidStretch {
  start_date: string;
  end_date: string;
  /** Null in a gap: no card prices these days. */
  card_id: string | null;
  card_name: string | null;
}

export interface ValidRates {
  stretches: ValidStretch[];
  has_gap: boolean;
}

export const RATE_CARDS_KEY = ['rates', 'cards'] as const;
export const coverageKey = (start: string, end: string) => ['rates', 'valid', start, end] as const;
export const previewKey = (indexation: Indexation) =>
  ['rates', 'preview', indexation.validFrom, indexation.increasePct, indexation.rounding] as const;
export const activationKey = (cardId: string) => ['rates', 'activation', cardId] as const;

export function fetchRateCards(): Promise<RateCardList> {
  return apiGet<RateCardList>('/api/rates/cards');
}

/** Which card prices which stretch of a period, and where no card does. */
export function fetchValidRates(start: string, end: string): Promise<ValidRates> {
  return apiGet<ValidRates>('/api/rates/valid', { start_date: start, end_date: end });
}

/** The rates a new card would get. The server computes them; nothing is created. */
export function fetchIndexationPreview(indexation: Indexation): Promise<IndexationPreview> {
  return apiGet<IndexationPreview>('/api/rates/indexation-preview', {
    valid_from: indexation.validFrom,
    increase_pct: indexation.increasePct,
    rounding: indexation.rounding,
  });
}

export interface NewCard {
  validFrom: string;
  /** Null: open-ended. */
  validTo: string | null;
  name: string | null;
  /** Null: the card starts empty. */
  indexation: Indexation | null;
}

/** A new card is always a draft; activating it is a separate step. */
export function createRateCard(card: NewCard): Promise<RateCard> {
  return apiPost<RateCard>('/api/rates/cards', {
    valid_from: card.validFrom,
    valid_to: card.validTo,
    name: card.name,
    copy_previous: card.indexation !== null,
    increase_pct: card.indexation?.increasePct ?? null,
    rounding: card.indexation?.rounding ?? 'euro',
  });
}

/** `version` is the version of the card the form started from. */
export function updateRateCard(
  id: string,
  changes: { name?: string; valid_to?: string | null },
  confirmClosed = false,
  version?: number,
): Promise<RateCard> {
  return apiPatch<RateCard>(
    `/api/rates/cards/${id}`,
    {
      ...changes,
      confirm_closed_year: confirmClosed,
    },
    ifMatch(id, version),
  );
}

/** What activating a draft does, before it is done. */
export function fetchActivationPreview(id: string): Promise<ActivationPreview> {
  return apiGet<ActivationPreview>(`/api/rates/cards/${id}/activation-preview`);
}

export function activateRateCard(id: string, confirmClosed = false): Promise<RateCard> {
  return apiPost<RateCard>(`/api/rates/cards/${id}/activate`, {
    confirm_closed_year: confirmClosed,
  });
}

export function closeRateCard(id: string): Promise<RateCard> {
  return apiPost<RateCard>(`/api/rates/cards/${id}/close`);
}

/** `confirmClosed` states that the caller knows the card is closed. */
export function setRateBand(
  id: string,
  category: string,
  monthlyRateCents: number,
  confirmClosed = false,
  /** The rate as the form found it: its id and version, when it existed. */
  from?: { id?: string | null; version?: number },
): Promise<RateCard> {
  return apiPut<RateCard>(
    `/api/rates/cards/${id}/bands/${category}`,
    {
      monthly_rate_cents: monthlyRateCents,
      confirm_closed_year: confirmClosed,
    },
    ifMatch(from?.id, from?.version),
  );
}

export function setScaleBand(
  id: string,
  scale: number,
  category: string,
  confirmClosed = false,
): Promise<RateCard> {
  return apiPut<RateCard>(`/api/rates/cards/${id}/scales/${scale}`, {
    category,
    confirm_closed_year: confirmClosed,
  });
}

export const STATUS_LABELS: Record<CardStatus, string> = {
  draft: 'Concept',
  active: 'Vastgesteld',
  closed: 'Gesloten',
};
