/**
 * A rate category in the words people use: the scales it covers. The letter
 * is the rate card's own band and means little on its own. Scales and rates
 * differ per year, so every text is made from the rate card of a year.
 */
import { useQuery } from '@tanstack/react-query';
import { RATE_CARDS_KEY, fetchRateCards, type RateCard } from '@/features/rates/api';
import { formatEuro } from '@/lib/format';

/** The card to price a year with: the active or closed one, never a draft. */
export function cardOfYear(cards: readonly RateCard[], year: number): RateCard | null {
  return cards.find((card) => card.year === year && card.status !== 'draft') ?? null;
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

export type CategoryNamer = (category: string, year?: number) => string;

/**
 * The rate cards, and a function that names a category for a year (this
 * year by default). Until the cards are there it falls back to the letter.
 */
export function useRateCards(enabled = true) {
  const query = useQuery({ queryKey: RATE_CARDS_KEY, queryFn: fetchRateCards, enabled, retry: false });
  const cards = query.data?.items ?? [];
  const thisYear = new Date().getFullYear();
  const name: CategoryNamer = (category, year) =>
    categoryText(cardOfYear(cards, year ?? thisYear), category);
  return { cards, name, loaded: query.isSuccess, failed: query.isError };
}
