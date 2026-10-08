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
}

export const RATE_CARDS_KEY = ['rates', 'cards'] as const;

export function fetchRateCards(): Promise<RateCardList> {
  return apiGet<RateCardList>('/api/rates/cards');
}

export function createRateCard(year: number, copyFrom: number | null): Promise<RateCard> {
  return apiPost<RateCard>('/api/rates/cards', { year, copy_from: copyFrom });
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
