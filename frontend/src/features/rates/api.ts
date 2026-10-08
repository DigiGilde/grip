import { apiGet, apiPost, apiPut } from '@/api/client';

export type CardStatus = 'draft' | 'active' | 'closed';
export const CATEGORIES = ['A', 'B', 'C', 'D', 'E'] as const;
export type Category = (typeof CATEGORIES)[number];

export interface RateBand {
  category: string;
  monthly_rate_cents: number;
}

export interface ScaleBand {
  scale: number;
  category: string;
}

export interface RateCard {
  year: number;
  status: CardStatus;
  rate_bands: RateBand[];
  scale_bands: ScaleBand[];
}

export interface RateCardList {
  items: RateCard[];
  may_manage: boolean;
  /** Instance setting: the increase proposed for a new year, as a decimal string. */
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
  copy_from: number;
  increase_pct: string;
  rounding: Rounding;
  rates: IndexedRate[];
}

/** How a new year is filled from an earlier one. */
export interface Indexation {
  copyFrom: number;
  increasePct: string;
  rounding: Rounding;
}

export const RATE_CARDS_KEY = ['rates', 'cards'] as const;

export function fetchRateCards(): Promise<RateCardList> {
  return apiGet<RateCardList>('/api/rates/cards');
}

export const previewKey = (indexation: Indexation) =>
  ['rates', 'preview', indexation.copyFrom, indexation.increasePct, indexation.rounding] as const;

/** The rates a new year would get. The server computes them; nothing is created. */
export function fetchIndexationPreview(indexation: Indexation): Promise<IndexationPreview> {
  return apiGet<IndexationPreview>('/api/rates/indexation-preview', {
    copy_from: indexation.copyFrom,
    increase_pct: indexation.increasePct,
    rounding: indexation.rounding,
  });
}

/** Without an indexation the year starts empty. */
export function createRateCard(year: number, indexation: Indexation | null): Promise<RateCard> {
  return apiPost<RateCard>('/api/rates/cards', {
    year,
    copy_from: indexation?.copyFrom ?? null,
    increase_pct: indexation?.increasePct ?? null,
    rounding: indexation?.rounding ?? 'euro',
  });
}

/** `confirmClosedYear` states that the caller knows the year is closed. */
export function setCardStatus(
  year: number,
  status: CardStatus,
  confirmClosedYear = false,
): Promise<RateCard> {
  return apiPut<RateCard>(`/api/rates/cards/${year}/status`, {
    status,
    confirm_closed_year: confirmClosedYear,
  });
}

export function setRateBand(
  year: number,
  category: string,
  monthlyRateCents: number,
  confirmClosedYear = false,
): Promise<RateCard> {
  return apiPut<RateCard>(`/api/rates/cards/${year}/bands/${category}`, {
    monthly_rate_cents: monthlyRateCents,
    confirm_closed_year: confirmClosedYear,
  });
}

export function setScaleBand(
  year: number,
  scale: number,
  category: string,
  confirmClosedYear = false,
): Promise<RateCard> {
  return apiPut<RateCard>(`/api/rates/cards/${year}/scales/${scale}`, {
    category,
    confirm_closed_year: confirmClosedYear,
  });
}

export const STATUS_LABELS: Record<CardStatus, string> = {
  draft: 'Concept',
  active: 'Actief',
  closed: 'Gesloten',
};
