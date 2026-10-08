/**
 * A rate category in the words people use: the scales it covers. The letter
 * is the rate card's own band and means little on its own. Scales and rates
 * differ per rate card, and a card is valid from a date to a date, so every
 * text is made from the card that is valid on a date.
 */
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';
import { RATE_CARDS_KEY, fetchRateCards } from '@/features/rates/api';
import { formatEuro } from '@/lib/format';

/** What a category text is made from: the bands of one card. */
export interface RateSource {
  rate_bands: readonly { category: string; monthly_rate_cents: number }[];
  scale_bands: readonly { scale: number; category: string }[];
}

type RateCard = RateSource;

/** A card from the list, with the period it is valid for. */
export interface DatedCard extends RateSource {
  status: string;
  valid_from?: string;
  valid_to?: string | null;
  /** Only on a list from before cards had a validity. */
  year?: number;
}

/** The card valid on a day (yyyy-mm-dd): the active or closed one, never a draft. */
export function cardOn(cards: readonly DatedCard[], day: string): DatedCard | null {
  const usable = cards.filter((card) => card.status !== 'draft');
  return (
    usable.find(
      (card) =>
        card.valid_from !== undefined &&
        card.valid_from <= day &&
        (card.valid_to == null || card.valid_to >= day),
    ) ??
    // A list from before cards had a validity: the card of the year.
    usable.find((card) => card.valid_from === undefined && String(card.year) === day.slice(0, 4)) ??
    null
  );
}

/** One stretch of a period and the card that prices it; no card in a gap. */
export interface ValidStretch extends RateSource {
  start_date: string;
  end_date: string;
  card_id: string | null;
  card_name: string | null;
  card_valid_to: string | null;
}

export interface ValidRates {
  start_date: string;
  end_date: string;
  stretches: ValidStretch[];
  /** More than one card prices the period. */
  crosses_cards: boolean;
  /** And they do not all have the same rates. */
  rates_differ: boolean;
  has_gap: boolean;
  /** One sentence for under a field: "Volgens Tarieven 2026, geldig t/m ...". */
  summary: string;
}

/** The rates valid over a period; over today when the period is not known yet. */
export function useValidRates(start: string, end: string, enabled = true) {
  const today = new Date().toISOString().slice(0, 10);
  const from = start || today;
  const to = end && end >= from ? end : from;
  return useQuery({
    queryKey: ['rates', 'valid', from, to],
    queryFn: () => apiGet<ValidRates>('/api/rates/valid', { start_date: from, end_date: to }),
    enabled,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

export function scalesOf(card: RateCard | null, category: string): number[] {
  return (card?.scale_bands ?? [])
    .filter((band) => band.category === category)
    .map((band) => band.scale)
    .sort((a, b) => a - b);
}

function scalesText(scales: number[]): string {
  if (scales.length === 0) return '';
  if (scales.length === 1) return `Schaal ${scales[0]}`;
  return `Schaal ${scales.slice(0, -1).join(', ')} en ${scales[scales.length - 1]}`;
}

/** "Schaal 10 en 11 (categorie B)"; just "Categorie B" without a card that maps it. */
export function categoryText(card: RateCard | null, category: string): string {
  const scales = scalesText(scalesOf(card, category));
  return scales ? `${scales} (categorie ${category})` : `Categorie ${category}`;
}

/** The same, with the monthly rate: "Schaal 10 en 11 (categorie B), € 13.125 per maand". */
export function categoryOptionText(card: RateCard | null, category: string): string {
  const rate = card?.rate_bands.find((band) => band.category === category);
  const text = categoryText(card, category);
  return rate ? `${text}, ${formatEuro(rate.monthly_rate_cents)} per maand` : text;
}

/** Whether two cards give a category other scales or another rate. */
export function categoryDiffers(a: RateCard | null, b: RateCard | null, category: string): boolean {
  if (!a || !b) return false;
  return categoryOptionText(a, category) !== categoryOptionText(b, category);
}

/** Names a category as on a day (yyyy-mm-dd); today when no day is given. */
export type CategoryNamer = (category: string, on?: string | null) => string;

/**
 * The rate cards, and a function that names a category on a day. Until the
 * cards are there it falls back to the letter.
 */
export function useRateCards(enabled = true) {
  const query = useQuery({ queryKey: RATE_CARDS_KEY, queryFn: fetchRateCards, enabled, retry: false });
  // Read structurally: only the bands, the status and the validity are used.
  const cards = (query.data?.items ?? []) as readonly DatedCard[];
  const today = new Date().toISOString().slice(0, 10);
  const name: CategoryNamer = (category, on) => categoryText(cardOn(cards, on || today), category);
  return { cards, name, loaded: query.isSuccess, failed: query.isError };
}
